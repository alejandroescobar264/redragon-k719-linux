"""Things the keyboard can't store or report, kept in ~/.config/k719.

- keymap.bin: the firmware has no command to read back the active key mapping (command 0x07
  returns the factory table), so - like the Windows app - we remember what we wrote.
- settings.json: app settings such as the audio-wave sync calibration.
"""

import json
import os

STATE_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                         "k719")
KEYMAP_FILE = os.path.join(STATE_DIR, "keymap.bin")
SETTINGS_FILE = os.path.join(STATE_DIR, "settings.json")


def load_keymap(num_keys):
    try:
        with open(KEYMAP_FILE, "rb") as f:
            d = f.read()
    except OSError:
        return None
    if len(d) != num_keys * 3:
        return None
    return [d[i * 3:i * 3 + 3] for i in range(num_keys)]


def save_keymap(entries):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(KEYMAP_FILE, "wb") as f:
        f.write(b"".join(bytes(e) for e in entries))


def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
    os.replace(tmp, SETTINGS_FILE)


def connection_name(kb):
    return "receiver" if kb.wireless else "cable"


def _calibration():
    cal = load_settings().get("calibration")
    return cal if isinstance(cal, dict) else {}


def get_calibration(kb):
    """(sound offset, light offset for this connection) in seconds; either may be None.

    The sound offset is how far the user's presses land from a beep (anticipation plus the
    speaker delay); the light offset is the same for a single-packet flash over this
    connection. Their difference is the light delay."""
    cal = _calibration()
    sound = cal.get("sound_offset_s")
    light = cal.get("light_offset_s", {}).get(connection_name(kb))
    ok = (int, float)
    return (float(sound) if isinstance(sound, ok) else None,
            float(light) if isinstance(light, ok) else None)


def set_calibration(kb, sound=None, light=None, forget=False):
    """Save one round's result (sound, or light for this connection); forget=True clears both
    rounds for this connection."""
    settings = load_settings()
    cal = settings.setdefault("calibration", {})
    lights = cal.setdefault("light_offset_s", {})
    if forget:
        lights.pop(connection_name(kb), None)
        if not lights:
            cal.pop("sound_offset_s", None)
    if sound is not None:
        cal["sound_offset_s"] = round(float(sound), 4)
    if light is not None:
        lights[connection_name(kb)] = round(float(light), 4)
    settings.pop("light_delay_s", None)  # format used by an earlier build
    save_settings(settings)


def get_light_delay(kb):
    """Calibrated delay (s) until a single-packet flash is seen over this connection, or None
    if either round is missing."""
    sound, light = get_calibration(kb)
    if sound is None or light is None:
        return None
    return light - sound
