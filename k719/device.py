"""Evision (VS11K53A) HID protocol used by the Redragon K719, reverse engineered
from K719-RGB-PRO.exe.

Every request is a 64-byte output report on the vendor interface (usage page 0xFF1C):

    [0]   0x04        report id
    [1:3] checksum    little-endian sum of bytes 3..63
    [3]   command
    [4]   length      payload bytes in this packet
    [5:7] offset      little-endian (the screen upload uses [5:8], 24 bit)
    [7]   0x00        (status byte in the reply)
    [8:]  payload

The keyboard answers each request with a 64-byte input report that echoes the
command byte. Reply byte [7] is 0xFF/0xFE on error. Through the 2.4G receiver a
reply with command 0xFF means the keyboard itself is not reachable (asleep/off).
Over the receiver only 0x18 payload bytes fit per packet; on the cable 0x38 do.
"""

import glob
import os
import select
import time

VID = 0x320F
RECEIVER_PIDS = {0x511C}
# Usage Page (Vendor 0xFF1C) ... Collection ... Report ID 4, as found in the report descriptor
USAGE_PAGE_TAG = b"\x06\x1c\xff\x09\x92\xa1\x01\x85\x04"

CMD_BEGIN = 0x01
CMD_END = 0x02
CMD_INFO = 0x03
CMD_READ_CONFIG = 0x05
CMD_WRITE_CONFIG = 0x06
CMD_READ_KEYMAP = 0x07  # returns the factory mapping, not the active one
CMD_WRITE_KEYMAP = 0x09
CMD_READ_COLORS = 0x0A
CMD_WRITE_COLORS = 0x0B
CMD_DIRECT_COLORS = 0x12
CMD_WRITE_MACROS = 0x15
CMD_READ_LED_MAP = 0x1B  # one byte per matrix slot: LED index (0xFF = none)
CMD_READ_MEMORY = 0x1A
CMD_SCREEN_DATA = 0x21
CMD_SCREEN_BEGIN = 0x23
CMD_LINK_STATUS = 0xAA

CONFIG_LEN = 0x15  # lighting part of the config block
FULL_CONFIG_LEN = 0x31  # whole block as written by the Windows app's "save everything" path
INFO_LEN = 0x25

# Offsets inside the config block (beyond the lighting fields)
CFG_SCREEN_FRAMES = 0x22  # number of frames stored for the TFT animation
CFG_CLOCK = 0x23  # 7 BCD bytes: second, minute, hour, weekday (0=Sunday), day, month, year%100
CFG_FRAME_INTERVAL = 0x2B  # 16-bit LE, milliseconds per animation frame

MODE_DIRECT = 0xFE  # effect id the Windows app uses while the PC streams colors (cmd 0x12)


class K719Error(Exception):
    pass


class KeyboardOffline(K719Error):
    pass


def _parse_uevent(path):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                out[k] = v
    except OSError:
        pass
    return out


def find_devices():
    """Return [(hidraw_path, pid, name)] for every Evision vendor interface."""
    found = []
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        ue = _parse_uevent(os.path.join(node, "device", "uevent"))
        hid_id = ue.get("HID_ID", "")
        try:
            _, vid, pid = (int(x, 16) for x in hid_id.split(":"))
        except ValueError:
            continue
        if vid != VID:
            continue
        try:
            with open(os.path.join(node, "device", "report_descriptor"), "rb") as f:
                desc = f.read()
        except OSError:
            continue
        if USAGE_PAGE_TAG not in desc:
            continue
        found.append(("/dev/" + os.path.basename(node), pid, ue.get("HID_NAME", "")))
    return found


