"""GTK3 front end for the Redragon K719."""

import glob
import os
import shutil
import sys
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import __version__, calibration, layout, state  # noqa: E402
from .device import K719, K719Error  # noqa: E402

SCALE = 1.35
X0, Y0 = 59, 19

REPO_URL = "https://github.com/alejandroescobar264/redragon-k719-linux"


def connected_firmware():
    """Firmware versions of the connected K719 devices, read from their USB descriptors
    (the same number Redragon's updaters show), e.g. ["keyboard (USB cable), firmware 1.03"]."""
    names = {"511b": "keyboard (USB cable)", "511c": "2.4G receiver"}
    found = []
    for dev in sorted(glob.glob("/sys/bus/usb/devices/*")):
        try:
            with open(os.path.join(dev, "idVendor")) as f:
                if f.read().strip() != "320f":
                    continue
            with open(os.path.join(dev, "idProduct")) as f:
                pid = f.read().strip()
            with open(os.path.join(dev, "bcdDevice")) as f:
                bcd = f.read().strip()
        except OSError:
            continue
        found.append(f"{names.get(pid, 'device ' + pid)}, firmware {int(bcd[:2], 16)}.{bcd[2:]}")
    return found


AUTOSTART_FILE = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "autostart", "com.argentag.K719.desktop")


EXTENSION_UUID = "k719@argentag.com"


def enable_panel_icon_once():
    """On the first launch under GNOME, enable the panel-icon extension (it ships disabled, like
    every GNOME extension). Done only once, so a user who turns it off later isn't overridden.
    GNOME shows a newly installed extension after the next login (or Alt+F2, r on X11)."""
    flag = os.path.join(state.STATE_DIR, "panel-icon-enabled")
    if os.path.exists(flag) or "GNOME" not in os.environ.get("XDG_CURRENT_DESKTOP", ""):
        return
    source = Gio.SettingsSchemaSource.get_default()
    if not source or not source.lookup("org.gnome.shell", True):
        return
    settings = Gio.Settings.new("org.gnome.shell")
    enabled = list(settings.get_strv("enabled-extensions"))
    if EXTENSION_UUID not in enabled:
        settings.set_strv("enabled-extensions", enabled + [EXTENSION_UUID])
    disabled = list(settings.get_strv("disabled-extensions"))
    if EXTENSION_UUID in disabled:
        settings.set_strv("disabled-extensions", [u for u in disabled if u != EXTENSION_UUID])
    Gio.Settings.sync()
    os.makedirs(state.STATE_DIR, exist_ok=True)
    open(flag, "w").close()


def autostart_enabled():
    return os.path.exists(AUTOSTART_FILE)


def set_autostart(on):
    """Create or remove the login entry that starts the app hidden in the background."""
    if not on:
        if os.path.exists(AUTOSTART_FILE):
            os.remove(AUTOSTART_FILE)
        return
    launcher = shutil.which("k719-gui") or os.path.realpath(sys.argv[0])
    os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
    with open(AUTOSTART_FILE, "w") as f:
        f.write("[Desktop Entry]\nType=Application\nName=Redragon K719 (background)\n"
                f"Exec={launcher} --background\nIcon=com.argentag.K719\n"
                "X-GNOME-Autostart-enabled=true\nNoDisplay=true\n")


def rgb_to_gdk(c):
    r = Gdk.RGBA()
    r.red, r.green, r.blue, r.alpha = c[0] / 255, c[1] / 255, c[2] / 255, 1
    return r


def gdk_to_rgb(g):
    return (round(g.red * 255), round(g.green * 255), round(g.blue * 255))


class KeyboardView(Gtk.DrawingArea):
    """Clickable drawing of the K719 key layout."""

    def __init__(self, on_select):
        super().__init__()
        self.colors = {}
        self.labels = {}
        self.selected = set()
        self.on_select = on_select
        w = max(k[1] + k[3] for k in layout.KEYS) - X0
        h = max(k[2] + k[4] for k in layout.KEYS) - Y0
        self.set_size_request(int(w * SCALE) + 20, int(h * SCALE) + 20)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._click)

    def _rect(self, k):
        return (10 + (k[1] - X0) * SCALE, 10 + (k[2] - Y0) * SCALE,
                k[3] * SCALE - 2, k[4] * SCALE - 2)

    def _draw(self, _w, cr):
        cr.set_source_rgb(0.12, 0.12, 0.13)
        cr.paint()
        for k in layout.KEYS:
            x, y, w, h = self._rect(k)
            c = self.colors.get(k[0], (40, 40, 40))
            cr.set_source_rgb(c[0] / 255, c[1] / 255, c[2] / 255)
            cr.rectangle(x, y, w, h)
            cr.fill()
            if k[0] in self.selected:
                cr.set_source_rgb(1, 1, 1)
                cr.set_line_width(3)
            else:
                cr.set_source_rgb(0, 0, 0)
                cr.set_line_width(1)
            cr.rectangle(x, y, w, h)
            cr.stroke()
            label = self.labels.get(k[0], k[6])
            lum = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
            cr.set_source_rgb(*((0, 0, 0) if lum > 140 else (1, 1, 1)))
            cr.select_font_face("DejaVu Sans")
            cr.set_font_size(10 if len(label) < 6 else 8)
            while cr.text_extents(label).width > w - 4 and len(label) > 1:
                label = label[:-1]
            ext = cr.text_extents(label)
            cr.move_to(x + (w - ext.width) / 2 - ext.x_bearing, y + h / 2 + ext.height / 2)
            cr.show_text(label)

    def _click(self, _w, ev):
        hit = None
        for k in layout.KEYS:
            x, y, w, h = self._rect(k)
            if x <= ev.x <= x + w and y <= ev.y <= y + h:
                hit = k[0]
        if hit is None:
            if not ev.state & Gdk.ModifierType.CONTROL_MASK:
                self.selected.clear()
        elif ev.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK):
            self.selected ^= {hit}
        else:
            self.selected = {hit}
        self.queue_draw()
        self.on_select(self.selected)


