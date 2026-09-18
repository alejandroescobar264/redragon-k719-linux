"""Image loading for the TFT screen (uses GdkPixbuf, so no extra Python deps)."""

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib  # noqa: E402


def pixbuf_to_rgb565(pb, width, height, bgr=False):
    pb = pb.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
    n = pb.get_n_channels()
    stride = pb.get_rowstride()
    px = pb.get_pixels()
    out = bytearray(width * height * 2)
    o = 0
    for y in range(height):
        row = y * stride
        for x in range(width):
            i = row + x * n
            r, g, b = px[i], px[i + 1], px[i + 2]
            if bgr:
                r, b = b, r
            v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out[o] = v >> 8
            out[o + 1] = v & 0xFF
            o += 2
    return bytes(out)


def gif_delays(path):
    """Frame delays in ms, read from the GIF block structure (no pixel decoding)."""
    with open(path, "rb") as f:
        d = f.read()
    if d[:3] != b"GIF":
        return []
    pos = 13
    if d[10] & 0x80:
        pos += 3 << ((d[10] & 7) + 1)
    delays = []
    delay = 100
    while pos < len(d):
        tag = d[pos]
        if tag == 0x3B:  # trailer
            break
        if tag == 0x21:  # extension
            label = d[pos + 1]
            pos += 2
            if label == 0xF9:
                delay = (d[pos + 2] | d[pos + 3] << 8) * 10 or 100
            while d[pos]:
                pos += d[pos] + 1
            pos += 1
        elif tag == 0x2C:  # image descriptor
            flags = d[pos + 9]
            pos += 10
            if flags & 0x80:
                pos += 3 << ((flags & 7) + 1)
            pos += 1  # LZW minimum code size
            while d[pos]:
                pos += d[pos] + 1
            pos += 1
            delays.append(delay)
            delay = 100
        else:
            break
    return delays


def load_frames(path, max_frames=80):
    """Return ([GdkPixbuf frames], interval_ms). Still images give one frame.

    The keyboard plays every frame with one fixed interval, so GIF frames with
    varying delays are resampled onto a fixed time grid."""
    anim = GdkPixbuf.PixbufAnimation.new_from_file(path)
    delays = gif_delays(path)
    if anim.is_static_image() or len(delays) < 2:
        return [anim.get_static_image()], 100
    t = GLib.TimeVal()
    it = anim.get_iter(t)
    frames = []  # (start_ms, composited pixbuf)
    start = 0
    for d in delays:
        frames.append((start, it.get_pixbuf().copy()))
        start += d
        t.add(d * 1000)
        it.advance(t)
    total = start
    interval = max(20, min(delays))
    count = max(1, round(total / interval))
    if count > max_frames:
        count = max_frames
        interval = max(20, round(total / count))
    out = []
    for k in range(count):
        at = k * interval
        cur = frames[0][1]
        for s0, pb in frames:
            if s0 <= at:
                cur = pb
        out.append(cur)
    return out, interval


def load_rgb565_frames(path, width, height, bgr=False, max_frames=80):
    frames, interval = load_frames(path, max_frames)
    return [pixbuf_to_rgb565(f, width, height, bgr) for f in frames], interval


def load_rgb565(path, width, height, bgr=False):
    pb = GdkPixbuf.Pixbuf.new_from_file(path)
    return pixbuf_to_rgb565(pb, width, height, bgr)
