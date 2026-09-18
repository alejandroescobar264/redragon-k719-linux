#!/bin/sh
# Per-user install from a source checkout (alternative to the .deb package).
# Copies the app to ~/.local, adds the launcher and GNOME extension, and installs the
# udev/hwdb rules system-wide (asks for sudo once).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
PREFIX="$HOME/.local"

mkdir -p "$PREFIX/share/k719" "$PREFIX/bin" "$PREFIX/share/applications"
rm -rf "$PREFIX/share/k719/k719"
cp -r "$HERE/k719" "$PREFIX/share/k719/"
find "$PREFIX/share/k719" -name __pycache__ -prune -exec rm -rf {} +
install -m 755 "$HERE/bin/k719" "$HERE/bin/k719-gui" "$PREFIX/share/k719/"
ln -sf "$PREFIX/share/k719/k719" "$PREFIX/bin/k719"
ln -sf "$PREFIX/share/k719/k719-gui" "$PREFIX/bin/k719-gui"
install -D -m 644 "$HERE/data/com.argentag.K719.svg" \
    "$PREFIX/share/icons/hicolor/scalable/apps/com.argentag.K719.svg"
gtk-update-icon-cache -q -t -f "$PREFIX/share/icons/hicolor" 2>/dev/null || true
sed "s|^Exec=k719-gui|Exec=$PREFIX/bin/k719-gui|" "$HERE/data/com.argentag.K719.desktop" \
    > "$PREFIX/share/applications/com.argentag.K719.desktop"

# GNOME panel icon (left click: app, right click: menu)
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/k719@argentag.com"
mkdir -p "$EXT_DIR"
cp -r "$HERE/gnome-extension/k719@argentag.com/." "$EXT_DIR/"

# Device access for the logged-in user, and the typing-lag fix (see docs/TROUBLESHOOTING.md)
if ! cmp -s "$HERE/data/70-redragon-k719.rules" /etc/udev/rules.d/70-redragon-k719.rules; then
    sudo install -m 644 "$HERE/data/70-redragon-k719.rules" /etc/udev/rules.d/
    sudo udevadm control --reload
    sudo udevadm trigger --subsystem-match=hidraw --action=change
fi
if ! cmp -s "$HERE/data/70-redragon-k719.hwdb" /etc/udev/hwdb.d/70-redragon-k719.hwdb; then
    sudo install -m 644 "$HERE/data/70-redragon-k719.hwdb" /etc/udev/hwdb.d/
    sudo systemd-hwdb update
    sudo udevadm trigger --subsystem-match=input --action=change
fi

echo "The app enables its GNOME panel icon on first launch; it appears after your next login"
echo "(or on X11: Alt+F2, r)."
echo "Installed. Run 'k719-gui' or 'k719 --help' (make sure ~/.local/bin is in PATH)."
