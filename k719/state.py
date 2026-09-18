"""The firmware has no command to read back the active key mapping (command 0x07
returns the factory table), so - like the Windows app - we remember what we wrote."""

import os

STATE_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                         "k719")
KEYMAP_FILE = os.path.join(STATE_DIR, "keymap.bin")


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
