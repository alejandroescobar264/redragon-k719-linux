# K719 USB protocol

Everything here was reverse engineered from Redragon's Windows app (`K719-RGB-PRO.exe`) and then
checked against a real keyboard. See [HOW_IT_WAS_BUILT.md](HOW_IT_WAS_BUILT.md) for the method.
The keyboard is built on an Evision controller (VS11K53A). Other Evision-based Redragon boards
use a similar protocol, but the details below were only verified on the K719.

## Devices

| USB ID | What | Vendor interface |
|---|---|---|
| `320f:511b` | Keyboard on the USB cable | interface 1 → hidraw |
| `320f:511c` | 2.4G receiver | interface 1 → hidraw |

The vendor interface is the one whose report descriptor contains usage page `0xFF1C` with
report ID 4. On Linux it appears as a `/dev/hidraw*` node, which `data/70-redragon-k719.rules`
opens to the logged-in user.

## Packet format

Every request is a 64-byte output report:

| Byte | Meaning |
|---|---|
| 0 | `0x04` (report ID) |
| 1–2 | checksum: sum of bytes 3–63, little-endian |
| 3 | command |
| 4 | payload length in this packet |
| 5–6 | offset, little-endian (the screen upload also uses byte 7 → 24-bit offset) |
| 7 | 0 in requests; status in replies |
| 8… | payload |

The keyboard answers each request with a 64-byte input report that echoes the header.

- **Errors:** reply byte 7 = `0xFE`/`0xFF` means an error.
- **Keyboard offline:** through the receiver, a reply whose command byte is `0xFF` means the
  keyboard is asleep or out of range.
- **Payload size:** up to `0x38` bytes fit per packet on the cable, and only `0x18` through the receiver.

## Commands

| Cmd | Direction | Meaning |
|---|---|---|
| `01` / `02` | – | Begin / end (commit) a write session. |
| `03` | read | Device info, 0x25 bytes (see below). |
| `05` / `06` | read / write | Config block at offset 0 (see below). |
| `07` | read | **Factory** key map (the active map can't be read back). |
| `09` | write | Key map: 128 slots × 3 bytes. |
| `0A` / `0B` | read / write | Per-key colors for the *Custom* effect: RGB per matrix slot. |
| `12` | write | Stream per-key colors without saving (effect must be `0xFE`). |
| `15` | write | Macros (not implemented). |
| `1B` | read | LED index per matrix slot (identity on the K719). |
| `21` | write | Screen image data (24-bit offset). |
| `23` | – | Start a screen upload: erases the stored animation (can take >10 s). |
| `AA` | read | Receiver link status: reply byte 8 = `0xFF` → keyboard connected. |

### Device info (`03`)

| Byte | Meaning |
|---|---|
| 5 | Number of matrix slots (128) |
| 0x1F, 0x20 | Screen width, height (240 × 135) |
| 0x23 | Maximum animation frames (90; the Windows app allows 80) |

### Config block (`05`/`06`, 0x31 bytes)

| Offset | Meaning |
|---|---|
| 0 | Active profile |
| 1 | Effect ID (see below); `0xFE` = PC-driven (used while streaming with `12`) |
| 2 | Brightness 0–5 |
| 3 | Speed, stored as `5 − speed` |
| 4 | Direction |
| 5 | Multicolor flag (0 = single color) |
| 6–8 | RGB color |
| 0x22 | Number of frames stored for the screen animation |
| 0x23–0x29 | Clock, BCD: second, minute, hour, weekday (0 = Sunday), day, month, year % 100 |
| 0x2B–0x2C | Milliseconds per animation frame, little-endian |

Effect IDs: 1 static, 2 breath, 3 spectrum, 4 traverse, 5 rain, 6 ripples, 7 stars, 8 reaction,
9 stream, 10 corrugated, 11 cartoon, 12 wave, 13 serpentine, 14 roll, 15 flowers, 16 scan,
17 surmount, 18 speed, 19 custom, 20 off.

Writing the config block is also how the clock is set: the Windows app writes the PC's time
into it every time it saves settings.

## Key matrix and key map

The firmware uses an 8 × 16 matrix (128 slots); the LED index equals the slot.
Slot numbers for every key are in `k719/layout.py`. They differ from the key order in the
Windows app's own key list.

Each key-map entry is 3 bytes:

| Bytes | Meaning |
|---|---|
| `20 mm uu` | Keyboard key: `mm` = modifier bits (lctrl 01, lshift 02, lalt 04, lgui 08, rctrl 10, rshift 20, ralt 40, rgui 80), `uu` = HID usage |
| `20 00 00` | Disabled |
| `A0 01 00` | Fn |
| `A0 xx 00` | Other special functions (knob, media) |
| `D0 A2 0n` | Macro key n |

## Screen upload

1. Write the config block with the frame count, frame interval and clock (`06`).
2. `01`, then `23` (erases; wait for the reply).
3. Send the image data with `21`, then `02`.

Frames are 240 × 135 RGB565, big-endian (`RRRRRGGG GGGBBBBB`), each padded to a multiple of
32 KiB, sent back to back. After the first data packet the Windows app waits 500 ms.
Uploads work only on the cable: at the receiver's rate one frame would take about 30 s.
An 80-frame animation takes about 3.5 minutes on the cable.

## Streaming colors (`12`) and the 2.4G receiver

- **Partial updates:** the keyboard applies partial `12` updates, so only changed packets need to be sent.
- **Rate limit:** frames sent faster than about 30 per second are dropped.
- **No pipelining:** the receiver drops packets when more than one is in flight.
- **Hidden queue:** the receiver acknowledges each packet after ~6 ms but only delivers one
  to the keyboard every ~11 ms, and extra packets wait in a queue. Measured by tapping along:
  a 1-packet flash lights up ~45 ms late, a 14-packet full-keyboard flash ~190 ms late.
  `k719/device.py` therefore paces packets to 11 ms and caps packets per frame over the receiver.

## Key-press notifications (the typing-lag bug)

After any configuration command, the firmware also reports every key press and release on
interface 1 as report ID 3 with a 16-bit value `0x05ss` (press) / `0x06ss` (release),
`ss` = matrix slot. The Windows app uses these for its effects. On Linux, `hid-generic` maps
them to a `KEY_UNKNOWN` that is never released, so it auto-repeats and floods the desktop.
`data/70-redragon-k719.hwdb` maps scancodes `c0500`–`c067f` to `reserved`, which drops them.
Re-plugging the keyboard also stops the notifications until the next configuration command.

## Firmware versions

The Windows updaters read the firmware version from the USB device version (`bcdDevice`).
The same value is in the USB descriptor inside each firmware image.

| Package | Version |
|---|---|
| Keyboard, bundled with the app (2024-11) | 2.05 |
| Keyboard, "Keyboard version update.12H24H" (2025-05) | 2.08 |
| Receiver, bundled with the app (2024-09) | 1.04 |
| Receiver, "Dongle Update" (2025-05) | 1.05 |

This project was developed and tested with keyboard firmware 1.03 and receiver 1.07.
