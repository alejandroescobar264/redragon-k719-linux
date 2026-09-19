"""Audio-wave sync calibration: measures how late the keyboard's lights appear.

The user presses a key in time with two steady rhythms:

1. sound round - beeps played through the speakers; each beep's time is taken from the
   speaker *monitor*, the same audio stream the visualizer analyses;
2. light round - flashes of the home row from Caps Lock to J: matrix slots 48-55, exactly one
   packet, so all eight keys light at the same instant (a full-keyboard flash needs 14 packets
   and sweeps across the keyboard over the 2.4G receiver); each flash's time is the moment
   it is sent.

Presses are matched to the nearest event. The difference between the two rounds' median
offsets is the light delay of one packet: the user's own anticipation of a steady beat cancels
out, and so does the speaker delay. The two rounds are saved separately, so either can be
redone alone. The visualizer fires its beat flashes that much earlier, plus half the time a
full-keyboard flash takes to go out.
"""

import math
import os
import select
import struct
import subprocess
import tempfile
import threading
import time
import wave

from . import layout
from .audio import RATE, monitor_source

PERIOD = 0.5  # seconds between beeps/flashes (120 BPM)
EVENTS = 16
WARMUP = 3  # first events are only for getting into the rhythm
BEEP_HZ = 1000
MIN_MATCHES = 8
MAX_SPREAD = 0.12  # s, interquartile range of offsets above which a round is rejected
DELAY_RANGE = (-0.4, 0.6)  # s, plausible light delays
FLASH_SLOTS = range(48, 56)  # Caps Lock, A, S, D, F, G, H, J: one packet
FLASH_KEYS = "Caps Lock to J"


class CalibrationError(Exception):
    pass


def _beep_track(path, count=EVENTS, lead_in=0.6):
    length = int(RATE * 0.03)
    buf = [0.0] * int(RATE * (lead_in + count * PERIOD + 0.5))
    for k in range(count):
        start = int(RATE * (lead_in + k * PERIOD))
        for i in range(length):
            buf[start + i] = (0.8 * math.sin(2 * math.pi * BEEP_HZ * i / RATE)
                              * math.sin(math.pi * i / length))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(v * 32767)) for v in buf))