class K719:
    def __init__(self, path=None, timeout=2.0, verbose=False):
        if path is None:
            devs = find_devices()
            if not devs:
                raise K719Error(
                    "no Redragon/Evision keyboard found (VID 320f with vendor interface)")
            path, pid, _ = devs[0]
        else:
            pid = None
            for p, dpid, _ in find_devices():
                if p == path:
                    pid = dpid
        self.path = path
        self.pid = pid
        self.wireless = pid in RECEIVER_PIDS
        self.chunk = 0x18 if self.wireless else 0x38
        self.timeout = timeout
        self.verbose = verbose
        try:
            self.fd = os.open(path, os.O_RDWR)
        except PermissionError:
            raise K719Error(
                f"permission denied on {path}; install 70-redragon-k719.rules "
                "(see README) and re-plug the keyboard/receiver")
        self._info = None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ---- transport -------------------------------------------------------

    @staticmethod
    def _packet(cmd, length=0, offset=0, data=b"", offset24=False):
        b = bytearray(64)
        b[0] = 0x04
        b[3] = cmd
        b[4] = length
        b[5] = offset & 0xFF
        b[6] = (offset >> 8) & 0xFF
        if offset24:
            b[7] = (offset >> 16) & 0xFF
        b[8:8 + len(data)] = data
        s = sum(b[3:])
        b[1] = s & 0xFF
        b[2] = (s >> 8) & 0xFF
        return bytes(b)

    def _drain(self):
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, 64)

    def transfer(self, cmd, length=0, offset=0, data=b"", offset24=False, timeout=None,
                 attempts=3):
        """Send one request and return the matching 64-byte reply."""
        timeout = self.timeout if timeout is None else timeout
        pkt = self._packet(cmd, length, offset, data, offset24)
        for attempt in range(attempts):
            self._drain()
            if self.verbose:
                print(">", pkt.hex(" "))
            os.write(self.fd, pkt)
            deadline = time.monotonic() + timeout
            while True:
                left = deadline - time.monotonic()
                if left <= 0 or not select.select([self.fd], [], [], left)[0]:
                    break
                r = os.read(self.fd, 64)
                if self.verbose:
                    print("<", r.hex(" "))
                if len(r) < 8 or r[0] != 0x04:
                    continue
                if r[3] == cmd and r[5] == pkt[5] and r[6] == pkt[6]:
                    if r[7] in (0xFE, 0xFF) and cmd != CMD_LINK_STATUS:
                        raise K719Error(f"command 0x{cmd:02x} rejected (status 0x{r[7]:02x})")
                    return r
                if r[3] == 0xFF and self.wireless:
                    raise KeyboardOffline(
                        "receiver found but the keyboard is not responding "
                        "(press a key to wake it, or check it is in 2.4G mode)")
        raise K719Error(f"no reply to command 0x{cmd:02x}")

    def read(self, cmd, total, base=0):
        out = bytearray()
        off = 0
        while off < total:
            n = min(self.chunk, total - off)
            r = self.transfer(cmd, n, base + off)
            out += r[8:8 + n]
            off += n
        return bytes(out)

    def write(self, cmd, data, base=0, progress=None, offset24=False):
        off = 0
        total = len(data)
        while off < total:
            n = min(self.chunk, total - off)
            self.transfer(cmd, n, base + off, data[off:off + n], offset24=offset24)
            off += n
            if progress:
                progress(off, total)

    def simple(self, cmd):
        return self.transfer(cmd)

    # ---- session ---------------------------------------------------------

    def link_ok(self):
        """True if the keyboard is reachable (always True on the cable)."""
        if not self.wireless:
            return True
        r = self.transfer(CMD_LINK_STATUS)
        return r[8] == 0xFF

    def wait_online(self, seconds=30.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.link_ok():
                return True
            time.sleep(0.5)
        return False

    def begin(self):
        self.simple(CMD_BEGIN)

    def end(self):
        time.sleep(0.01)
        self.simple(CMD_END)

    # ---- queries ---------------------------------------------------------

    def info(self):
        if self._info is None:
            self._info = self.read(CMD_INFO, INFO_LEN)
        return self._info

    @property
    def num_keys(self):
        n = self.info()[5]
        return n if n else 126

    def screen_size(self):
        i = self.info()
        return i[0x1F], i[0x20]

    # ---- lighting --------------------------------------------------------

    def get_lighting(self):
        b = self.read(CMD_READ_CONFIG, CONFIG_LEN, 0)
        return {
            "profile": b[0],
            "mode": b[1],
            "brightness": b[2],
            "speed": 5 - b[3] if b[3] <= 5 else b[3],
            "direction": b[4],
            "multicolor": b[5] != 0,
            "color": (b[6], b[7], b[8]),
            "raw": b,
        }

    def set_lighting(self, mode=None, brightness=None, speed=None, direction=None,
                     color=None, multicolor=None):
        b = bytearray(self.read(CMD_READ_CONFIG, CONFIG_LEN, 0))
        if mode is not None:
            b[1] = mode
        if brightness is not None:
            if not 0 <= brightness <= 5:
                raise ValueError("brightness must be 0..5")
            b[2] = brightness
        if speed is not None:
            if not 0 <= speed <= 5:
                raise ValueError("speed must be 0..5")
            b[3] = 5 - speed
        if direction is not None:
            b[4] = direction
        if multicolor is not None:
            b[5] = 1 if multicolor else 0
        if color is not None:
            b[6], b[7], b[8] = color
        self.begin()
        self.write(CMD_WRITE_CONFIG, bytes(b), 0)
        self.end()

    def update_config(self, fn):
        """Read the full config block, let fn modify it in place, write it back."""
        b = bytearray(self.read(CMD_READ_CONFIG, FULL_CONFIG_LEN, 0))
        fn(b)
        self.begin()
        self.write(CMD_WRITE_CONFIG, bytes(b), 0)
        self.end()

    @staticmethod
    def _put_clock(b, t):
        def bcd(v):
            return (v // 10) << 4 | (v % 10)
        wday = (t.tm_wday + 1) % 7  # Python: Monday=0; keyboard: Sunday=0
        b[CFG_CLOCK:CFG_CLOCK + 7] = bytes([
            bcd(t.tm_sec), bcd(t.tm_min), bcd(t.tm_hour), bcd(wday),
            bcd(t.tm_mday), bcd(t.tm_mon), bcd(t.tm_year % 100)])

    def get_clock(self):
        """Time last written to the keyboard (the running clock can't be read back)."""
        b = self.read(CMD_READ_CONFIG, 7, CFG_CLOCK)

        def unbcd(v):
            return (v >> 4) * 10 + (v & 0xF)
        s, mi, h, wd, d, mo, y = (unbcd(x) for x in b)
        return f"20{y:02d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"

    def sync_clock(self):
        """Set the keyboard's clock (shown on the TFT) to the PC's local time."""
        self.update_config(lambda b: self._put_clock(b, time.localtime()))

    # ---- per-key colors (used by the "custom" effect) ----------------------

    def get_custom_colors(self):
        n = self.num_keys
        d = self.read(CMD_READ_COLORS, n * 3, 0)
        return [tuple(d[i * 3:i * 3 + 3]) for i in range(n)]

    def set_custom_colors(self, colors):
        """colors: list indexed by matrix slot of (r, g, b)."""
        n = self.num_keys
        buf = bytearray(n * 3)
        for i, c in enumerate(colors[:n]):
            if c is not None:
                buf[i * 3:i * 3 + 3] = bytes(c)
        self.begin()
        self.write(CMD_WRITE_COLORS, bytes(buf), 0)
        self.end()

    def enter_direct_mode(self):
        """Switch the effect to PC-driven; afterwards send frames with set_direct_colors().
        The firmware drops frames sent faster than ~30 per second."""
        self.set_lighting(mode=MODE_DIRECT)
        self._direct_shown = None

    DIRECT_REFRESH_S = 3.0  # resend each packet at least this often, in case one was lost
    # Through the 2.4G receiver each packet is acknowledged after ~6 ms but only reaches the
    # keyboard every ~11 ms; anything sent faster queues up in the receiver and the lights fall
    # further and further behind (measured by tapping: 1 packet ~45 ms, 14 packets ~190 ms).
    RF_PACKET_S = 0.011

    def set_direct_colors(self, colors, slots=None, bottom_first=False, max_packets=None):
        """Show one frame of per-key colors without saving (needs enter_direct_mode()).

        Only packets whose keys changed are sent (the keyboard applies partial updates).
        `slots` limits the frame to the first N matrix slots (the ones with LEDs).
        `max_packets` caps the packets per call: the most-changed ones go first and the rest
        stay pending for the next call. `bottom_first` sends the highest slots (bottom rows)
        first, which is where visualizer bars start. Returns the number of packets sent."""
        n = min(slots or self.num_keys, self.num_keys)
        buf = bytearray(n * 3)
        for i, c in enumerate(colors[:n]):
            if c is not None:
                buf[i * 3:i * 3 + 3] = bytes(c)
        shown = getattr(self, "_direct_shown", None)
        offsets = list(range(0, len(buf), self.chunk))
        if shown is None or len(shown) != len(buf):
            shown = None
            self._direct_shown = bytearray(len(buf))
            self._direct_sent_at = [0.0] * len(offsets)
        now = time.monotonic()
        todo = []
        for idx, off in enumerate(offsets):
            seg = buf[off:off + self.chunk]
            if shown is None:
                change = float("inf")
            else:
                change = sum(abs(x - y) for x, y in zip(seg, shown[off:off + self.chunk]))
            if change > 0:
                todo.append((change, off, idx))
            elif now - self._direct_sent_at[idx] >= self.DIRECT_REFRESH_S:
                todo.append((0.5, off, idx))  # refresh, lowest priority
        todo.sort(key=lambda t: (-t[0], -t[1] if bottom_first else t[1]))
        if max_packets:
            todo = todo[:max_packets]
        # changed keys go out first (in row order), routine refreshes only after them, so a
        # refresh never delays something the user should see now
        todo.sort(key=lambda t: (t[0] == 0.5, -t[1] if bottom_first else t[1]))
        for _change, off, idx in todo:
            if self.wireless:
                wait = getattr(self, "_next_send", 0.0) - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
            seg = bytes(buf[off:off + self.chunk])
            self.transfer(CMD_DIRECT_COLORS, len(seg), off, seg, timeout=0.5)
            self._next_send = time.monotonic() + self.RF_PACKET_S
            self._direct_shown[off:off + len(seg)] = seg
            self._direct_sent_at[idx] = time.monotonic()
        return len(todo)

    def send_direct_packet(self, first_slot, colors):
        """Send one packet of direct colors starting at `first_slot` (for timing tests).
        Returns the time it was handed to the device. Over the receiver it is paced like
        set_direct_colors so it never queues behind earlier packets."""
        data = b"".join(bytes(c) for c in colors)[:self.chunk]
        if self.wireless:
            wait = getattr(self, "_next_send", 0.0) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        sent_at = time.monotonic()
        self.transfer(CMD_DIRECT_COLORS, len(data), first_slot * 3, data, timeout=0.5)
        self._next_send = time.monotonic() + self.RF_PACKET_S
        return sent_at

    # ---- key mapping -----------------------------------------------------

    def get_default_keymap(self):
        """Factory mapping stored in the firmware (not the active one)."""
        n = self.num_keys
        d = self.read(CMD_READ_KEYMAP, n * 3, 0)
        return [bytes(d[i * 3:i * 3 + 3]) for i in range(n)]

    def set_keymap(self, entries):
        buf = b"".join(bytes(e) for e in entries)
        if len(buf) != self.num_keys * 3:
            raise ValueError("keymap size mismatch")
        self.begin()
        self.write(CMD_WRITE_KEYMAP, buf, 0)
        self.end()

    # ---- screen ----------------------------------------------------------

    def upload_screen(self, frames, interval_ms=100, progress=None):
        """Upload one or more RGB565 (big-endian) frames to the TFT. USB cable only.

        Each frame is padded to a 32 KiB multiple and the frames are sent back to back.
        The frame count and interval live in the config block, which the Windows app
        rewrites (together with the clock) right before the image data."""
        if self.wireless:
            raise K719Error("screen uploads only work with the keyboard on the USB cable")
        if isinstance(frames, (bytes, bytearray)):
            frames = [frames]
        max_frames = self.info()[0x23] or 80
        if len(frames) > max_frames:
            raise K719Error(f"too many frames ({len(frames)}), the keyboard holds {max_frames}")
        data = bytearray()
        for f in frames:
            data += f
            data += bytes((-len(f)) % 0x8000)

        def cfg(b):
            b[CFG_SCREEN_FRAMES] = len(frames)
            b[CFG_FRAME_INTERVAL] = interval_ms & 0xFF
            b[CFG_FRAME_INTERVAL + 1] = (interval_ms >> 8) & 0xFF
            self._put_clock(b, time.localtime())
        self.update_config(cfg)

        self.begin()
        # The keyboard erases the stored animation before answering; with 80 frames stored
        # that takes several seconds (the Windows app waits up to 50 s). Never resend it.
        self.transfer(CMD_SCREEN_BEGIN, timeout=60.0, attempts=1)
        off = 0
        while off < len(data):
            n = min(self.chunk, len(data) - off)
            self.transfer(CMD_SCREEN_DATA, n, off, bytes(data[off:off + n]), offset24=True,
                          timeout=5.0)
            if off == 0:
                time.sleep(0.5)  # the Windows app waits here while the flash is erased
            off += n
            if progress:
                progress(off, len(data))
        self.end()
