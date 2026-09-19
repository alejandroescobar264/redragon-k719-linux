# `k719` command reference

`k719` does everything the app does, from a terminal or a script. Global options go before the
command:

```sh
k719 [-d /dev/hidrawN] [-v] <command> [options]
```

| Option | Meaning |
|---|---|
| `-d`, `--device` | Use this hidraw node instead of auto-detecting |
| `-v`, `--verbose` | Print every HID packet sent and received |
| `--version` | Show the version |

Through the 2.4G receiver the keyboard falls asleep after a while. Commands notice this and
ask you to press a key.

---

## `list`, `info`

```sh
k719 list        # detected keyboards / receivers
k719 info        # device info and current lighting
```

## `light`: lighting effect

```sh
k719 light                                  # show current settings
k719 light -m wave -b 5 -s 3 --multicolor   # rainbow wave, full brightness
k719 light -m static -c ff8800              # solid orange
k719 light -m breath -c 00ffff -s 2
k719 off                                    # backlight off
```

| Option | Meaning |
|---|---|
| `-m`, `--mode` | static, breath, spectrum, traverse, rain, ripples, stars, reaction, stream, corrugated, cartoon, wave, serpentine, roll, flowers, scan, surmount, speed, custom, off |
| `-b`, `--brightness` | 0–5 |
| `-s`, `--speed` | 0–5 |
| `-D`, `--direction` | effect direction (0, 1, …) |
| `-c`, `--color` | `RRGGBB` (implies single color) |
| `--multicolor` / `--single` | rainbow or the single `--color` |

## `colors`: per-key colors

Writes the colors of the *Custom* effect and switches to it.

```sh
k719 colors                                   # list current per-key colors
k719 colors --all 000040 --set w,a,s,d=00ff00 --set esc=ff0000
k719 colors --reset --set space=ffffff        # everything black except Space
```

| Option | Meaning |
|---|---|
| `--set KEY[,KEY]=RRGGBB` | color one or more keys (repeatable) |
| `--all RRGGBB` | color every key first |
| `--reset` | start from all keys black |
| `--no-activate` | don't switch the effect to *Custom* |

`k719 keys` lists the key names (`esc`, `f1`, `a`, `kp_1`, `lctrl`, `space`, …). `#<slot>`
addresses a matrix slot directly.

## `keymap`: remap keys

```sh
k719 keymap                                  # show the mapping
k719 keymap --set capslock=lctrl             # Caps Lock becomes Ctrl
k719 keymap --set f12=ctrl+alt+delete        # key combos
k719 keymap --set rctrl=menu --set lgui=none # Menu key; disable Win
k719 keymap --reset                          # factory mapping
```

Actions can be a key name, a combo such as `ctrl+shift+esc`, `none`/`disable`, or
`raw:XXYYZZ` for a raw 3-byte entry (see [PROTOCOL.md](PROTOCOL.md#key-matrix-and-key-map)).

The keyboard can't report its active mapping, so `k719` keeps a record in
`~/.config/k719/keymap.bin`. If you remapped keys with the Windows app, run
`k719 keymap --reset` once so the two agree.

## `screen`: images and GIFs (USB cable only)

```sh
k719 screen picture.png
k719 screen animation.gif --interval 80
```

| Option | Meaning |
|---|---|
| `--interval MS` | milliseconds per frame (default: taken from the GIF) |
| `--size WxH` | override the screen size (default: read from the keyboard, 240×135) |
| `--bgr` | swap red and blue if colors look wrong |

- **Frames:** up to 80, uploaded at about 3 s per frame.
- **Timing:** the keyboard plays every frame at one fixed interval, so GIFs with uneven frame
  delays are resampled.
- **Replaces the stored animation:** an upload overwrites whatever animation the keyboard had.

## `time`: clock

```sh
k719 time          # set the keyboard's clock to this PC's time
k719 time --show   # when it was last set (the running clock can't be read)
```

Every screen upload also sets the clock, like the Windows app does. The 12 h / 24 h format is
chosen on the keyboard.

## `audio`: music visualizer

```sh
k719 audio                                # spectrum bars, rainbow (Ctrl+C stops)
k719 audio --style beat                   # whole keyboard flashes on the beat
k719 audio --style both                   # bars + background flash on the beat
k719 audio -c 00a0ff --gain 1.5           # single color, taller bars
k719 audio --bass 1.5 --treble 0.7        # per-band sensitivity
```

| Option | Meaning |
|---|---|
| `--style` | `spectrum`, `beat` or `both` |
| `-c`, `--color` | bar color (default: rainbow) |
| `--background RRGGBB` | color of unlit keys |
| `--gain` | overall sensitivity: bar height multiplier and beat detection |
| `--bass`, `--mid`, `--treble` | per-band multipliers (<250 Hz, 250 Hz–2 kHz, >2 kHz) |
| `--source` | PulseAudio/PipeWire source (default: the output's monitor) |
| `--fps` | frames per second (default 30) |
| `--no-calibration` | ignore the saved sync calibration |

It listens to the speaker monitor (what the PC plays), never the microphone. When it stops,
the previous lighting effect comes back. It uses the sync calibration saved from the app's
*Audio wave* tab for the current connection (cable or receiver); without one it uses a
built-in estimate.

## `raw`: debugging

```sh
k719 raw 03 0x25      # device info
k719 raw 05 0x31      # config block
k719 -v info          # show every packet
```
