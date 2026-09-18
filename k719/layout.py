"""Static tables for the Redragon K719, extracted from the Windows app
(Skin/XML/DeviceXml/keyboarddevice.xml, DefaultData/Keyboard.json and
DefaultData/default_light.json)."""

# Lighting effect id -> name (firmware ids from default_light.json; names from lan_en.xml).
# Ids 21/22 in the Windows app are PC-driven effects (audio / screen capture), not firmware modes.
MODES = {
    1: "static",
    2: "breath",
    3: "spectrum",
    4: "traverse",
    5: "rain",
    6: "ripples",
    7: "stars",
    8: "reaction",
    9: "stream",
    10: "corrugated",
    11: "cartoon",
    12: "wave",
    13: "serpentine",
    14: "roll",
    15: "flowers",
    16: "scan",
    17: "surmount",
    18: "speed",
    19: "custom",
    20: "off",
}
MODE_IDS = {v: k for k, v in MODES.items()}
MODE_CUSTOM = 19

# HID keyboard usage -> short name.
HID_NAMES = {
    0x00: "none",
    **{0x04 + i: chr(ord("a") + i) for i in range(26)},
    **{0x1E + i: str((i + 1) % 10) for i in range(10)},
    0x28: "enter", 0x29: "esc", 0x2A: "backspace", 0x2B: "tab", 0x2C: "space",
    0x2D: "minus", 0x2E: "equal", 0x2F: "leftbracket", 0x30: "rightbracket",
    0x31: "backslash", 0x32: "nonus_hash", 0x33: "semicolon", 0x34: "apostrophe",
    0x35: "grave", 0x36: "comma", 0x37: "period", 0x38: "slash", 0x39: "capslock",
    **{0x3A + i: f"f{i + 1}" for i in range(12)},
    0x46: "printscreen", 0x47: "scrolllock", 0x48: "pause", 0x49: "insert",
    0x4A: "home", 0x4B: "pageup", 0x4C: "delete", 0x4D: "end", 0x4E: "pagedown",
    0x4F: "right", 0x50: "left", 0x51: "down", 0x52: "up", 0x53: "numlock",
    0x54: "kp_slash", 0x55: "kp_asterisk", 0x56: "kp_minus", 0x57: "kp_plus",
    0x58: "kp_enter",
    **{0x59 + i: f"kp_{(i + 1) % 10}" for i in range(10)},
    0x63: "kp_period", 0x64: "nonus_backslash", 0x65: "menu",
    **{0x68 + i: f"f{13 + i}" for i in range(12)},
    0x87: "ro",
}
HID_CODES = {v: k for k, v in HID_NAMES.items()}

# Modifier bits in byte 1 of a keyboard (type 0x20) mapping.
MODIFIERS = {
    "lctrl": 0x01, "lshift": 0x02, "lalt": 0x04, "lgui": 0x08,
    "rctrl": 0x10, "rshift": 0x20, "ralt": 0x40, "rgui": 0x80,
}

