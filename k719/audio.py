"""Audio-wave effect: the keyboard becomes a spectrum analyser for whatever the PC plays.

Like the Windows app's "Audio wave" mode, this switches the firmware to PC-driven
mode (0xFE) and streams per-key colors with command 0x12. Audio comes from the
PipeWire/PulseAudio monitor of the default output via `parec`.
"""

import cmath
import colorsys
import math
import os
import select
import struct
import subprocess
import threading
import time

from . import layout
from .device import K719Error, KeyboardOffline

RATE = 22050
WINDOW = 512  # 23 ms of audio per frame: short enough that drum hits don't smear
FFT_N = 1024  # the window is zero-padded so neighbouring bass columns stay distinct
MIN_SPAN_DB = 16.0  # smallest dB range between an empty and a full column
# Rhythm: bars jump straight to a new peak and drop fast, and part of each bar's height comes
# from how far the column is above its own recent average, which is what makes beats visible.
# All per-frame rates below are defined at 30 fps and scaled by the real frame time.
FALL = 0.55  # fraction of the height kept per frame when the sound gets quieter
TRANSIENT_MIX = 0.7  # share of the bar driven by the jump above the recent average
TRANSIENT_KEEP = 0.85  # smoothing of that recent average (per frame)
TRANSIENT_DB = 6.0  # a jump this many dB above the average fills the column

STYLES = ("spectrum", "beat", "both")
MAX_CATCHUP = 4096  # samples of not-yet-analysed audio kept between frames (~190 ms)
CATCHUP_HOP = 512  # step between analysis windows (= WINDOW: back to back, nothing skipped)
MAX_WINDOWS = 5
BEAT_LEAD_S = 0.05  # capture + analysis delay that the beat flash is fired ahead of
# Through the 2.4G receiver packets reach the keyboard only every ~11 ms (measured by tapping
# along: a 1-packet flash showed ~45 ms late, a 14-packet full-keyboard flash ~190 ms), so:
WIRELESS_FADE_STEPS = 1  # beat flash is just on/off: 2 full frames per beat, not 4+
WIRELESS_MAX_PACKETS = 5  # per spectrum frame (~55 ms); the most-changed keys go first
WIRELESS_BASE_S = 0.035  # radio delay of the first packet