def _detect_beeps(chunks):
    """Beep times (monotonic clock) from monitor chunks [(arrival time, bytes)]."""
    samples, times = [], []
    for t, data in chunks:
        n = len(data) // 2
        values = struct.unpack("<%dh" % n, data[:n * 2])
        for i, v in enumerate(values):
            samples.append(v / 32768)
            times.append(t - (n - 1 - i) / RATE)
    hop = 110  # 5 ms
    k = 2 * math.cos(2 * math.pi * BEEP_HZ / RATE)
    env = []
    for s0 in range(0, len(samples) - hop, hop):
        q1 = q2 = 0.0
        for x in samples[s0:s0 + hop]:
            q1, q2 = x + k * q1 - q2, q1
        env.append((times[s0], q1 * q1 + q2 * q2 - k * q1 * q2))
    if not env:
        return []
    peak = max(e for _, e in env)
    base = sorted(e for _, e in env)[len(env) // 2]
    if peak < base * 20 or peak < 1e-4:
        return []  # no clear beeps: muted, or drowned by other sound
    threshold = base + (peak - base) * 0.3
    beeps, last = [], -1.0
    for t, e in env:
        if e > threshold and t - last > PERIOD * 0.6:
            beeps.append(t)
            last = t
    return beeps


def sound_round(stop=None, on_event=None):
    """Play the beep track and return the beep times as heard on the speaker monitor."""
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="k719-beeps-")
    os.close(fd)
    _beep_track(path)
    rec = subprocess.Popen(["parec", "--device=" + monitor_source(), "--format=s16le",
                            f"--rate={RATE}", "--channels=1", "--latency-msec=10"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    player = None
    chunks = []
    try:
        rfd = rec.stdout.fileno()
        time.sleep(0.3)
        player = subprocess.Popen(["paplay", path], stderr=subprocess.DEVNULL)
        start = time.monotonic()
        end = start + 0.6 + EVENTS * PERIOD + 0.6
        announced = 0
        while time.monotonic() < end and not (stop and stop.is_set()):
            if select.select([rfd], [], [], 0.05)[0]:
                chunks.append((time.monotonic(), os.read(rfd, 65536)))
            if on_event:  # progress: expected beeps so far
                due = int((time.monotonic() - start - 0.6) / PERIOD) + 1
                while announced < min(due, EVENTS):
                    announced += 1
                    on_event(announced)
    finally:
        rec.terminate()
        if player:
            player.terminate()
        os.unlink(path)
    beeps = _detect_beeps(chunks)
    if len(beeps) < EVENTS - 2:
        raise CalibrationError(
            "Couldn't hear the beeps on the speaker output. Pause any music, make sure the "
            "sound isn't muted, and try again.")
    return beeps


def light_round(kb, stop=None, on_event=None):
    """Flash the home-row keys on a steady beat; return the moments each flash was sent.

    Each flash is one packet sent directly (no other traffic in between), so the flashes are
    evenly spaced and time-stamped at the moment they go out."""
    slots = max(k[0] for k in layout.KEYS) + 1
    first = FLASH_SLOTS[0]
    count = len(FLASH_SLOTS)
    white = [(255, 255, 255)] * count
    black = [(0, 0, 0)] * count
    previous = kb.get_lighting()["mode"]
    kb.enter_direct_mode()
    events = []
    try:
        kb.set_direct_colors([(0, 0, 0)] * kb.num_keys, slots=slots)  # everything off
        t0 = time.monotonic() + 1.0
        for k in range(EVENTS):
            if stop and stop.is_set():
                break
            time.sleep(max(0.0, t0 + k * PERIOD - time.monotonic()))
            events.append(kb.send_direct_packet(first, white))
            if on_event:
                on_event(k + 1)
            time.sleep(max(0.0, t0 + k * PERIOD + 0.12 - time.monotonic()))
            kb.send_direct_packet(first, black)
        time.sleep(0.4)
    finally:
        kb.set_lighting(mode=previous if previous != 0xFE else 1)
    return events


def offsets(events, presses):
    """Offsets of presses from their nearest event, ignoring the warm-up events."""
    counted = events[WARMUP:]
    if not counted:
        return []
    out = []
    for p in presses:
        if p < counted[0] - PERIOD / 2:
            continue
        nearest = min(counted, key=lambda e: abs(e - p))
        if abs(p - nearest) < PERIOD / 2:
            out.append(p - nearest)
    return sorted(out)


ROUND_WORDS = {"sound": ("beep", "beeps"), "light": ("flash", "flashes")}


def summarize(offs, which):
    """Median offset of a round ("sound" or "light"), checking there are enough, consistent
    presses. Returns (median, spread) in seconds."""
    one, many = ROUND_WORDS[which]
    if len(offs) < MIN_MATCHES:
        raise CalibrationError(
            f"Only {len(offs)} presses matched the {many}. Press Space once for every "
            f"{one}, keeping the rhythm, and try again.")
    q1, q3 = offs[len(offs) // 4], offs[(3 * len(offs)) // 4]
    if q3 - q1 > MAX_SPREAD:
        raise CalibrationError(
            f"The presses were too irregular (spread {round((q3 - q1) * 1000)} ms). "
            f"Try again, pressing steadily with the {many}.")
    return offs[len(offs) // 2], q3 - q1


def check_delay(delay):
    """Raise if a combined light delay (s) is implausible."""
    if not DELAY_RANGE[0] <= delay <= DELAY_RANGE[1]:
        raise CalibrationError(
            f"The sound and light rounds give an implausible delay ({round(delay * 1000)} ms). "
            "Redo the round that felt off.")


class Presses:
    """Thread-safe list of key-press times (time.monotonic)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._times = []

    def add(self, t=None):
        with self._lock:
            self._times.append(time.monotonic() if t is None else t)

    def take(self):
        with self._lock:
            times, self._times = self._times, []
        return times

    def __len__(self):
        with self._lock:
            return len(self._times)