# (matrix slot, x, y, width, height, default mapping, label)
# The firmware uses an 8x16 matrix (128 slots); the per-key LED index equals the slot.
# x/y/width/height are the key rectangles from the Windows skin (pixels).
KEYS = [
    (0, 59, 19, 30, 29, 0x200029, 'Esc'),
    (1, 95, 19, 29, 29, 0x20003A, 'F1'),
    (2, 126, 19, 27, 29, 0x20003B, 'F2'),
    (3, 154, 19, 27, 29, 0x20003C, 'F3'),
    (4, 182, 19, 29, 29, 0x20003D, 'F4'),
    (5, 216, 19, 28, 29, 0x20003E, 'F5'),
    (6, 246, 19, 26, 29, 0x20003F, 'F6'),
    (7, 274, 19, 27, 29, 0x200040, 'F7'),
    (8, 302, 19, 27, 29, 0x200041, 'F8'),
    (9, 335, 19, 29, 29, 0x200042, 'F9'),
    (10, 366, 19, 27, 29, 0x200043, 'F10'),
    (11, 394, 19, 27, 29, 0x200044, 'F11'),
    (12, 422, 19, 29, 29, 0x200045, 'F12'),
    (13, 456, 19, 29, 29, 0x20004C, 'Del'),
    (16, 59, 56, 30, 27, 0x200035, '`'),
    (17, 90, 56, 27, 27, 0x20001E, '1'),
    (18, 118, 56, 27, 27, 0x20001F, '2'),
    (19, 147, 56, 26, 27, 0x200020, '3'),
    (20, 175, 56, 27, 27, 0x200021, '4'),
    (21, 203, 56, 27, 27, 0x200022, '5'),
    (22, 231, 56, 27, 27, 0x200023, '6'),
    (23, 260, 56, 27, 27, 0x200024, '7'),
    (24, 288, 56, 27, 27, 0x200025, '8'),
    (25, 316, 56, 27, 27, 0x200026, '9'),
    (26, 344, 56, 27, 27, 0x200027, '0'),
    (27, 373, 56, 26, 27, 0x20002D, '-'),
    (28, 401, 56, 27, 27, 0x20002E, '='),
    (29, 429, 56, 56, 27, 0x20002A, 'Bksp'),
    (96, 498, 56, 28, 27, 0x200053, 'Num'),
    (97, 527, 56, 27, 27, 0x200054, '/'),
    (98, 555, 56, 28, 27, 0x200055, '*'),
    (99, 584, 56, 27, 27, 0x200056, '-'),
    (32, 59, 84, 44, 28, 0x20002B, 'Tab'),
    (33, 104, 84, 27, 28, 0x200014, 'Q'),
    (34, 133, 84, 27, 28, 0x20001A, 'W'),
    (35, 161, 84, 27, 28, 0x200008, 'E'),
    (36, 189, 84, 27, 28, 0x200015, 'R'),
    (37, 217, 84, 27, 28, 0x200017, 'T'),
    (38, 246, 84, 26, 28, 0x20001C, 'Y'),
    (39, 274, 84, 27, 28, 0x200018, 'U'),
    (40, 302, 84, 27, 28, 0x20000C, 'I'),
    (41, 330, 84, 27, 28, 0x200012, 'O'),
    (42, 358, 84, 27, 28, 0x200013, 'P'),
    (43, 387, 84, 26, 28, 0x20002F, '['),
    (44, 415, 84, 27, 28, 0x200030, ']'),
    (45, 443, 84, 42, 28, 0x200031, '\\'),
    (100, 498, 84, 28, 28, 0x20005F, '7'),
    (101, 527, 84, 27, 28, 0x200060, '8'),
    (102, 555, 84, 28, 28, 0x200061, '9'),
    (106, 584, 84, 27, 56, 0x200057, '+'),
    (48, 59, 113, 51, 27, 0x200039, 'Caps'),
    (49, 111, 113, 28, 27, 0x200004, 'A'),
    (50, 140, 113, 27, 27, 0x200016, 'S'),
    (51, 168, 113, 27, 27, 0x200007, 'D'),
    (52, 196, 113, 27, 27, 0x200009, 'F'),
    (53, 224, 113, 28, 27, 0x20000A, 'G'),
    (54, 253, 113, 27, 27, 0x20000B, 'H'),
    (55, 281, 113, 27, 27, 0x20000D, 'J'),
    (56, 309, 113, 27, 27, 0x20000E, 'K'),
    (57, 337, 113, 27, 27, 0x20000F, 'L'),
    (58, 366, 113, 26, 27, 0x200033, ';'),
    (59, 394, 113, 27, 27, 0x200034, "'"),
    (61, 422, 113, 63, 27, 0x200028, 'Enter'),
    (103, 498, 113, 28, 27, 0x20005C, '4'),
    (104, 527, 113, 27, 27, 0x20005D, '5'),
    (105, 555, 113, 28, 27, 0x20005E, '6'),
    (64, 59, 141, 65, 27, 0x200200, 'Shift'),
    (66, 126, 141, 26, 27, 0x20001D, 'Z'),
    (67, 154, 141, 27, 27, 0x20001B, 'X'),
    (68, 182, 141, 27, 27, 0x200006, 'C'),
    (69, 210, 141, 27, 27, 0x200019, 'V'),
    (70, 238, 141, 27, 27, 0x200005, 'B'),
    (71, 267, 141, 27, 27, 0x200011, 'N'),
    (72, 295, 141, 27, 27, 0x200010, 'M'),
    (73, 323, 141, 27, 27, 0x200036, ','),
    (74, 351, 141, 27, 27, 0x200037, '.'),
    (75, 380, 141, 26, 27, 0x200038, '/'),
    (77, 408, 141, 48, 27, 0x202000, 'Shift'),
    (78, 464, 147, 27, 26, 0x200052, '↑'),
    (79, 498, 141, 28, 27, 0x200059, '1'),
    (107, 527, 141, 27, 27, 0x20005A, '2'),
    (108, 555, 141, 28, 27, 0x20005B, '3'),
    (111, 584, 141, 27, 56, 0x200058, 'Ent'),
    (80, 59, 169, 37, 28, 0x200100, 'Ctrl'),
    (81, 97, 169, 34, 28, 0x200800, 'Win'),
    (82, 132, 169, 35, 28, 0x200400, 'Alt'),
    (85, 168, 169, 175, 28, 0x20002C, ''),
    (89, 344, 170, 27, 27, 0x204000, 'Alt'),
    (90, 372, 169, 27, 28, 0xA00100, 'Fn'),
    (92, 400, 169, 28, 28, 0x201000, 'Ctrl'),
    (93, 435, 176, 28, 27, 0x200050, '←'),
    (94, 464, 176, 27, 27, 0x200051, '↓'),
    (95, 492, 176, 27, 27, 0x20004F, '→'),
    (109, 527, 170, 27, 27, 0x200062, '0'),
    (110, 555, 169, 28, 28, 0x200063, '.'),
]

