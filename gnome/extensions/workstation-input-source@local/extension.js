import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {getInputSourceManager} from 'resource:///org/gnome/shell/ui/status/keyboard.js';

// ~/.local/share/wsconfig/libexec: home-manager link to the internal tools of wsconfig.
const LED_HELPER = GLib.build_filenamev([GLib.get_home_dir(), '.local/share/wsconfig/libexec/ws-caps-led']);

const DBUS_XML = `
<node>
  <interface name="org.gnome.Shell.Extensions.WorkstationInputSource">
    <method name="ToggleCaps">
      <arg type="b" direction="out" name="success"/>
    </method>
    <method name="Select">
      <arg type="s" direction="in" name="target"/>
      <arg type="b" direction="out" name="success"/>
    </method>
    <method name="Cycle">
      <arg type="s" direction="in" name="direction"/>
      <arg type="b" direction="out" name="success"/>
    </method>
    <method name="GetState">
      <arg type="s" direction="out" name="current"/>
      <arg type="s" direction="out" name="caps_state"/>
    </method>
  </interface>
</node>
`;

export default class WorkstationInputSourceExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._manager = getInputSourceManager();

        this._sessionModeId = Main.sessionMode.connect(
            'updated',
            () => this._onSessionModeUpdated()
        );

        this._screenShieldId = Main.screenShield?.connect(
            'locked-changed',
            () => this._onSessionModeUpdated()
        ) ?? 0;

        this._sourceChangedId = this._manager.connect(
            'current-source-changed',
            () => this._onCurrentSourceChanged()
        );

        // Overview search (Command/Win+Space and every other way in) is
        // typed in English; the previous source comes back on close.
        this._overviewRestore = null;
        this._overviewShowingId = Main.overview.connect(
            'showing',
            () => this._onOverviewShowing()
        );
        this._overviewHiddenId = Main.overview.connect(
            'hidden',
            () => this._onOverviewHidden()
        );

        // A keyboard that appears (t2bce re-creates the internal one on
        // every resume) starts with the LED off, and GNOME sets its LEDs
        // from the xkb state (CapsLock off): light it again for RU/UA.
        this._ledTimeoutId = 0;
        this._seat = Clutter.get_default_backend().get_default_seat();
        this._deviceAddedId = this._seat.connect('device-added', (_seat, device) => {
            if (device.get_device_type() === Clutter.InputDeviceType.KEYBOARD_DEVICE)
                this._refreshLedLater();
        });

        this._dbus = Gio.DBusExportedObject.wrapJSObject(DBUS_XML, this);
        this._dbus.export(
            Gio.DBus.session,
            '/org/gnome/Shell/Extensions/WorkstationInputSource'
        );

        this._syncFromCurrent();
        this._onSessionModeUpdated();
    }

    disable() {
        if (this._sessionModeId) {
            Main.sessionMode.disconnect(this._sessionModeId);
            this._sessionModeId = 0;
        }

        if (this._screenShieldId && Main.screenShield) {
            Main.screenShield.disconnect(this._screenShieldId);
            this._screenShieldId = 0;
        }

        if (this._sourceChangedId) {
            this._manager.disconnect(this._sourceChangedId);
            this._sourceChangedId = 0;
        }

        if (this._overviewShowingId) {
            Main.overview.disconnect(this._overviewShowingId);
            this._overviewShowingId = 0;
        }

        if (this._overviewHiddenId) {
            Main.overview.disconnect(this._overviewHiddenId);
            this._overviewHiddenId = 0;
        }

        if (this._deviceAddedId) {
            this._seat.disconnect(this._deviceAddedId);
            this._deviceAddedId = 0;
        }
        this._seat = null;

        if (this._ledTimeoutId) {
            GLib.source_remove(this._ledTimeoutId);
            this._ledTimeoutId = 0;
        }

        this._overviewRestore = null;

        this._dbus?.flush();
        this._dbus?.unexport();

        this._dbus = null;
        this._manager = null;
        this._settings = null;
    }

    _token(source) {
        if (!source)
            return '';

        const type = String(source.type ?? '').toLowerCase();
        const id = String(source.id ?? source.xkbId ?? '').toLowerCase();
        const shortName = String(source.shortName ?? '').toLowerCase();

        if (type && type !== 'xkb')
            return '';

        const base = id.split('+', 1)[0];

        if (base === 'us' || shortName === 'en')
            return 'en';

        if (base === 'ru' || shortName === 'ru')
            return 'ru';

        if (base === 'ua' || shortName === 'ua' || shortName === 'uk')
            return 'ua';

        return '';
    }

    _sources() {
        return Object.values(this._manager.inputSources ?? {});
    }

    _find(target) {
        return this._sources().find(source => this._token(source) === target)
            ?? null;
    }

    _setLed(binaryState) {
        const action = binaryState === 'ru' ? 'on' : 'off';

        try {
            Gio.Subprocess.new(
                [LED_HELPER, action],
                Gio.SubprocessFlags.STDOUT_SILENCE |
                Gio.SubprocessFlags.STDERR_SILENCE
            );
        } catch (error) {
            console.warn(
                `${this.uuid}: failed to set CapsLock LED: ${error.message}`
            );
        }
    }



    _isUnlockDialog() {
        return Main.sessionMode.currentMode === 'unlock-dialog';
    }

    _onSessionModeUpdated() {
        if (this._isUnlockDialog()) {
            // Locked with the overview open: the lock screen owns the
            // source now, nothing is restored afterwards.
            this._overviewRestore = null;
            this._syncLockScreenEnglish();
            return;
        }

        // Back in the normal user session. Re-sync logical Caps state
        // and LED from the input source GNOME restored (unless it is the
        // temporary overview EN).
        this._onCurrentSourceChanged();
        // GNOME restores the source and resets the LEDs of the devices
        // after this signal too: the LED once more when that is done.
        this._refreshLedLater();
    }

    // The LED of the current source again, without touching the
    // remembered EN/RU state.
    _refreshLedLater() {
        if (this._ledTimeoutId)
            GLib.source_remove(this._ledTimeoutId);

        this._ledTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 700, () => {
            this._ledTimeoutId = 0;

            if (this._isUnlockDialog() || this._overviewRestore) {
                this._setLed('en');
            } else {
                const current = this._token(this._manager?.currentSource);
                this._setLed(current === 'ru' || current === 'ua' ? 'ru' : 'en');
            }

            return GLib.SOURCE_REMOVE;
        });
    }

    _onCurrentSourceChanged() {
        if (this._isUnlockDialog()) {
            // The password field can make GNOME reload InputSourceManager.
            // That reload may reactivate the pre-lock MRU source.
            this._syncLockScreenEnglish();
            return;
        }

        if (this._overviewRestore) {
            const current = this._token(this._manager.currentSource);

            // The temporary overview EN: keep the remembered EN/RU state.
            if (current === 'en') {
                this._setLed('en');
                return;
            }

            // Switched by hand while the overview is open (panel menu or
            // anything else): that choice stays.
            this._overviewRestore = null;
        }

        this._syncFromCurrent();
    }

    _onOverviewShowing() {
        if (this._isUnlockDialog())
            return;

        const current = this._token(this._manager.currentSource);
        if (current !== 'ru' && current !== 'ua')
            return;

        // Like the lock screen: EN without touching caps-binary-state.
        this._overviewRestore = current;
        this._setLed('en');
        this._activate('en');
    }

    _onOverviewHidden() {
        const target = this._overviewRestore;
        this._overviewRestore = null;

        if (!target || this._isUnlockDialog())
            return;

        if (this._token(this._manager.currentSource) === 'en')
            this._activate(target);
    }

    _syncLockScreenEnglish() {
        if (!this._isUnlockDialog())
            return;

        // Lock/unlock password entry is always English. Do NOT overwrite
        // the remembered EN/RU Caps state while the screen is locked.
        this._setLed('en');

        const current = this._token(this._manager.currentSource);
        if (current !== 'en')
            this._activate('en');
    }

    _syncFromCurrent() {
        const current = this._token(this._manager.currentSource);

        if (current === 'en') {
            this._settings.set_string('caps-binary-state', 'en');
            this._setLed('en');
            return;
        }

        if (current === 'ru') {
            this._settings.set_string('caps-binary-state', 'ru');
            this._setLed('ru');
            return;
        }

        if (current === 'ua') {
            // UA lights the LED as requested, but does not overwrite
            // remembered EN/RU state used by the plain CapsLock toggle.
            this._setLed('ru');
            return;
        }

        this._setLed('en');
    }

    _activate(target) {
        const source = this._find(target);

        if (!source) {
            console.error(
                `${this.uuid}: input source '${target}' is not configured`
            );
            return false;
        }

        source.activate();
        return true;
    }

    ToggleCaps() {
        this._overviewRestore = null;

        const current = this._token(this._manager.currentSource);

        let target;

        if (current === 'en')
            target = 'ru';
        else
            target = 'en';

        // Explicit semantics:
        // EN -> RU
        // RU -> EN
        // UA/unknown -> EN
        this._settings.set_string('caps-binary-state', target);
        this._setLed(target);

        return this._activate(target);
    }


    Cycle(direction) {
        this._overviewRestore = null;

        direction = String(direction).toLowerCase();

        if (!['next', 'prev'].includes(direction))
            return false;

        const order = ['en', 'ru', 'ua'];
        const current = this._token(this._manager.currentSource);
        const index = order.indexOf(current);

        if (index < 0)
            return this._activate('en');

        const delta = direction === 'prev' ? -1 : 1;
        const nextIndex = (index + delta + order.length) % order.length;

        return this._activate(order[nextIndex]);
    }

    Select(target) {
        this._overviewRestore = null;

        target = String(target).toLowerCase();

        if (!['en', 'ru', 'ua'].includes(target))
            return false;

        if (target === 'en' || target === 'ru') {
            this._settings.set_string('caps-binary-state', target);
            this._setLed(target);
        }

        return this._activate(target);
    }

    GetState() {
        const current = this._token(this._manager.currentSource) || 'unknown';
        const capsState = this._settings.get_string('caps-binary-state');

        return [current, capsState];
    }
}
