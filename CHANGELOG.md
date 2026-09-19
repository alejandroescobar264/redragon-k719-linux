# Changelog

## 1.1.0 — 2026-09-18

### New
- **Audio wave tab:** the visualizer has its own tab, with the start/stop button, style,
  colors and the four sensitivity sliders. The Lighting tab now holds only the lighting
  settings.
- **Sync calibration:** a guided test in the Audio wave tab measures how late the keyboard's
  lights appear, so beat flashes land on the beat.
  - *Sound round:* press Space with 16 beeps. It captures your timing and your speakers' delay.
  - *Light round:* press Space when the keys from Caps Lock to J flash.
  - Each round is saved on its own and can be redone alone. The light round is kept
    separately for the USB cable and the 2.4G receiver.
  - Bad rounds (too few or too irregular presses) are rejected with a clear message.
    **Reset** returns to the built-in estimate.
- `k719 audio` uses the saved calibration too; `--no-calibration` ignores it.
- **About window:** opened with the ⓘ button in the app or from the panel menu. It shows the
  installed version, a short description, the connected keyboard or receiver's firmware
  version, the project page and the license.

### Fixed
- Beat flashes over the 2.4G receiver could arrive up to ~80 ms late every few seconds,
  when a routine refresh of unchanged keys was sent ahead of them. Changed keys now always
  go out first.

## 1.0.0 — 2026-09-18

First public release.

- GTK app: lighting effects, per-key colors, key remapping, screen image/GIF upload, clock sync.
- `k719` command-line tool with the same features.
- Audio wave visualizer: spectrum bars, beat flash (tempo tracking) and both combined, with
  bass/mid/treble sensitivity. Records the speaker monitor, never the microphone.
- Tuned for the 2.4G receiver: paced, prioritized updates and beat flashes fired early.
- GNOME Shell panel icon with a menu (show app, audio wave, start at login, quit).
- Background mode with optional start at login.
- udev rule for device access and an hwdb rule that fixes the typing lag caused by the
  firmware's key notifications.
- `.deb` package and a per-user `install.sh`.
- App icon: the panel icon's dragon on a dark tile, used by the launcher, dock and window.
