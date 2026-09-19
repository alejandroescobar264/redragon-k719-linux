# Troubleshooting

## "permission denied on /dev/hidrawN"

The udev rule that gives your user access to the keyboard isn't active yet.

- The `.deb` and `install.sh` both install it. Re-plug the keyboard or receiver once afterwards.
- To check that it's there: `ls /usr/lib/udev/rules.d/70-redragon-k719.rules /etc/udev/rules.d/70-redragon-k719.rules`
- To apply it without re-plugging:
  `sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=hidraw --action=change`

## "no Redragon/Evision keyboard found"

`k719 list` should show one line. If it doesn't:

- **Check the USB connection:** `lsusb | grep 320f` should show `320f:511b` (cable) or `320f:511c` (receiver).
- **Check the mode:** a keyboard in Bluetooth mode isn't reachable; switch it to 2.4G or plug in the cable.

## "the keyboard is not responding" through the receiver

The keyboard is asleep. Press any key on it; the app and `k719` wait up to 30 s for it to
wake. If it still doesn't answer, check that the keyboard is switched to 2.4G mode.

## Typing lags after changing a setting

After any configuration command, the keyboard's firmware starts reporting every key press to
the "driver", and Linux misreads those reports as a key that's stuck down. The hwdb rule
installed by the package fixes it permanently. To check that it's active:

```sh
udevadm info /dev/input/by-id/*REDRAGON*-event-if01 | grep -c KEYBOARD_KEY_c05
```

It should print 128. If it prints 0, re-run:

```sh
sudo systemd-hwdb update && sudo udevadm trigger --subsystem-match=input --action=change
```

Until then, re-plugging the keyboard also clears the lag (until the next setting change).
Details: [PROTOCOL.md](PROTOCOL.md#key-press-notifications-the-typing-lag-bug).

## The panel icon doesn't appear

1. **Start the app once:** on its first launch under GNOME it turns the panel icon on.
2. **Restart GNOME Shell** once after installing, since new extensions are only discovered on
   start: log out and back in (on X11 you can press Alt+F2, type `r`, Enter instead).
3. **Keep the app running:** the icon only shows while the app runs. Start **Redragon K719**
   from the app grid, or turn on *Start at login*.
4. **Still missing?** Check it isn't switched off:
   `gnome-extensions info k719@argentag.com` should say `Enabled: Yes`.
   If not, run `gnome-extensions enable k719@argentag.com`.

The extension supports GNOME Shell 45–48. Other desktops can use the app and the `k719`
command; only the panel icon is GNOME-specific.

## Key remaps look wrong in the app

The keyboard can't report its active key mapping, so the app keeps its own record. If you
remapped keys elsewhere (for example with the Windows app), click **Restore defaults**, or run
`k719 keymap --reset`, once so both agree.

## Screen upload fails or isn't allowed

- **Use the cable:** uploads only work with the keyboard on the USB cable, not through the receiver.
- **Wait out the pause:** the first step erases the old animation and can take more than 10 s
  when a large one is stored. The progress bar stays at 0 % during that time.

## Audio wave doesn't react

- **Check that sound is playing** through the default output device. The visualizer follows
  the output that was the default when it started.
- **Check that `parec` is installed** (package `pulseaudio-utils`). It works on PipeWire systems too.
- **Try a different sensitivity:** raise **Sensitivity**, or the Bass / Mid / Treble sliders.

## GNOME shows the microphone icon while the audio wave runs

The visualizer records the speaker **monitor** (a copy of what the PC plays), never the
microphone, but GNOME's privacy indicator counts any recording stream. You can confirm what
is recorded with `pactl list source-outputs`: the source is a `.monitor` of your speakers.

## Audio wave is out of sync with the beat

Run the **Sync calibration** in the *Audio wave* tab:
- **Sound round:** press Space with 16 beeps (pause your music first).
- **Light round:** press Space when the keys from Caps Lock to J flash.

Beat flashes are then fired early by the measured delay. Each round is saved separately, so
you can redo just one: the sound round after changing speakers or headphones, or the light
round for the other connection (it's stored separately for the cable and the receiver).
**Reset** removes the calibration for the current connection.

Over the 2.4G receiver, the keyboard can only receive about 90 small packets per second, so
the app sends only the keys that changed. *Beat flash* is the most accurate style over
wireless. The spectrum bars simply react to the sound, so they can't be shifted and stay
slightly behind. On the cable all styles are in sync.

## Calibration says it couldn't hear the beeps

The sound round listens to the speaker output. Pause other audio, make sure the output isn't
muted, and check that the default output is the device you're listening on.

## Collecting details for a bug report

The app's **About** window (the ⓘ button) shows the installed version and the connected
device's firmware. From a terminal:

```sh
k719 --version
k719 list
k719 -v info 2>&1 | head -40
gnome-shell --version
```
