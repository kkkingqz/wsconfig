import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

// Hibernate in the power menu of Quick Settings, right under Suspend
// (ws help suspend, Hibernate). Shown only while logind's CanHibernate says
// yes or challenge: hosts without a resume device never see it.
const RETRY_MS = 500;

export default class WorkstationHibernateExtension extends Extension {
    enable() {
        this._cancellable = new Gio.Cancellable();
        this._retryId = 0;
        this._addItem();
    }

    disable() {
        if (this._retryId)
            GLib.source_remove(this._retryId);
        this._retryId = 0;
        this._cancellable.cancel();
        this._cancellable = null;
        this._menu?.disconnectObject(this);
        this._menu = null;
        this._item?.destroy();
        this._item = null;
    }

    // Quick Settings add their system indicator asynchronously at startup.
    _addItem() {
        const system = Main.panel.statusArea.quickSettings?._system;
        if (!system) {
            this._retryId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, RETRY_MS, () => {
                this._retryId = 0;
                this._addItem();
                return GLib.SOURCE_REMOVE;
            });
            return;
        }

        this._menu = system._systemItem.menu;
        this._item = new PopupMenu.PopupMenuItem('Hibernate');
        this._item.visible = false;
        this._item.connect('activate', () => {
            Main.panel.closeQuickSettings();
            this._logind('Hibernate', new GLib.Variant('(b)', [true]));
        });
        // 0 is Suspend.
        this._menu.addMenuItem(this._item, 1);

        this._menu.connectObject('open-state-changed', (menu, open) => {
            if (open)
                this._sync();
        }, this);
        this._sync();
    }

    _sync() {
        this._logind('CanHibernate', null, reply => {
            const [answer] = reply.deepUnpack();
            if (this._item)
                this._item.visible = answer === 'yes' || answer === 'challenge';
        });
    }

    _logind(method, params, onReply) {
        Gio.DBus.system.call('org.freedesktop.login1', '/org/freedesktop/login1',
            'org.freedesktop.login1.Manager', method, params, null,
            Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION, -1, this._cancellable,
            (connection, result) => {
                let reply;
                try {
                    reply = connection.call_finish(result);
                } catch (e) {
                    if (!e.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
                        console.error(`workstation-hibernate: ${method}: ${e.message}`);
                    return;
                }
                onReply?.(reply);
            });
    }
}
