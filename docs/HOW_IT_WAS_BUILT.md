# How this was built

No official Linux software or protocol documentation exists for the K719. This app was built by
reverse engineering Redragon's Windows software and testing every finding on a real keyboard.
No Redragon code or files are included in this repository.

## From the Windows app to a Linux tool

1. **Unpacked the installer.** `K719-RGB-PRO.exe` is an NSIS installer. 7-Zip extracts
   `app.7z`, which holds the real app (a 32-bit C++ program), its skin XML files, JSON
   defaults and two firmware update packages.
2. **Decompiled the app.** Ghidra (headless) decompiled all ~17,000 functions. The calls to
   `WriteFile`, `ReadFile` and `HidD_SetOutputReport` led to one send/receive routine and about
   18 small command functions. Together they give the whole protocol: 64-byte reports with ID 4,
   a 16-bit checksum, and a command byte with length and offset
   (see [PROTOCOL.md](PROTOCOL.md)).
3. **Took the data tables from the app's own files.** Effect IDs came from
   `default_light.json`, key names and positions from `keyboarddevice.xml`, and default key
   codes from `Keyboard.json`.
4. **Checked everything against a real keyboard.** Every command was first tried read-only
   through `/dev/hidraw`, then with writes, restoring the original settings after each test.
   This found things the code alone didn't show:
   - the 8 × 16 key matrix (the Windows app's key list uses a different order),
   - the smaller packets through the 2.4G receiver (24 bytes instead of 56),
   - that the active key mapping can't be read back,
   - the clock and animation fields in the config block,
   - that the firmware's key-press notifications cause typing lag on Linux.
5. **Wrote it in Python** with no dependencies beyond what Ubuntu-family systems ship (GTK 3
   through PyGObject): `k719/device.py` (protocol), `cli.py`, `gui.py`, `audio.py`,
   `image.py`, plus a GNOME Shell extension.
6. **Measured instead of guessing.** Timing problems in the audio wave were solved with
   measurements:
   - a click track played while the keys flashed (end-to-end delay on the cable),
   - the user tapping along to music (which beat people actually feel),
   - tapping along to flashes through the receiver (its hidden packet queue).
7. **Checked the firmware.** Redragon's .NET update tools were decompiled with ILSpy. Firmware
   versions were read from the USB descriptor inside each firmware image and compared with what
   the keyboard and receiver report (see [PROTOCOL.md](PROTOCOL.md#firmware-versions)).

## What's the same and what's new

**Same as the Windows app:** 20 lighting effects with brightness, speed, direction and color;
per-key colors; key remapping; image and GIF upload to the screen (USB cable only); the
audio-wave effect; clock sync.

**New or different on Linux:**
- **Command line:** `k719` does everything from a terminal or script.
- **Better audio wave:**
  - three styles (spectrum bars, beat flash, both),
  - bass / mid / treble sensitivity that applies live,
  - a tempo-following beat tracker, tuned against real tapping,
  - it records the speaker monitor, never the microphone.
- **Tuned for the 2.4G receiver:** only changed keys are sent, packets are paced to the radio's
  real rate, and beat flashes are fired early to hide the delay.
- **GNOME panel icon:** left-click shows the app; right-click opens a menu with audio wave on/off,
  start at login and quit. The icon turns red while the audio wave runs, and it's only shown
  while the app runs.
- **Background mode:** closing the window only hides it; *Start at login* is optional and off
  by default.
- **Typing-lag fix:** an hwdb rule stops Linux from misreading the keyboard's key-press reports
  as a stuck key.

## Not implemented

- Macros (command `0x15`).
- The Windows app's "light & shadow" effect (screen-capture colors).
- Firmware updates: use Redragon's updaters on Windows.
