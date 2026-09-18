#!/bin/sh
# Builds dist/redragon-k719_<version>_all.deb from this source tree.
# Needs only dpkg-deb (part of dpkg). Usage: packaging/build-deb.sh
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PKG=redragon-k719
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/k719/__init__.py")
MAINTAINER="Alejandro Escobar <alejandroescobar264@gmail.com>"
STAGE="$ROOT/build/${PKG}_${VERSION}_all"
OUT="$ROOT/dist"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$OUT"

# app code
install -d "$STAGE/usr/share/$PKG/k719"
install -m 644 "$ROOT"/k719/*.py "$STAGE/usr/share/$PKG/k719/"
install -d "$STAGE/usr/bin"
install -m 755 "$ROOT/bin/k719" "$ROOT/bin/k719-gui" "$STAGE/usr/bin/"

# desktop entry, udev access rule, hwdb typing-lag fix
install -D -m 644 "$ROOT/data/com.argentag.K719.desktop" \
    "$STAGE/usr/share/applications/com.argentag.K719.desktop"
install -D -m 644 "$ROOT/data/com.argentag.K719.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/com.argentag.K719.svg"
install -D -m 644 "$ROOT/data/70-redragon-k719.rules" \
    "$STAGE/usr/lib/udev/rules.d/70-redragon-k719.rules"
install -D -m 644 "$ROOT/data/70-redragon-k719.hwdb" \
    "$STAGE/usr/lib/udev/hwdb.d/70-redragon-k719.hwdb"

# GNOME Shell extension (system-wide; each user enables it once)
EXT="$STAGE/usr/share/gnome-shell/extensions/k719@argentag.com"
install -d "$EXT/icons"
install -m 644 "$ROOT/gnome-extension/k719@argentag.com/extension.js" \
    "$ROOT/gnome-extension/k719@argentag.com/metadata.json" "$EXT/"
install -m 644 "$ROOT/gnome-extension/k719@argentag.com/icons/"*.svg "$EXT/icons/"

# docs
DOC="$STAGE/usr/share/doc/$PKG"
install -d "$DOC"
install -m 644 "$ROOT/README.md" "$DOC/"
install -m 644 "$ROOT"/docs/*.md "$DOC/"
gzip -9n -c "$ROOT/CHANGELOG.md" > "$DOC/changelog.gz"
cat > "$DOC/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: redragon-k719-linux
Source: https://github.com/alejandroescobar264/redragon-k719-linux

Files: *
Copyright: $(date +%Y) Alejandro Escobar
License: GPL-3.0-or-later
 On Debian systems the full license text is in /usr/share/common-licenses/GPL-3.
EOF

# normalize modes regardless of the builder's umask
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/usr/bin/k719" "$STAGE/usr/bin/k719-gui"

SIZE=$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-gi, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0, pulseaudio-utils, udev
Recommends: gnome-shell
Installed-Size: $SIZE
Maintainer: $MAINTAINER
Homepage: https://github.com/alejandroescobar264/redragon-k719-linux
Description: Linux app for the Redragon K719 keyboard
 Unofficial replacement for the Windows K719 software: RGB lighting effects,
 per-key colors, key remapping, images and GIFs on the built-in screen, clock
 sync and a music visualizer (audio wave). Works over the USB cable and the
 2.4G receiver. Includes a GTK app, the k719 command-line tool, a GNOME Shell
 panel icon, a udev rule for device access and an hwdb rule that fixes the
 typing lag caused by the firmware's key notifications.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    systemd-hwdb update 2>/dev/null || true
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
    udevadm control --reload 2>/dev/null || true
    udevadm trigger --subsystem-match=hidraw --action=change 2>/dev/null || true
    udevadm trigger --subsystem-match=input --action=change 2>/dev/null || true
    echo "redragon-k719: re-plug the keyboard/receiver if the app can't open it."
    echo "redragon-k719: open 'Redragon K719' once; its GNOME panel icon appears after your next login."
fi
exit 0
EOF
cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    systemd-hwdb update 2>/dev/null || true
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
    udevadm control --reload 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

dpkg-deb --root-owner-group --build "$STAGE" "$OUT/${PKG}_${VERSION}_all.deb"
echo "Built $OUT/${PKG}_${VERSION}_all.deb"
