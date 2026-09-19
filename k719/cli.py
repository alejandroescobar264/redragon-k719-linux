"""k719 - command line control for the Redragon K719 on Linux."""

import argparse
import sys

from . import __version__, layout, state
from .device import K719, K719Error, KeyboardOffline, find_devices


def parse_color(s):
    s = s.strip().lstrip("#")
    if "," in s:
        r, g, b = (int(x, 0) for x in s.split(","))
    else:
        if len(s) != 6:
            raise argparse.ArgumentTypeError(f"bad color '{s}' (use RRGGBB or r,g,b)")
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return (r, g, b)


def parse_mode(s):
    s = s.lower()
    if s in layout.MODE_IDS:
        return layout.MODE_IDS[s]
    try:
        return int(s, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"unknown mode '{s}'; choose from: {', '.join(layout.MODE_IDS)}")


def open_kb(args):
    kb = K719(args.device, verbose=args.verbose)
    if kb.wireless and not kb.link_ok():
        print("Keyboard not reachable through the receiver - press a key to wake it...",
              file=sys.stderr)
        if not kb.wait_online(30):
            raise KeyboardOffline("keyboard did not wake up")
    return kb


def cmd_list(args):
    devs = find_devices()
    if not devs:
        print("no device found")
        return 1
    for path, pid, name in devs:
        kind = "2.4G receiver" if pid in (0x511C,) else "USB"
        print(f"{path}  320f:{pid:04x}  {name}  ({kind})")


def cmd_info(args):
    with open_kb(args) as kb:
        i = kb.info()
        print(f"device      : {kb.path} ({'2.4G receiver' if kb.wireless else 'USB cable'})")
        print(f"keys        : {kb.num_keys}")
        print(f"info bytes  : {i.hex(' ')}")
        light = kb.get_lighting()
        print_light(light)


def print_light(l):
    name = layout.MODES.get(l["mode"], f"unknown({l['mode']})")
    if l["mode"] == 0xFE:
        name = "PC-driven (audio wave running)"
    print(f"mode        : {name} ({l['mode']})")
    print(f"brightness  : {l['brightness']}/5")
    print(f"speed       : {l['speed']}/5")
    print(f"direction   : {l['direction']}")
    print(f"colors      : {'multicolor' if l['multicolor'] else 'single'}")
    print("color       : #%02x%02x%02x" % l["color"])


def cmd_light(args):
    with open_kb(args) as kb:
        if all(v is None for v in (args.mode, args.brightness, args.speed, args.direction,
                                   args.color, args.multicolor)):
            print_light(kb.get_lighting())
            return
        multicolor = args.multicolor
        if args.color is not None and multicolor is None:
            multicolor = False
        kb.set_lighting(mode=args.mode, brightness=args.brightness, speed=args.speed,
                        direction=args.direction, color=args.color, multicolor=multicolor)
        print_light(kb.get_lighting())


def cmd_off(args):
    with open_kb(args) as kb:
        kb.set_lighting(mode=layout.MODE_IDS["off"])


def cmd_keys(args):
    for k in layout.KEYS:
        print(f"{layout.key_name(k[0]):16s} #{k[0]}")


def cmd_colors(args):
    with open_kb(args) as kb:
        colors = kb.get_custom_colors()
        if not args.set and args.all is None and not args.reset:
            for k in layout.KEYS:
                c = colors[k[0]] if k[0] < len(colors) else (0, 0, 0)
                print(f"{layout.key_name(k[0]):16s} #%02x%02x%02x" % c)
            return
        if args.reset:
            colors = [(0, 0, 0)] * len(colors)
        if args.all is not None:
            colors = [args.all] * len(colors)
        for item in args.set or []:
            keys, _, col = item.rpartition("=")
            if not keys:
                raise SystemExit(f"bad --set '{item}', expected KEY[,KEY...]=RRGGBB")
            c = parse_color(col)
            for k in keys.split(","):
                colors[layout.resolve_key(k)] = c
        kb.set_custom_colors(colors)
        if not args.no_activate:
            kb.set_lighting(mode=layout.MODE_CUSTOM)
        print("custom colors written" + ("" if args.no_activate else ", custom mode active"))


def cmd_keymap(args):
    with open_kb(args) as kb:
        km = state.load_keymap(kb.num_keys) or kb.get_default_keymap()
        if not args.set and not args.reset:
            for k in layout.KEYS:
                if k[0] < len(km):
                    print(f"{layout.key_name(k[0]):16s} -> {layout.describe_action(km[k[0]])}")
            return
        if args.reset:
            f = layout.FACTORY_KEYMAP
            km = [f[i * 3:i * 3 + 3] for i in range(len(km))]
        for item in args.set or []:
            key, _, action = item.partition("=")
            if not action:
                raise SystemExit(f"bad --set '{item}', expected KEY=ACTION")
            km[layout.resolve_key(key)] = layout.encode_action(action)
        kb.set_keymap(km)
        state.save_keymap(km)
        print("keymap written")


def cmd_screen(args):
    from .image import load_rgb565_frames
    with open_kb(args) as kb:
        w, h = kb.screen_size()
        if args.size:
            w, h = (int(x) for x in args.size.lower().split("x"))
        if not w or not h:
            raise SystemExit("keyboard did not report a screen size; pass --size WxH")
        frames, interval = load_rgb565_frames(args.image, w, h, bgr=args.bgr,
                                              max_frames=min(80, kb.info()[0x23] or 80))
        if args.interval:
            interval = args.interval
        print(f"{len(frames)} frame(s) of {w}x{h}, {interval} ms per frame")

        def progress(done, total):
            print(f"\r{done * 100 // total:3d}%", end="", flush=True)
        kb.upload_screen(frames, interval, progress=progress)
        print("\ndone")