class BeatTracker:
    """Tempo-following beat tracker, like tapping a foot to the music.

    Onsets come from spectral flux over the whole spectrum (drums, hi-hats and vocal attacks
    carry the felt beat more reliably than the bass alone). Every half second the tempo is
    re-estimated by autocorrelating the last few seconds of onsets, weighted towards ~120 BPM
    (the tempo people tend to tap), and the beat grid is phase-aligned to the strongest onsets.
    Beats are predicted, so flashes can be fired slightly early to hide the display delay."""
    HOP = 256  # onset resolution: 11.6 ms at 22050 Hz
    WIN = 512
    HISTORY_S = 6.0
    MIN_BPM, MAX_BPM = 60.0, 180.0
    PREFERRED_BPM = 120.0
    PRIOR_OCTAVES = 1.0  # width of the tempo preference
    MIN_CONFIDENCE = 0.15  # autocorrelation strength below which no beats are shown
    ONSET_DELAY = 0.0  # hops between a hit and its onset peak (calibrated against taps)

    def __init__(self):
        self.rate = RATE / self.HOP
        self.window = [0.5 - 0.5 * math.cos(2 * math.pi * i / (self.WIN - 1))
                       for i in range(self.WIN)]
        self.pending = []
        self.prev = None
        self.env = []  # onset strength per hop
        self.n = 0  # hops processed so far
        self.period = None  # beat period in hops
        self.next_beat = None  # hop index of the next predicted beat
        self.last_estimate = -1
        self.sensitivity = 1.0

    def feed(self, new_samples):
        self.pending.extend(new_samples)
        while len(self.pending) >= self.WIN:
            seg = self.pending[:self.WIN]
            del self.pending[:self.HOP]
            sp = _fft([x * w for x, w in zip(seg, self.window)])
            mag = [math.log1p(100 * abs(z)) for z in sp[1:self.WIN // 2]]
            flux = sum(max(0.0, a - b) for a, b in zip(mag, self.prev)) if self.prev else 0.0
            self.prev = mag
            self.env.append(flux)
            self.n += 1
        keep = int(self.HISTORY_S * self.rate)
        if len(self.env) > keep:
            del self.env[:len(self.env) - keep]
        if self.n - self.last_estimate >= self.rate / 2 and len(self.env) >= keep // 2:
            self.last_estimate = self.n
            self._estimate()

    def _estimate(self):
        m = sum(self.env) / len(self.env)
        c = [x - m for x in self.env]
        norm = sum(x * x for x in c) or 1.0
        lo_lag = int(self.rate * 60 / self.MAX_BPM) - 1
        hi_lag = int(self.rate * 60 / self.MIN_BPM) + 2
        ac = {lag: sum(x * y for x, y in zip(c, c[lag:])) / norm
              for lag in range(lo_lag, min(2 * hi_lag + 2, len(c) - 1))}
        e = [max(0.0, x) for x in c]  # phase alignment only looks at above-average onsets

        def strength(lag):
            # a real beat also repeats at twice its period; crediting that echo stops the
            # tracker from flipping between a tempo and its half/double
            return ac[lag] + 0.5 * ac.get(2 * lag, 0.0)

        best, best_lag = 0.0, None
        for lag in range(lo_lag + 1, hi_lag):
            bpm = 60 * self.rate / lag
            prior = math.exp(-0.5 * (math.log2(bpm / self.PREFERRED_BPM) / self.PRIOR_OCTAVES) ** 2)
            if ac[lag] >= ac[lag - 1] and ac[lag] >= ac[lag + 1] and strength(lag) * prior > best:
                best, best_lag = strength(lag) * prior, lag
        if best_lag is None or best < self.MIN_CONFIDENCE / max(self.sensitivity, 0.1):
            self.period = None
            self.next_beat = None
            return
        # sub-frame period from a parabola through the peak: an integer period drifts
        # several ms per beat, which adds up to a visibly late/early grid
        y0, y1, y2 = ac[best_lag - 1], ac[best_lag], ac[best_lag + 1]
        den = y0 - 2 * y1 + y2
        period = best_lag + (0.5 * (y0 - y2) / den if den else 0.0)
        if self.period:
            if abs(period / self.period - 1) < 0.1:
                period = self.period * 0.7 + period * 0.3  # small drift: follow smoothly
                self.switch_votes = 0
            else:
                self.switch_votes = getattr(self, "switch_votes", 0) + 1
                if self.switch_votes < 3:  # a different tempo must win 3 times (1.5 s) in a row
                    period = self.period
                else:
                    self.next_beat = None
                    self.switch_votes = 0
        # phase: offset whose comb of beats (weighted towards recent ones) collects most onset
        start = len(e) - 1
        best_phase, best_score = 0.0, -1.0
        steps = max(1, int(period * 2))
        for k in range(steps):
            ph = k * period / steps
            score, w, pos = 0.0, 1.0, start - ph
            while pos >= 1:
                i = int(pos)
                f = pos - i
                score += w * (e[i] * (1 - f) + e[min(i + 1, start)] * f)
                pos -= period
                w *= 0.85
            if score > best_score:
                best_phase, best_score = ph, score
        # env[i] peaks one window after the hit it measures; ONSET_DELAY maps it back
        target = (self.n - 1 - best_phase) - self.ONSET_DELAY + period
        if self.next_beat is not None and self.period:
            # phase-locked loop: move the running grid part of the way to the new estimate
            err = (target - self.next_beat + period / 2) % period - period / 2
            target = self.next_beat + err * 0.35
        self.period = period
        self.next_beat = target

    def bpm(self):
        return 60 * self.rate / self.period if self.period else None

    def beat_due(self, lead_s=0.0):
        """True once per beat, `lead_s` seconds before the predicted beat."""
        if not self.period or self.next_beat is None:
            return False
        now = self.n + len(self.pending) / self.HOP + lead_s * self.rate
        if now >= self.next_beat:
            while self.next_beat <= now:
                self.next_beat += self.period
            return True
        return False


def _scale(c, k):
    return tuple(min(255, round(v * k)) for v in c)
MAX_SPAN_DB = 40.0  # largest; stops one quiet moment from squashing the scale
SILENCE_DB = 0.0  # below this a column counts as silent


def _fft(x):
    """Iterative radix-2 FFT (len(x) must be a power of two)."""
    n = len(x)
    a = [complex(v) for v in x]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    size = 2
    while size <= n:
        w_step = cmath.exp(-2j * math.pi / size)
        half = size // 2
        for start in range(0, n, size):
            w = 1
            for k in range(start, start + half):
                t = w * a[k + half]
                a[k + half] = a[k] - t
                a[k] = a[k] + t
                w *= w_step
        size *= 2
    return a


def _columns():
    """Group the keys into vertical columns by x position, rows by y position."""
    keys = [k for k in layout.KEYS]
    xs = sorted({round((k[1] + k[3] / 2) / 28) for k in keys})
    col_of = {}
    for k in keys:
        col_of[k[0]] = xs.index(round((k[1] + k[3] / 2) / 28))
    ys = sorted({k[2] for k in keys})
    rows = []
    for y in ys:
        if not rows or y - rows[-1] > 10:
            rows.append(y)
    row_of = {}
    for k in keys:
        # 0 = bottom row
        top_row = min(range(len(rows)), key=lambda r: abs(rows[r] - k[2]))
        row_of[k[0]] = len(rows) - 1 - top_row
    return col_of, len(xs), row_of, len(rows)


FREQ_LO, FREQ_HI = 40.0, 9000.0
BASS_MID_HZ = 250.0  # crossover between the bass and mid controls
MID_TREBLE_HZ = 2000.0  # crossover between the mid and treble controls


def _band_freqs(ncols):
    return [FREQ_LO * (FREQ_HI / FREQ_LO) ** (i / ncols) for i in range(ncols + 1)]


def _band_edges(ncols):
    return [max(1, int(f * FFT_N / RATE)) for f in _band_freqs(ncols)]


def tone_weights(ncols):
    """(bass, mid, treble) weight per column; blends over one octave around each crossover
    so neighbouring columns don't jump when a slider moves."""
    f = _band_freqs(ncols)
    out = []
    for c in range(ncols):
        center = math.log2(math.sqrt(f[c] * f[c + 1]))

        def rise(x0):
            return min(1.0, max(0.0, center - math.log2(x0) + 0.5))
        treble = rise(MID_TREBLE_HZ)
        bass = 1.0 - rise(BASS_MID_HZ)
        out.append((bass, 1.0 - bass - treble, treble))
    return out


def monitor_source():
    try:
        sink = subprocess.run(["pactl", "get-default-sink"], capture_output=True,
                              text=True, timeout=3).stdout.strip()
        if sink:
            return sink + ".monitor"
    except (OSError, subprocess.SubprocessError):
        pass
    return "@DEFAULT_MONITOR@"


class FrameSender:
    """Sends frames to the keyboard on its own thread, always the newest one.

    Analysis keeps running at full rate; whenever the link is free the latest frame goes
    out and older unsent frames are dropped. Through the 2.4G receiver a frame can take
    50-90 ms to send, so this keeps what the keys show as fresh as the link allows."""

    def __init__(self, kb, slots, per_packet):
        self.kb = kb
        self.slots = slots
        self.per_packet = per_packet  # seconds, running average
        self.error = None
        self.offline = False
        self.max_packets = None
        self._frame = None
        self._done = False
        self._cond = threading.Condition()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def post(self, frame):
        with self._cond:
            self._frame = frame
            self._cond.notify()

    def _run(self):
        while True:
            with self._cond:
                while self._frame is None and not self._done:
                    self._cond.wait()
                if self._done:
                    return
                frame, self._frame = self._frame, None
            try:
                t = time.monotonic()
                sent = self.kb.set_direct_colors(frame, slots=self.slots, bottom_first=True,
                                                 max_packets=self.max_packets)
                if sent:
                    self.per_packet = self.per_packet * 0.9 + (time.monotonic() - t) / sent * 0.1
            except KeyboardOffline:
                # wireless keyboard went to sleep: wait for it, then resend everything
                self.offline = True
                while not self._done and not self._link_back():
                    time.sleep(1.0)
                self.kb._direct_shown = None
                self.offline = False
            except Exception as e:  # reported by the analysis loop
                self.error = e
                return

    def _link_back(self):
        try:
            if self.kb.link_ok():
                self.kb.enter_direct_mode()
                return True
        except K719Error:
            pass
        return False

    def close(self):
        with self._cond:
            self._done = True
            self._cond.notify()
        self._thread.join(timeout=2)


def run_visualizer(kb, fg=None, bg=(0, 0, 0), rainbow=True, source=None, fps=30, gain=1.0,
                   stop=None, gains=None, style="spectrum"):
    """Run until Ctrl+C or until `stop` (a threading.Event) is set.
    Restores the previous lighting effect afterwards.

    Bar heights are multiplied by gains["overall"] and by the bass/mid/treble gain for
    each column's frequency range. `gains` is read on every frame, so a GUI can change
    it while the visualizer runs.

    style: "spectrum" (bars per frequency), "beat" (whole keyboard flashes on each beat
    found by the tempo tracker, new colour every beat) or "both" (bars over a background that flashes on beats).
    `style` may also be a dict {"style": ...} so it can be switched while running; the
    overall gain also sets how readily beats are detected."""
    if gains is None:
        gains = {"overall": gain, "bass": 1.0, "mid": 1.0, "treble": 1.0}
    style_box = style if isinstance(style, dict) else {"style": style}
    beats = BeatTracker()
    pulse = 0.0
    beat_hue = 0.0
    beat_color = fg or (255, 255, 255)
    col_of, ncols, row_of, nrows = _columns()
    edges = _band_edges(ncols)
    weights = tone_weights(ncols)
    window = [0.5 - 0.5 * math.cos(2 * math.pi * i / (WINDOW - 1)) for i in range(WINDOW)]
    padding = [0.0] * (FFT_N - WINDOW)
    colors_by_col = [
        tuple(int(c * 255) for c in colorsys.hsv_to_rgb(0.75 * c / max(1, ncols - 1), 1, 1))
        for c in range(ncols)]

    proc = subprocess.Popen(
        ["parec", "--device=" + (source or monitor_source()), "--format=s16le",
         f"--rate={RATE}", "--channels=1", "--latency-msec=20"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    fd = proc.stdout.fileno()
    os.set_blocking(fd, False)

    previous = kb.get_lighting()
    kb.enter_direct_mode()
    samples = [0.0] * WINDOW
    unseen = 0  # samples received since the last frame
    avg = [None] * ncols
    levels = [0.0] * ncols
    # Each column auto-ranges on its own: music has far more energy in the bass than the
    # treble, so a single global scale leaves the right-hand columns flat.
    hi = [-100.0] * ncols  # recent loudest level per column (falls slowly)
    lo = [100.0] * ncols  # recent quietest level per column (rises slowly)
    frame_time = 1.0 / fps
    slots = max(k[0] for k in layout.KEYS) + 1  # matrix slots past this have no LED
    full_packets = math.ceil(slots * 3 / kb.chunk)
    sender = FrameSender(kb, slots, 0.006 if kb.wireless else 0.002)
    last_tick = time.monotonic()
    leftover = b""
    try:
        while stop is None or not stop.is_set():
            t0 = time.monotonic()
            if select.select([fd], [], [], 0)[0]:
                raw = leftover + (proc.stdout.read(65536) or b"")
                n = len(raw) // 2
                leftover = raw[n * 2:]  # never split a 16-bit sample across reads
                if n:
                    new = [v / 32768 for v in struct.unpack("<%dh" % n, raw[:n * 2])]
                    samples = (samples + new)[-(WINDOW + MAX_CATCHUP):]
                    unseen = min(unseen + n, MAX_CATCHUP)
                    beats.sensitivity = gains.get("overall", 1.0)
                    beats.feed(new)
            elif proc.poll() is not None:
                raise RuntimeError("parec exited - is PipeWire/PulseAudio running?")
            # Analyse every window of audio that arrived since the last frame and keep the
            # loudest per column, so hits between frames aren't missed when the frame rate
            # drops (e.g. ~16 fps through the 2.4G receiver).
            col_energy = [0.0] * ncols
            end = len(samples)
            first_end = max(WINDOW, end - unseen)
            ends = list(range(end, first_end - 1, -CATCHUP_HOP)) or [end]
            for e in ends[:MAX_WINDOWS]:
                seg = samples[max(0, e - WINDOW):e]
                seg = [0.0] * (WINDOW - len(seg)) + seg
                spec = _fft([x * w for x, w in zip(seg, window)] + padding)
                for c in range(ncols):
                    a, b = edges[c], max(edges[c + 1], edges[c] + 1)
                    col_energy[c] = max(col_energy[c], sum(abs(v) ** 2 for v in spec[a:b]))
            unseen = 0
            now = time.monotonic()
            ticks = min(10.0, (now - last_tick) * 30)  # elapsed time in 30 fps frames
            last_tick = now
            g_all, g_bass, g_mid, g_treble = (gains.get(k, 1.0) for k in
                                              ("overall", "bass", "mid", "treble"))
            for c in range(ncols):
                db = 10 * math.log10(col_energy[c] + 1e-18)
                if db < SILENCE_DB:
                    v = 0.0  # silence: leave the range tracking alone
                else:
                    hi[c] = max(db, hi[c] - 0.1 * ticks)
                    lo[c] = max(min(db, lo[c] + 0.3 * ticks), hi[c] - MAX_SPAN_DB)
                    span = max(MIN_SPAN_DB, hi[c] - lo[c])
                    v = min(1.0, max(0.0, (db - (hi[c] - span)) / span)) ** 1.6
                    keep = TRANSIENT_KEEP ** ticks
                    avg[c] = db if avg[c] is None else avg[c] * keep + db * (1 - keep)
                    jump = min(1.0, max(0.0, (db - avg[c]) / TRANSIENT_DB))
                    v = v * (1 - TRANSIENT_MIX) + jump * TRANSIENT_MIX
                wb, wm, wt = weights[c]
                v = min(1.0, v * g_all * (wb * g_bass + wm * g_mid + wt * g_treble))
                if v > levels[c]:
                    levels[c] = v
                else:
                    fall = FALL ** ticks
                    levels[c] = levels[c] * fall + v * (1 - fall)
            # fire early enough that the middle of the (progressively sent) flash frame lands
            # on the beat: capture delay, plus over the receiver the radio delay and half of
            # a full frame at the radio's packet rate
            if kb.wireless:
                lead = BEAT_LEAD_S + WIRELESS_BASE_S + 0.5 * full_packets * kb.RF_PACKET_S
            else:
                lead = BEAT_LEAD_S + 0.75 * sender.per_packet * full_packets
            decay = 0.8 ** ticks  # same fade speed at any frame rate
            if beats.beat_due(lead_s=lead):
                pulse = 1.0
                if rainbow or fg is None:
                    beat_hue = (beat_hue + 0.13) % 1.0
                    beat_color = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(beat_hue, 1, 1))
            else:
                pulse *= decay
            shown = pulse
            if kb.wireless:
                shown = math.ceil(pulse * WIRELESS_FADE_STEPS - 0.3) / WIRELESS_FADE_STEPS
                shown = max(0.0, shown)
            mode = style_box.get("style", "spectrum")
            if mode == "beat":
                flash = _scale(beat_color, shown)
                frame = [flash if max(flash) > max(bg) else bg] * kb.num_keys
            else:
                back = bg
                if mode == "both":
                    flash = _scale(beat_color, shown * 0.35)
                    back = flash if max(flash) > max(bg) else bg
                frame = [back] * kb.num_keys
                for slot, c in col_of.items():
                    if row_of[slot] < int(levels[c] * nrows + 0.5):
                        frame[slot] = colors_by_col[c] if rainbow or fg is None else fg
            if sender.error:
                raise sender.error
            # over the receiver cap spectrum frames so the radio never queues up; a beat flash
            # is sent whole (it's predicted, so its send time is part of the lead)
            sender.max_packets = WIRELESS_MAX_PACKETS if kb.wireless and mode != "beat" else None
            sender.post(frame)
            dt = time.monotonic() - t0
            if dt < frame_time:
                time.sleep(frame_time - dt)
    except KeyboardInterrupt:
        pass
    finally:
        sender.close()
        proc.terminate()
        kb.set_lighting(mode=previous["mode"] if previous["mode"] != 0xFE else 1)