KEY_BY_INDEX = {k[0]: k for k in KEYS}


def key_name(index):
    """Stable command-line name for a matrix slot, derived from its default HID code."""
    k = KEY_BY_INDEX.get(index)
    if k is None:
        return f"#{index}"
    code = k[5]
    if code >> 16 == 0x20 and code & 0xFF:
        name = HID_NAMES.get(code & 0xFF, f"#{index}")
        return name
    if code == 0xA00100:
        return "fn"
    mods = (code >> 8) & 0xFF
    for n, bit in MODIFIERS.items():
        if code >> 16 == 0x20 and mods == bit:
            return n
    return f"#{index}"


KEY_NAMES = {key_name(k[0]): k[0] for k in KEYS}


def resolve_key(name):
    """Accept a key name (e.g. 'a', 'f5', 'lctrl', 'kp_1') or '#<matrix index>'."""
    name = name.strip().lower()
    if name.startswith("#"):
        return int(name[1:], 0)
    if name in KEY_NAMES:
        return KEY_NAMES[name]
    raise KeyError(f"unknown key '{name}' (see `k719 keys`)")


def encode_action(spec):
    """Turn 'ctrl+c', 'f13', 'none', 'disable' or 'raw:200029' into a 3-byte mapping."""
    spec = spec.strip().lower()
    if spec.startswith("raw:"):
        v = int(spec[4:], 16)
        return bytes([(v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])
    if spec in ("none", "disable", "disabled"):
        return bytes([0x20, 0x00, 0x00])
    mods = 0
    code = 0
    aliases = {"ctrl": "lctrl", "shift": "lshift", "alt": "lalt", "win": "lgui",
               "super": "lgui", "gui": "lgui", "meta": "lgui"}
    for part in spec.split("+"):
        part = aliases.get(part, part)
        if part in MODIFIERS:
            mods |= MODIFIERS[part]
        elif part in HID_CODES:
            if code:
                raise ValueError("only one non-modifier key per mapping")
            code = HID_CODES[part]
        else:
            raise ValueError(f"unknown key '{part}'")
    return bytes([0x20, mods, code])


def describe_action(b):
    t, m, c = b[0], b[1], b[2]
    if t == 0x20:
        parts = [n for n, bit in MODIFIERS.items() if m & bit]
        if c:
            parts.append(HID_NAMES.get(c, f"0x{c:02x}"))
        return "+".join(parts) if parts else "disabled"
    if t == 0xA0 and m == 0x01 and c == 0:
        return "fn"
    return f"raw:{t:02x}{m:02x}{c:02x}"


# Factory keymap as read from a stock K719 (128 slots x 3 bytes), used by `keymap --reset`.
FACTORY_KEYMAP = bytes.fromhex(
    "20002920003a20003b20003c20003d20003e20003f200040"
    "20004120004220004320004420004520004c200000200000"
    "20003520001e20001f200020200021200022200023200024"
    "20002520002620002720002d20002e20002a200000200000"
    "20002b20001420001a20000820001520001720001c200018"
    "20000c20001220001320002f200030200031200000200000"
    "20003920000420001620000720000920000a20000b20000d"
    "20000e20000f200033200034200032200028200000200000"
    "20020020006420001d20001b200006200019200005200011"
    "200010200036200037200038200087202000200052200059"
    "20010020080020040020000020000020002c200000200000"
    "a02a00204000a0010020006520100020005020005120004f"
    "20005320005420005520005620005f20006020006120005c"
    "20005d20005e20005720005a20005b200062200063200058"
    "a01700a01600a00000200000200000200000200000200000"
    "200000200000200000200000200000000000000000000000"
)
