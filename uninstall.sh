#!/bin/sh
# Removes a per-user install made with install.sh (not the .deb: use `sudo apt remove redragon-k719`).
PREFIX="$HOME/.local"
k719-gui --quit 2>/dev/null || true
rm -rf "$PREFIX/share/k719" "$HOME/.local/share/gnome-shell/extensions/k719@argentag.com"
rm -f "$PREFIX/bin/k719" "$PREFIX/bin/k719-gui" "$PREFIX/share/applications/com.argentag.K719.desktop" \
      "$PREFIX/share/icons/hicolor/scalable/apps/com.argentag.K719.svg" \
      "$HOME/.config/autostart/com.argentag.K719.desktop"
echo "Removed the per-user install. Your key-mapping record in ~/.config/k719 was kept."
echo "To also remove the system rules: sudo rm /etc/udev/rules.d/70-redragon-k719.rules /etc/udev/hwdb.d/70-redragon-k719.hwdb && sudo systemd-hwdb update"