class App(Gtk.ApplicationWindow):
    def __init__(self, application=None):
        super().__init__(application=application, title="Redragon K719")
        self.set_border_width(10)
        # installed icon (hicolor theme), else the SVG in a source checkout, else a stock icon
        src_icon = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "data", "com.argentag.K719.svg")
        if Gtk.IconTheme.get_default().has_icon("com.argentag.K719"):
            self.set_icon_name("com.argentag.K719")
        elif os.path.exists(src_icon):
            self.set_icon_from_file(src_icon)
        else:
            self.set_icon_name("input-keyboard")
        self.kb = None
        self.busy = False
        self.custom = [(0, 0, 0)] * 128
        self.keymap = None
        self.audio_stop = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(root)

        top = Gtk.Box(spacing=8)
        self.status = Gtk.Label(label="Not connected", xalign=0)
        reconnect = Gtk.Button(label="Connect / Refresh")
        reconnect.connect("clicked", lambda *_: self.connect_device())
        self.autostart_check = Gtk.CheckButton(label="Start at login",
                                               active=autostart_enabled())
        self.autostart_check.set_tooltip_text(
            "Start hidden in the background when you log in, so the panel icon can "
            "toggle the audio wave right away")
        self.autostart_check.connect("toggled", self._autostart_toggled)
        top.pack_start(self.status, True, True, 0)
        top.pack_start(self.autostart_check, False, False, 0)
        top.pack_start(reconnect, False, False, 0)
        about = Gtk.Button.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON)
        about.set_tooltip_text("About Redragon K719")
        about.connect("clicked", lambda *_: self.show_about())
        top.pack_start(about, False, False, 0)
        root.pack_start(top, False, False, 0)

        nb = Gtk.Notebook()
        root.pack_start(nb, True, True, 0)
        nb.append_page(self._light_page(), Gtk.Label(label="Lighting"))
        nb.append_page(self._audio_page(), Gtk.Label(label="Audio wave"))
        nb.append_page(self._custom_page(), Gtk.Label(label="Per-key colors"))
        nb.append_page(self._keymap_page(), Gtk.Label(label="Key mapping"))
        nb.append_page(self._screen_page(), Gtk.Label(label="Screen"))

        # Closing the window only hides it; the app keeps running in the background so the
        # panel icon can bring it back or toggle the audio wave.
        self.connect("delete-event", lambda *_: self.hide() or True)
        GLib.idle_add(self.connect_device)

    def _autostart_toggled(self, check):
        try:
            set_autostart(check.get_active())
        except OSError as e:
            self.set_status(f"Error: {e}")
        app = self.get_application()
        if app:
            app.sync_autostart()

    def show_about(self):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name("Redragon K719")
        dialog.set_version(f"Version {__version__}")
        firmware = connected_firmware()
        comments = ("Unofficial Linux app for the Redragon K719 keyboard: lighting effects, "
                    "per-key colors, key remapping, pictures and GIFs on the built-in screen, "
                    "and a music visualizer. Works over the USB cable and the 2.4G receiver.")
        if firmware:
            comments += "\n\nConnected: " + "; ".join(firmware)
        dialog.set_comments(comments)
        dialog.set_website(REPO_URL)
        dialog.set_website_label("Project page on GitHub")
        dialog.set_authors(["Alejandro Escobar"])
        dialog.set_copyright("\u00a9 2026 Alejandro Escobar\n"
                             "Not affiliated with or endorsed by Redragon.")
        dialog.set_license_type(Gtk.License.GPL_3_0)
        if Gtk.IconTheme.get_default().has_icon("com.argentag.K719"):
            dialog.set_logo_icon_name("com.argentag.K719")
        else:
            dialog.set_logo_icon_name("input-keyboard")
        dialog.connect("response", lambda d, _r: d.destroy())
        dialog.present()

    def stop_audio_and_wait(self):
        if self.audio_stop:
            self.audio_stop.set()
            time.sleep(0.3)  # let the visualizer restore the previous effect

    # ---- background work -------------------------------------------------

    def run(self, what, fn, done=None):
        if self.busy:
            return
        if self.kb is None:
            self.set_status("Not connected")
            return
        self.busy = True
        self.set_status(what + "...")

        def worker():
            try:
                if self.kb.wireless and not self.kb.link_ok():
                    GLib.idle_add(self.set_status, "Keyboard asleep - press a key on it...")
                    if not self.kb.wait_online(30):
                        raise K719Error("keyboard not reachable through the receiver")
                res = fn()
                err = None
            except Exception as e:  # shown to the user
                res, err = None, e
            GLib.idle_add(finish, res, err)

        def finish(res, err):
            self.busy = False
            if err:
                self.set_status(f"Error: {err}")
            else:
                self.set_status(what + " - done")
                if done:
                    done(res)

        threading.Thread(target=worker, daemon=True).start()

    def set_status(self, text):
        conn = ""
        if self.kb:
            conn = f"{self.kb.path} via {'2.4G receiver' if self.kb.wireless else 'USB cable'} | "
        self.status.set_text(conn + text)

    def connect_device(self):
        if self.kb:
            self.kb.close()
            self.kb = None
        try:
            self.kb = K719()
        except K719Error as e:
            self.set_status(str(e))
            return
        self.run("Reading keyboard", self._read_all, self._apply_read)

    def _read_all(self):
        light = self.kb.get_lighting()
        colors = self.kb.get_custom_colors()
        km = state.load_keymap(self.kb.num_keys) or self.kb.get_default_keymap()
        return light, colors, km

    def _apply_read(self, res):
        self._calib_show_saved()
        light, colors, km = res
        self.custom = list(colors)
        self.keymap = list(km)
        mode_name = layout.MODES.get(light["mode"])
        if mode_name:
            self.mode_combo.set_active_id(mode_name)
        self.bright.set_value(light["brightness"])
        self.speed.set_value(light["speed"])
        self.direction.set_value(light["direction"])
        self.multi.set_active(light["multicolor"])
        self.color_btn.set_rgba(rgb_to_gdk(light["color"]))
        self.refresh_views()

    def refresh_views(self):
        self.kview.colors = {i: c for i, c in enumerate(self.custom)}
        self.kview.queue_draw()
        if self.keymap:
            changed = {k[0] for k in layout.KEYS
                       if bytes(self.keymap[k[0]]) != k[5].to_bytes(3, "big")}
            self.mview.labels = {i: layout.describe_action(self.keymap[i]) for i in changed}
            self.mview.colors = {k[0]: (180, 120, 20) if k[0] in changed else (40, 40, 40)
                                 for k in layout.KEYS}
            self.mview.queue_draw()

    # ---- lighting --------------------------------------------------------

    def _light_page(self):
        g = Gtk.Grid(column_spacing=12, row_spacing=10, margin=12)
        self.mode_combo = Gtk.ComboBoxText()
        for mid, name in layout.MODES.items():
            self.mode_combo.append(name, name.capitalize())
        self.bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 5, 1)
        self.speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 5, 1)
        for s in (self.bright, self.speed):
            s.set_hexpand(True)
            s.set_digits(0)
        self.direction = Gtk.SpinButton.new_with_range(0, 7, 1)
        self.multi = Gtk.CheckButton(label="Multicolor (rainbow)")
        self.color_btn = Gtk.ColorButton()
        apply = Gtk.Button(label="Apply to keyboard")
        apply.connect("clicked", self.apply_light)
        rows = [("Effect", self.mode_combo), ("Brightness", self.bright), ("Speed", self.speed),
                ("Direction", self.direction), ("Color", self.color_btn), ("", self.multi)]
        for i, (lbl, w) in enumerate(rows):
            g.attach(Gtk.Label(label=lbl, xalign=0), 0, i, 1, 1)
            g.attach(w, 1, i, 1, 1)
        g.attach(apply, 1, len(rows), 1, 1)

        return g

    # ---- audio wave ------------------------------------------------------

    def _audio_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=12)

        # visualizer controls
        abox = Gtk.Box(spacing=8)
        self.audio_toggle = Gtk.ToggleButton(label="Start visualizer")
        self.audio_toggle.connect("toggled", self.toggle_audio)
        self.audio_rainbow = Gtk.CheckButton(label="Rainbow", active=True)
        self.audio_color = Gtk.ColorButton.new_with_rgba(rgb_to_gdk((0, 160, 255)))
        self.audio_style = {"style": "spectrum"}
        style_combo = Gtk.ComboBoxText()
        for sid, label in (("spectrum", "Spectrum bars"), ("beat", "Beat flash"),
                           ("both", "Bars + beat flash")):
            style_combo.append(sid, label)
        style_combo.set_active_id("spectrum")
        style_combo.connect("changed", lambda c: self.audio_style.__setitem__(
            "style", c.get_active_id()))
        for w in (self.audio_toggle, Gtk.Label(label="Style"), style_combo,
                  self.audio_rainbow, self.audio_color):
            abox.pack_start(w, False, True, 0)
        page.pack_start(abox, False, False, 0)

        # Sensitivity sliders multiply the bar heights; they apply live while running.
        self.audio_gains = {"overall": 1.0, "bass": 1.0, "mid": 1.0, "treble": 1.0}
        sliders = Gtk.Grid(column_spacing=8, row_spacing=2)
        for i, (key, label) in enumerate([("overall", "Sensitivity"),
                                          ("bass", "Bass (< 250 Hz)"),
                                          ("mid", "Mid (250 Hz - 2 kHz)"),
                                          ("treble", "Treble (> 2 kHz)")]):
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.25, 3, 0.05)
            sc.set_value(1)
            sc.set_hexpand(True)
            sc.add_mark(1, Gtk.PositionType.BOTTOM, None)
            sc.connect("format-value", lambda _s, v: f"{v:.2f}\u00d7")
            sc.connect("value-changed", lambda s, k=key: self.audio_gains.__setitem__(
                k, s.get_value()))
            sliders.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            sliders.attach(sc, 1, i, 1, 1)
        reset = Gtk.Button(label="Reset")
        reset.connect("clicked", lambda *_: [
            c.set_value(1) for c in sliders.get_children() if isinstance(c, Gtk.Scale)])
        sliders.attach(reset, 2, 0, 1, 1)
        page.pack_start(sliders, False, False, 0)
        page.pack_start(Gtk.Label(
            label="Spectrum: bars per frequency (bass left, treble right). Beat flash: the "
                  "whole keyboard flashes on the beat (the tempo is followed automatically; "
                  "allow a few seconds to lock on). Style and sliders change live; "
                  "Sensitivity also affects how readily beats are found. Stopping restores "
                  "the previous effect.", xalign=0, wrap=True), False, False, 0)

        page.pack_start(Gtk.Separator(), False, False, 0)
        page.pack_start(self._calibration_section(), False, False, 0)
        return page

    # ---- sync calibration ------------------------------------------------

    def _calibration_section(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        title = Gtk.Label(xalign=0)
        title.set_markup("<b>Sync calibration</b>")
        box.pack_start(title, False, False, 0)
        box.pack_start(Gtk.Label(
            label="Measures how late the lights appear on your setup (the 2.4G receiver is "
                  "slower than the cable) so the beat flashes land on the beat. Two short "
                  "rounds, each saved on its own: press Space in time with beeps (sound), "
                  "and with flashes on the keyboard (light, per connection). Redo either one "
                  "any time, e.g. the sound round after switching to headphones. Spectrum "
                  "bars react to the sound, so they aren't shifted.",
            xalign=0, wrap=True), False, False, 0)
        self.calib_saved = Gtk.Label(xalign=0, wrap=True)
        box.pack_start(self.calib_saved, False, False, 0)

        self.calib_text = Gtk.Label(xalign=0, wrap=True)
        self.calib_text.set_no_show_all(True)
        box.pack_start(self.calib_text, False, False, 0)
        self.calib_progress = Gtk.ProgressBar(show_text=True)
        self.calib_progress.set_no_show_all(True)
        box.pack_start(self.calib_progress, False, False, 0)

        buttons = Gtk.Box(spacing=8)
        self.calib_sound_btn = Gtk.Button(label="Sound round")
        self.calib_sound_btn.connect("clicked", lambda *_: self._calib_prepare("sound"))
        self.calib_light_btn = Gtk.Button(label="Light round")
        self.calib_light_btn.connect("clicked", lambda *_: self._calib_prepare("light"))
        self.calib_start = Gtk.Button(label="Start")
        self.calib_start.connect("clicked", lambda *_: self._calib_run(self.calib_round))
        self.calib_start.set_no_show_all(True)
        self.calib_cancel = Gtk.Button(label="Cancel")
        self.calib_cancel.connect("clicked", lambda *_: self._calib_finish("Cancelled."))
        self.calib_cancel.set_no_show_all(True)
        self.calib_forget = Gtk.Button(label="Reset")
        self.calib_forget.set_tooltip_text(
            "Forget the calibration for the current connection and use the built-in estimate")
        self.calib_forget.connect("clicked", self._calib_forget)
        for w in (self.calib_sound_btn, self.calib_light_btn, self.calib_start,
                  self.calib_cancel):
            buttons.pack_start(w, False, False, 0)
        buttons.pack_end(self.calib_forget, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        self.calib_round = None  # "sound" / "light" while preparing or running
        self.calib_running = False
        self.calib_presses = None
        self.connect("key-press-event", self._calib_key)
        GLib.idle_add(self._calib_show_saved)
        return box

    def _calib_show_saved(self):
        if not self.kb:
            self.calib_saved.set_text("Connect the keyboard to see its calibration.")
            return False
        sound, light = state.get_calibration(self.kb)
        link = "2.4G receiver" if self.kb.wireless else "USB cable"
        lines = [
            "Sound round: " + ("<b>done</b>" if sound is not None else "not done yet"),
            f"Light round ({link}): " + ("<b>done</b>" if light is not None else "not done yet"),
        ]
        delay = state.get_light_delay(self.kb)
        if delay is not None:
            lines.append(f"Light delay over the {link}: <b>{round(delay * 1000)} ms</b> "
                         "\u2014 beat flashes are timed with it.")
        else:
            lines.append("Using the built-in estimate until both rounds are done.")
        self.calib_saved.set_markup("\n".join(lines))
        return False

    def _calib_say(self, text, progress=None):
        if not text:
            self.calib_text.hide()
            self.calib_progress.hide()
            return
        self.calib_text.set_text(text)
        self.calib_text.show()
        if progress is None:
            self.calib_progress.hide()
        else:
            self.calib_progress.set_fraction(progress)
            self.calib_progress.set_text(f"{round(progress * calibration.EVENTS)} / "
                                         f"{calibration.EVENTS}")
            self.calib_progress.show()

    def _calib_buttons(self, idle):
        """idle: round buttons shown; otherwise Start/Cancel for the chosen round."""
        for w in (self.calib_sound_btn, self.calib_light_btn, self.calib_forget):
            w.set_sensitive(idle)
        self.calib_start.set_visible(not idle)
        self.calib_start.set_sensitive(True)
        self.calib_cancel.set_visible(not idle)

    def _calib_prepare(self, which):
        if self.kb is None:
            self.connect_device()
        if not self.kb:
            self._calib_say("Connect the keyboard first.")
            return
        if self.audio_running():
            self.audio_toggle.set_active(False)  # stop the visualizer, then continue
            GLib.timeout_add(800, lambda: self._calib_prepare(which) and False)
            return
        if self.busy:
            self._calib_say("The keyboard is busy - try again in a moment.")
            return
        self.busy = True
        self.calib_round = which
        self._calib_buttons(idle=False)
        self.calib_start.set_label("Start")
        if which == "sound":
            self._calib_say(
                "Sound round. Pause any music. When you press Start, 16 beeps play at a "
                "steady beat. Press Space in time with every beep (the first three are just "
                "to find the rhythm). Keep this window focused.")
        else:
            self._calib_say(
                f"Light round. Watch the keyboard: when you press Start, the keys from "
                f"{calibration.FLASH_KEYS} flash white 16 times, without sound. Press Space "
                f"every time they flash (the first three are just to find the rhythm). Keep "
                f"this window focused.")

    def _calib_run(self, which):
        self.calib_running = True
        self.calib_stop = threading.Event()
        self.calib_start.set_sensitive(False)
        self.set_focus(None)  # Space must not click a button
        self.calib_presses = calibration.Presses()
        what = "beep" if which == "sound" else "flash"
        self._calib_say(f"Press Space with every {what}...", 0.0)

        def progress(n):
            GLib.idle_add(self._calib_say, f"Press Space with every {what}... "
                          f"({len(self.calib_presses)} presses)", n / calibration.EVENTS)

        def worker():
            try:
                if which == "sound":
                    events = calibration.sound_round(self.calib_stop, progress)
                else:
                    if self.kb.wireless and not self.kb.link_ok():
                        GLib.idle_add(self._calib_say, "Keyboard asleep - press a key on it...")
                        if not self.kb.wait_online(30):
                            raise K719Error("keyboard not reachable through the receiver")
                    events = calibration.light_round(self.kb, self.calib_stop, progress)
                result, err = (events, self.calib_presses.take()), None
            except Exception as e:  # shown to the user
                result, err = None, e
            GLib.idle_add(self._calib_round_done, which, result, err)

        threading.Thread(target=worker, daemon=True).start()

    def _calib_round_done(self, which, result, err):
        self.calib_running = False
        self.calib_presses = None
        if self.calib_stop.is_set():  # cancelled while the round was running
            self.busy = False
            return
        if err is None:
            events, presses = result
            try:
                offset, spread = calibration.summarize(calibration.offsets(events, presses),
                                                       which)
                sound, light = state.get_calibration(self.kb)
                sound = offset if which == "sound" else sound
                light = offset if which == "light" else light
                if sound is not None and light is not None:
                    calibration.check_delay(light - sound)
            except calibration.CalibrationError as e:
                err = e
        if err is not None:
            self.calib_start.set_label("Retry")
            self.calib_start.set_sensitive(True)
            self._calib_say(str(err))
            return
        if which == "sound":
            state.set_calibration(self.kb, sound=offset)
        else:
            state.set_calibration(self.kb, light=offset)
        name = "Sound" if which == "sound" else "Light"
        message = f"{name} round saved (your presses varied by \u00b1{round(spread * 500)} ms)."
        if state.get_light_delay(self.kb) is None:
            other = "light" if which == "sound" else "sound"
            message += f" Now do the {other} round."
        self._calib_finish(message)

    def _calib_finish(self, message):
        if getattr(self, "calib_stop", None) and self.calib_running:
            self.calib_stop.set()  # busy is released when the running round stops
        elif self.calib_round is not None:
            self.busy = False
        self.calib_round = None
        self.calib_presses = None
        self._calib_buttons(idle=True)
        self._calib_say(message)
        self._calib_show_saved()

    def _calib_forget(self, *_):
        if self.kb:
            state.set_calibration(self.kb, forget=True)
            self._calib_show_saved()
            self._calib_say("Calibration removed for this connection; using the built-in "
                            "estimate.")

    def _calib_key(self, _win, event):
        if self.calib_presses is not None and event.keyval in (Gdk.KEY_space, Gdk.KEY_KP_Space):
            if not event.is_modifier:
                self.calib_presses.add()
            return True  # swallow Space during a round
        return False

    def audio_running(self):
        return self.audio_stop is not None and not self.audio_stop.is_set()

    def _publish_audio_state(self, on):
        app = self.get_application()
        if app:
            app.set_audio_state(on)

    def toggle_audio(self, btn):
        from .audio import run_visualizer
        if not btn.get_active():
            if self.audio_stop:
                self.audio_stop.set()
            return
        if self.kb is None:
            self.connect_device()
        if self.busy and self.kb and not self.audio_running():
            # another keyboard operation (e.g. the initial read at startup) is in progress:
            # try again shortly instead of dropping the request
            btn.handler_block_by_func(self.toggle_audio)
            btn.set_active(False)
            btn.handler_unblock_by_func(self.toggle_audio)
            retries = getattr(self, "_audio_retries", 0)
            if retries < 140:  # up to ~35 s: a sleeping wireless keyboard takes time to wake
                self._audio_retries = retries + 1
                GLib.timeout_add(250, lambda: btn.set_active(True) and False)
            else:
                self._audio_retries = 0
                self._publish_audio_state(False)
            return
        self._audio_retries = 0
        if not self.kb:
            btn.set_active(False)
            self._publish_audio_state(False)
            return
        self.busy = True
        self.audio_stop = threading.Event()
        btn.set_label("Stop visualizer")
        self.set_status("Audio wave running")
        self._publish_audio_state(True)
        opts = dict(fg=gdk_to_rgb(self.audio_color.get_rgba()),
                    rainbow=self.audio_rainbow.get_active(),
                    gains=self.audio_gains, style=self.audio_style, stop=self.audio_stop,
                    light_delay_s=state.get_light_delay(self.kb))

        def worker():
            err = None
            try:
                if self.kb.wireless and not self.kb.link_ok():
                    GLib.idle_add(self.set_status, "Keyboard asleep - press a key on it...")
                    if not self.kb.wait_online(30):
                        raise K719Error("keyboard not reachable through the receiver")
                    GLib.idle_add(self.set_status, "Audio wave running")
                run_visualizer(self.kb, **opts)
            except Exception as e:  # shown to the user
                err = e
            GLib.idle_add(finished, err)

        def finished(err):
            self.busy = False
            self.audio_stop = None
            btn.set_label("Start visualizer")
            btn.set_active(False)
            self.set_status(f"Error: {err}" if err else "Audio wave stopped")
            self._publish_audio_state(False)

        threading.Thread(target=worker, daemon=True).start()

    def apply_light(self, *_):
        mode = layout.MODE_IDS[self.mode_combo.get_active_id() or "static"]
        args = dict(mode=mode, brightness=int(self.bright.get_value()),
                    speed=int(self.speed.get_value()),
                    direction=int(self.direction.get_value()),
                    color=gdk_to_rgb(self.color_btn.get_rgba()),
                    multicolor=self.multi.get_active())
        self.run("Writing lighting", lambda: self.kb.set_lighting(**args))

    # ---- per-key colors --------------------------------------------------

    def _custom_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=8)
        box.pack_start(Gtk.Label(
            label="Click keys to select (Ctrl/Shift-click to add), pick a color, paint, then "
                  "write. Writing switches the effect to Custom.", xalign=0), False, False, 0)
        self.kview = KeyboardView(lambda sel: None)
        box.pack_start(self.kview, True, True, 0)
        bar = Gtk.Box(spacing=8)
        self.paint_color = Gtk.ColorButton.new_with_rgba(rgb_to_gdk((255, 0, 0)))
        paint = Gtk.Button(label="Paint selected")
        paint.connect("clicked", self.paint_selected)
        fill = Gtk.Button(label="Fill all")
        fill.connect("clicked", self.fill_all)
        sel_all = Gtk.Button(label="Select all")
        sel_all.connect("clicked", self.select_all)
        write = Gtk.Button(label="Write to keyboard")
        write.connect("clicked", self.write_custom)
        for w in (self.paint_color, paint, fill, sel_all):
            bar.pack_start(w, False, False, 0)
        bar.pack_end(write, False, False, 0)
        box.pack_start(bar, False, False, 0)
        return box

    def paint_selected(self, *_):
        c = gdk_to_rgb(self.paint_color.get_rgba())
        for i in self.kview.selected:
            self.custom[i] = c
        self.refresh_views()

    def fill_all(self, *_):
        c = gdk_to_rgb(self.paint_color.get_rgba())
        self.custom = [c] * len(self.custom)
        self.refresh_views()

    def select_all(self, *_):
        self.kview.selected = {k[0] for k in layout.KEYS}
        self.kview.queue_draw()

    def write_custom(self, *_):
        colors = list(self.custom)

        def job():
            self.kb.set_custom_colors(colors)
            self.kb.set_lighting(mode=layout.MODE_CUSTOM)
        self.run("Writing per-key colors", job,
                 lambda _r: self.mode_combo.set_active_id("custom"))

    # ---- key mapping -----------------------------------------------------

    def _keymap_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=8)
        box.pack_start(Gtk.Label(
            label="Select a key, type what it should send (e.g. esc, ctrl+c, f13, lgui, none) "
                  "and press Set. Remapped keys are shown in orange.", xalign=0),
            False, False, 0)
        self.mview = KeyboardView(self.on_map_select)
        box.pack_start(self.mview, True, True, 0)
        bar = Gtk.Box(spacing=8)
        self.map_label = Gtk.Label(label="(no key selected)")
        self.map_entry = Gtk.Entry(placeholder_text="action, e.g. ctrl+c")
        self.map_entry.connect("activate", self.set_mapping)
        setb = Gtk.Button(label="Set")
        setb.connect("clicked", self.set_mapping)
        reset = Gtk.Button(label="Restore defaults")
        reset.connect("clicked", self.reset_mapping)
        for w in (self.map_label, self.map_entry, setb):
            bar.pack_start(w, False, False, 0)
        bar.pack_end(reset, False, False, 0)
        box.pack_start(bar, False, False, 0)
        return box

    def on_map_select(self, sel):
        if len(sel) == 1 and self.keymap:
            i = next(iter(sel))
            self.map_label.set_text(f"{layout.key_name(i)} →")
            self.map_entry.set_text(layout.describe_action(self.keymap[i]))
            self.map_entry.grab_focus()
        else:
            self.map_label.set_text("(select one key)")

    def set_mapping(self, *_):
        if len(self.mview.selected) != 1 or not self.keymap:
            return
        i = next(iter(self.mview.selected))
        try:
            action = layout.encode_action(self.map_entry.get_text())
        except ValueError as e:
            self.set_status(f"Error: {e}")
            return
        km = list(self.keymap)
        km[i] = action
        self._write_keymap(km)

    def reset_mapping(self, *_):
        f = layout.FACTORY_KEYMAP
        self._write_keymap([f[i * 3:i * 3 + 3] for i in range(len(self.keymap or []))])

    def _write_keymap(self, km):
        def done(_r):
            self.keymap = km
            state.save_keymap(km)
            self.refresh_views()
        self.run("Writing key mapping", lambda: self.kb.set_keymap(km), done)

    # ---- screen ----------------------------------------------------------

    def _screen_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        box.pack_start(Gtk.Label(
            label="Upload a picture or animated GIF (up to 80 frames) to the keyboard's "
                  "240x135 screen. Uploading only works with the keyboard on the USB cable "
                  "and takes about 3 s per frame.",
            xalign=0, wrap=True), False, False, 0)
        row = Gtk.Box(spacing=8)
        self.image_chooser = Gtk.FileChooserButton(title="Choose an image or GIF")
        flt = Gtk.FileFilter()
        flt.add_pixbuf_formats()
        self.image_chooser.set_filter(flt)
        self.image_chooser.connect("file-set", self.preview_image)
        self.interval = Gtk.SpinButton.new_with_range(20, 2000, 10)
        self.interval.set_value(100)
        row.pack_start(self.image_chooser, True, True, 0)
        row.pack_start(Gtk.Label(label="ms per frame"), False, False, 0)
        row.pack_start(self.interval, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.preview = Gtk.Image()
        self.preview.set_size_request(240, 135)
        self.frame_info = Gtk.Label(label="", xalign=0)
        self.progress = Gtk.ProgressBar(show_text=True)
        up = Gtk.Button(label="Upload to screen")
        up.connect("clicked", self.upload_image)
        clock = Gtk.Button(label="Set keyboard clock to this PC's time")
        clock.connect("clicked", lambda *_: self.run("Setting clock", self.kb.sync_clock))
        for w in (self.preview, self.frame_info, self.progress, up, Gtk.Separator(), clock):
            box.pack_start(w, False, False, 0)
        return box

    def preview_image(self, *_):
        from gi.repository import GdkPixbuf
        from .image import load_frames
        path = self.image_chooser.get_filename()
        if not path:
            return
        try:
            anim = GdkPixbuf.PixbufAnimation.new_from_file(path)
            frames, interval = load_frames(path)
        except Exception as e:  # shown to the user
            self.set_status(f"Error: {e}")
            return
        if anim.is_static_image():
            pb = anim.get_static_image().scale_simple(240, 135, GdkPixbuf.InterpType.BILINEAR)
            self.preview.set_from_pixbuf(pb)
        else:
            self.preview.set_from_animation(anim)
        self.interval.set_value(interval)
        self.frame_info.set_text(f"{len(frames)} frame(s) will be uploaded")

    def upload_image(self, *_):
        from .image import load_rgb565_frames
        path = self.image_chooser.get_filename()
        if not path or not self.kb:
            return
        interval = int(self.interval.get_value())

        def job():
            w, h = self.kb.screen_size()
            frames, _ = load_rgb565_frames(path, w or 240, h or 135)
            self.kb.upload_screen(
                frames, interval,
                progress=lambda d, t: GLib.idle_add(self.progress.set_fraction, d / t))
        self.run("Uploading image", job)


class K719Application(Gtk.Application):
    """Single-instance app. Its actions are exported on D-Bus (org.gtk.Actions at
    /com/argentag/K719), which is how the GNOME panel indicator talks to it:
      show  - present the window
      audio - boolean state: audio wave visualizer on/off
      quit  - stop the visualizer and exit"""

    ID = "com.argentag.K719"

    def __init__(self):
        super().__init__(application_id=self.ID)
        self.window = None
        self.add_main_option("background", ord("b"), GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE, "Start hidden (for autostart)", None)
        self.add_main_option("toggle-audio", ord("t"), GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE, "Toggle the audio wave in the running app",
                             None)
        self.add_main_option("quit", ord("q"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Quit the running app (stops the audio wave)", None)
        self.connect("handle-local-options", self._local_options)

    def _local_options(self, _app, options):
        opts = options.end().unpack()
        self.start_hidden = "background" in opts
        if "quit" in opts:
            self.register(None)
            if self.get_is_remote():
                self.activate_action("quit", None)
            return 0
        if "toggle-audio" in opts:
            self.register(None)
            if self.get_is_remote():
                self.activate_action("toggle-audio", None)
                return 0
            self.pending_toggle = True
        return -1

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()  # keep running with the window hidden
        show = Gio.SimpleAction.new("show", None)
        show.connect("activate", lambda *_: self.show_window())
        self.add_action(show)
        self.audio_action = Gio.SimpleAction.new_stateful("audio", None,
                                                          GLib.Variant.new_boolean(False))
        self.audio_action.connect("change-state", self._on_audio_change)
        self.add_action(self.audio_action)
        toggle = Gio.SimpleAction.new("toggle-audio", None)
        toggle.connect("activate", lambda *_: self._on_audio_change(
            self.audio_action, GLib.Variant.new_boolean(not self.audio_action.get_state())))
        self.add_action(toggle)
        self.autostart_action = Gio.SimpleAction.new_stateful(
            "autostart", None, GLib.Variant.new_boolean(autostart_enabled()))
        self.autostart_action.connect("change-state", self._on_autostart_change)
        self.add_action(self.autostart_action)
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", lambda *_: (self.show_window(), self.window.show_about()))
        self.add_action(about)
        quit_ = Gio.SimpleAction.new("quit", None)
        quit_.connect("activate", lambda *_: self.quit_app())
        self.add_action(quit_)
        self.window = App(application=self)
        try:
            enable_panel_icon_once()
        except GLib.Error:
            pass  # not fatal: the icon can still be enabled with gnome-extensions

    def do_activate(self):
        if getattr(self, "start_hidden", False):
            self.start_hidden = False  # later activations (a second launch) show the window
            self.window.realize()
        else:
            self.show_window()
        if getattr(self, "pending_toggle", False):
            self.pending_toggle = False
            self.activate_action("toggle-audio", None)

    def show_window(self):
        self.window.show_all()
        self.window.present()

    def _on_audio_change(self, action, value):
        want = value.get_boolean()
        if want != self.window.audio_toggle.get_active():
            self.window.audio_toggle.set_active(want)  # runs App.toggle_audio
        else:
            action.set_state(value)

    def _on_autostart_change(self, _action, value):
        # the checkbox handler writes the file and calls sync_autostart()
        self.window.autostart_check.set_active(value.get_boolean())
        self.sync_autostart()

    def sync_autostart(self):
        on = autostart_enabled()
        self.autostart_action.set_state(GLib.Variant.new_boolean(on))
        if self.window.autostart_check.get_active() != on:
            self.window.autostart_check.set_active(on)

    def set_audio_state(self, on):
        if self.audio_action.get_state().get_boolean() != on:
            self.audio_action.set_state(GLib.Variant.new_boolean(on))

    def quit_app(self):
        self.window.stop_audio_and_wait()
        self.quit()


def main():
    import sys
    GLib.set_prgname(K719Application.ID)  # window class matches the .desktop file for the dock
    GLib.set_application_name("Redragon K719")
    sys.exit(K719Application().run(sys.argv))
