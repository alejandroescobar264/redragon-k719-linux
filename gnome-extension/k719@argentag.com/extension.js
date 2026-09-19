// Panel icon for redragon-k719-linux (k719-gui). SPDX-License-Identifier: GPL-3.0-or-later
// The icon is only shown while the app is running (it appears when the app starts and
// disappears when it quits). Left click: show the app window.
// Right click: menu (show app, audio wave on/off, start at login on/off, about, quit).
// The app is a GtkApplication (com.argentag.K719) whose actions are exported on D-Bus;
// this indicator calls them and follows the "audio" action's state for its icon.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_ID = 'com.argentag.K719';
const APP_PATH = '/com/argentag/K719';
// k719-gui from the .deb (/usr/bin) or a per-user install (~/.local/bin)
const LAUNCHER = GLib.find_program_in_path('k719-gui') ??
    GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'k719-gui']);
const AUTOSTART_FILE = GLib.build_filenamev([GLib.get_user_config_dir(), 'autostart',
    'com.argentag.K719.desktop']);

const AUDIO_ON_STYLE = 'color: #e01b24;'; // Redragon red while the audio wave runs
const ICON_SIZE = 20; // px; GNOME's default panel icon is 16

const K719Indicator = GObject.registerClass(
class K719Indicator extends PanelMenu.Button {
    _init(extensionPath) {
        super._init(0.0, 'Redragon K719', false);
        this._icon = new St.Icon({
            style_class: 'system-status-icon',
            icon_size: ICON_SIZE,
            gicon: Gio.icon_new_for_string(`${extensionPath}/icons/redragon-symbolic.svg`),
        });
        this.add_child(this._icon);
        this._buildMenu();
        this._actions = null;
        this._actionSignals = [];
        this._audioOn = false;
        this._autostart = false;
        this._running = false;
        this._watchId = Gio.bus_watch_name(Gio.BusType.SESSION, APP_ID,
            Gio.BusNameWatcherFlags.NONE,
            () => this._appeared(),
            () => this._vanished());
        this._refresh();
    }

    _appeared() {
        this._running = true;
        this._actions = Gio.DBusActionGroup.get(Gio.DBus.session, APP_ID, APP_PATH);
        this._actionSignals = [
            this._actions.connect('action-state-changed', (_g, name, state) => {
                if (name === 'audio')
                    this._setAudio(state.get_boolean());
                else if (name === 'autostart')
                    this._setAutostart(state.get_boolean());
            }),
            this._actions.connect('action-added', (_g, name) => {
                const state = this._actions.get_action_state(name)?.get_boolean() ?? false;
                if (name === 'audio')
                    this._setAudio(state);
                else if (name === 'autostart')
                    this._setAutostart(state);
            }),
        ];
        this._actions.list_actions(); // starts the async fetch; 'action-added' follows
        this._refresh();
    }

    _vanished() {
        this._disconnectActions();
        this._running = false;
        this._audioOn = false;
        this._refresh();
    }

    _disconnectActions() {
        if (this._actions) {
            for (const id of this._actionSignals)
                this._actions.disconnect(id);
        }
        this._actionSignals = [];
        this._actions = null;
    }

    _buildMenu() {
        this._showItem = new PopupMenu.PopupMenuItem('Show Redragon K719');
        this._showItem.connect('activate', () => this._show());
        this.menu.addMenuItem(this._showItem);

        this._audioItem = new PopupMenu.PopupSwitchMenuItem('Audio wave', false);
        this._audioItem.connect('toggled', (_item, on) => {
            if (on !== this._audioOn)
                this._toggleAudio();
        });
        this.menu.addMenuItem(this._audioItem);

        this._autostartItem = new PopupMenu.PopupSwitchMenuItem('Start at login', false);
        this._autostartItem.connect('toggled', (_item, on) => {
            if (this._actions && on !== this._autostart)
                this._actions.change_action_state('autostart', GLib.Variant.new_boolean(on));
        });
        this.menu.addMenuItem(this._autostartItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._aboutItem = new PopupMenu.PopupMenuItem('About');
        this._aboutItem.connect('activate', () => this._actions?.activate_action('about', null));
        this.menu.addMenuItem(this._aboutItem);

        this._quitItem = new PopupMenu.PopupMenuItem('Quit');
        this._quitItem.connect('activate', () => this._actions?.activate_action('quit', null));
        this.menu.addMenuItem(this._quitItem);
    }

    _setAutostart(on) {
        this._autostart = on;
        this._refresh();
    }

    _setAudio(on) {
        this._audioOn = on;
        this._refresh();
    }

    _refresh() {
        this._icon.style = this._audioOn ? AUDIO_ON_STYLE : null;
        this.visible = this._running;
        this._audioItem.setToggleState(this._audioOn);
        const autostart = this._running ? this._autostart : GLib.file_test(AUTOSTART_FILE, GLib.FileTest.EXISTS);
        this._autostartItem.setToggleState(autostart);
        this._autostartItem.reactive = this._running; // setting lives in the app
    }

    _launch(args) {
        try {
            GLib.spawn_async(null, [LAUNCHER, ...args], null, GLib.SpawnFlags.DEFAULT, null);
        } catch (e) {
            Main.notifyError('Redragon K719', `Could not start ${LAUNCHER}: ${e.message}`);
        }
    }

    _show() {
        if (this._actions)
            this._actions.activate_action('show', null);
        else
            this._launch([]);
    }

    _toggleAudio() {
        if (this._actions)
            this._actions.activate_action('toggle-audio', null);
        else
            this._launch(['--background', '--toggle-audio']);
    }

    vfunc_event(event) {
        // PanelMenu.Button opens the menu on any press; here only the right button does.
        const type = event.type();
        if (type === Clutter.EventType.BUTTON_PRESS) {
            if (event.get_button() === Clutter.BUTTON_SECONDARY)
                this.menu.toggle();
            else if (event.get_button() === Clutter.BUTTON_PRIMARY)
                this._show();
            return Clutter.EVENT_STOP;
        }
        if (type === Clutter.EventType.TOUCH_BEGIN) {
            this.menu.toggle();
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    destroy() {
        if (this._watchId) {
            Gio.bus_unwatch_name(this._watchId);
            this._watchId = 0;
        }
        this._disconnectActions();
        super.destroy();
    }
});

export default class K719Extension extends Extension {
    enable() {
        this._indicator = new K719Indicator(this.path);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