def cmd_time(args):
    with open_kb(args) as kb:
        if args.show:
            print(f"clock last set to {kb.get_clock()} (the keyboard can't report its running time)")
        else:
            kb.sync_clock()
            print(f"keyboard clock set to {kb.get_clock()}")


def cmd_audio(args):
    from .audio import run_visualizer
    with open_kb(args) as kb:
        run_visualizer(kb, fg=args.color, bg=args.background, rainbow=args.color is None,
                       source=args.source, fps=args.fps, style=args.style,
                       light_delay_s=None if args.no_calibration else state.get_light_delay(kb),
                       gains={"overall": args.gain, "bass": args.bass, "mid": args.mid,
                              "treble": args.treble})


def cmd_raw(args):
    with open_kb(args) as kb:
        d = kb.read(int(args.cmd, 16), int(args.length, 0), int(args.offset, 0))
        for i in range(0, len(d), 16):
            print("%04x: %s" % (int(args.offset, 0) + i, d[i:i + 16].hex(" ")))


def main(argv=None):
    p = argparse.ArgumentParser(prog="k719", description=__doc__)
    p.add_argument("-d", "--device", help="hidraw node (default: auto-detect)")
    p.add_argument("-v", "--verbose", action="store_true", help="dump HID traffic")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list detected keyboards/receivers").set_defaults(func=cmd_list)
    sub.add_parser("info", help="show device info and lighting").set_defaults(func=cmd_info)

    s = sub.add_parser("light", help="show or change the lighting effect")
    s.add_argument("-m", "--mode", type=parse_mode,
                   help="effect: " + ", ".join(layout.MODE_IDS))
    s.add_argument("-b", "--brightness", type=int, help="0-5")
    s.add_argument("-s", "--speed", type=int, help="0-5")
    s.add_argument("-D", "--direction", type=int, help="effect direction (0, 1, ...)")
    s.add_argument("-c", "--color", type=parse_color, help="RRGGBB (implies single color)")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--multicolor", dest="multicolor", action="store_true", default=None,
                   help="rainbow colors instead of --color")
    g.add_argument("--single", dest="multicolor", action="store_false",
                   help="use the single --color")
    s.set_defaults(func=cmd_light)

    sub.add_parser("off", help="turn the backlight off").set_defaults(func=cmd_off)
    sub.add_parser("keys", help="list key names").set_defaults(func=cmd_keys)

    s = sub.add_parser("colors", help="show or set per-key colors (custom effect)")
    s.add_argument("--set", action="append", metavar="KEY[,KEY]=RRGGBB")
    s.add_argument("--all", type=parse_color, metavar="RRGGBB", help="set every key")
    s.add_argument("--reset", action="store_true", help="start from all keys black")
    s.add_argument("--no-activate", action="store_true",
                   help="do not switch the effect to 'custom'")
    s.set_defaults(func=cmd_colors)

    s = sub.add_parser("keymap", help="show or remap keys")
    s.add_argument("--set", action="append", metavar="KEY=ACTION",
                   help="e.g. capslock=lctrl, f12=ctrl+alt+delete, rctrl=menu, lgui=none, raw:200029")
    s.add_argument("--reset", action="store_true", help="restore factory mapping")
    s.set_defaults(func=cmd_keymap)

    s = sub.add_parser("screen", help="upload an image or GIF to the TFT screen (USB cable only)")
    s.add_argument("image")
    s.add_argument("--size", help="override screen size, e.g. 240x135")
    s.add_argument("--bgr", action="store_true", help="swap red/blue if colors look wrong")
    s.add_argument("--interval", type=int, help="ms per frame for animations (default: from GIF)")
    s.set_defaults(func=cmd_screen)

    s = sub.add_parser("time", help="set the keyboard clock to this PC's time")
    s.add_argument("--show", action="store_true", help="print when the clock was last set")
    s.set_defaults(func=cmd_time)

    s = sub.add_parser("audio", help="audio-wave effect: key columns follow the sound (Ctrl+C stops)")
    s.add_argument("-c", "--color", type=parse_color, help="bar color (default: rainbow)")
    s.add_argument("--background", type=parse_color, default=(0, 0, 0), metavar="RRGGBB",
                   help="color of unlit keys (default: off)")
    s.add_argument("--source", help="PulseAudio/PipeWire source (default: output monitor)")
    s.add_argument("--fps", type=int, default=30, help="frames per second (default 30)")
    s.add_argument("--gain", type=float, default=1.0,
                   help="overall sensitivity: bar height multiplier and beat detection (default 1)")
    s.add_argument("--no-calibration", action="store_true",
                   help="ignore the saved sync calibration (see the app's Audio wave tab)")
    s.add_argument("--style", choices=("spectrum", "beat", "both"), default="spectrum",
                   help="bars per frequency, whole-keyboard flash on each beat, or both")
    s.add_argument("--bass", type=float, default=1.0,
                   help="bass (< 250 Hz) multiplier")
    s.add_argument("--mid", type=float, default=1.0, help="mid (250 Hz - 2 kHz) multiplier")
    s.add_argument("--treble", type=float, default=1.0, help="treble (> 2 kHz) multiplier")
    s.set_defaults(func=cmd_audio)

    s = sub.add_parser("raw", help="dump device memory (debug)")
    s.add_argument("cmd", help="read command in hex (03 info, 05 config, 07 keymap, 0a colors, 1b led map)")
    s.add_argument("length")
    s.add_argument("offset", nargs="?", default="0")
    s.set_defaults(func=cmd_raw)

    args = p.parse_args(argv)
    try:
        return args.func(args) or 0
    except (K719Error, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
