# Changelog

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
