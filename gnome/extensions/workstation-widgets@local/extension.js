import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import Mtk from 'gi://Mtk';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {PanelButtons} from './lib/panelButtons.js';
import {IpcClient} from './lib/ipcClient.js';
import {WindowPlacement} from './lib/windowPlacement.js';
import {validateManifest} from './lib/manifest.mjs';
import {shouldDismiss} from './lib/dismissal.mjs';

function readJson(path) {
    const [ok, bytes] = Gio.File.new_for_path(path).load_contents(null);
    if (!ok) throw new Error(`Cannot read ${path}`);
    return JSON.parse(new TextDecoder().decode(bytes));
}
export default class WorkstationWidgets extends Extension {
    enable() {
        this.signals = [];
        this.focusTimer = 0;
        this.suppressedUntil = 0;
        this.instanceId = null;
        this.reloadTimer = 0;
        try {
            const root = GLib.build_filenamev([GLib.get_user_config_dir(), 'workstation', 'widgets']);
            const config = readJson(`${root}/runtime.json`);
            if (config.schemaVersion !== 1 || config.adapter !== 'gnome' || config.configName !== 'workstation-widgets'
                || typeof config.qsPath !== 'string' || !GLib.path_is_absolute(config.qsPath)) throw new Error('Invalid widget runtime config');
            const entries = validateManifest(readJson(config.manifestPath));
            this.monitor = Gio.File.new_for_path(root).monitor_directory(Gio.FileMonitorFlags.NONE, null);
            this.connectSignal(this.monitor, 'changed', (_monitor, file, other) => {
                if (![file?.get_basename(), other?.get_basename()].some(name => ['manifest.json', 'runtime.json'].includes(name))) return;
                if (this.reloadTimer) GLib.source_remove(this.reloadTimer);
                this.reloadTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
                    this.reloadTimer = 0; this.disable(); this.enable(); return GLib.SOURCE_REMOVE;
                });
            });
            this.client = new IpcClient(config, snapshot => {
                this.buttons.update(snapshot); this.placement.update(snapshot);
                if (this.instanceId !== snapshot.instanceId && snapshot.adapter.ready) { this.instanceId = snapshot.instanceId; this.sendAnimations?.(); }
            }, () => { this.buttons.update(null); this.placement.destroy(); });
            this.buttons = new PanelButtons(entries, (id, timestamp) => {
                this.suppressedUntil = GLib.get_monotonic_time() + 250000;
                this.placement.timestamp = timestamp;
                this.client.call('widgets', 'toggle', [id]).catch(error => console.error(`Workstation Widgets: ${error}`));
            });
            this.placement = new WindowPlacement(this.client, this.buttons);
            this.settings = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
            const animations = () => this.client.call('widgetAdapter', 'setAnimationsEnabled', [this.settings.get_boolean('enable-animations')]).catch(() => {});
            this.connectSignal(this.settings, 'changed::enable-animations', animations);
            this.connectSignal(global.display, 'notify::focus-window', () => this.scheduleFocusCheck());
            this.connectSignal(global.stage, 'captured-event', (_actor, event) => {
                if (event.type() !== Clutter.EventType.BUTTON_PRESS && event.type() !== Clutter.EventType.TOUCH_BEGIN) return Clutter.EVENT_PROPAGATE;
                const ownButton = this.buttons.contains(event.get_source());
                if (ownButton) this.suppressedUntil = GLib.get_monotonic_time() + 250000;
                const [x, y] = event.get_coords();
                const active = this.active();
                const inFamily = this.family().some(window => {
                    const r = window.get_frame_rect();
                    const gutter = window === active.window ? window.protocol_to_stage_rect(new Mtk.Rectangle({x: 0, y: 0, width: 12, height: 12})).width : 0;
                    return x >= r.x + gutter && x < r.x + r.width - gutter && y >= r.y + gutter && y < r.y + r.height - gutter;
                });
                if (shouldDismiss({type: 'pointer', ownButton, inFamily}, active)) this.hideAll();
                return Clutter.EVENT_PROPAGATE;
            });
            this.connectSignal(Main.overview, 'showing', () => this.hideAll());
            this.connectSignal(global.workspace_manager, 'active-workspace-changed', () => this.hideAll());
            this.connectSignal(Main.sessionMode, 'updated', () => { if (Main.sessionMode.isLocked || Main.sessionMode.isGreeter) this.hideAll(); });
            this.connectSignal(Main.layoutManager, 'monitors-changed', () => this.placement.reposition());
            this.connectSignal(global.display, 'workareas-changed', () => this.placement.reposition());
            this.sendAnimations = animations;
            this.client.start();
        } catch (error) { console.error(`Workstation Widgets: ${error}`); this.disable(); }
    }
    disable() {
        if (this.reloadTimer) GLib.source_remove(this.reloadTimer);
        this.reloadTimer = 0;
        this.monitor?.cancel(); this.monitor = null;
        if (this.focusTimer) GLib.source_remove(this.focusTimer);
        this.focusTimer = 0;
        for (const [object, id] of this.signals || []) object.disconnect(id);
        this.signals = [];
        this.placement?.destroy(); this.buttons?.destroy(); this.client?.shutdown();
        this.client = null; this.buttons = null; this.placement = null;
        this.settings = null;
    }
    connectSignal(object, name, callback) { this.signals.push([object, object.connect(name, callback)]); }
    hideAll() { this.client?.call('widgets', 'hideAll').catch(() => {}); }
    active() {
        const snapshot = this.client?.snapshot;
        const id = snapshot?.selectedId;
        return {phase: snapshot?.widgets[id]?.phase || 'closed', window: id ? this.placement.find(snapshot, id) : null,
            ownButtonSuppressed: GLib.get_monotonic_time() < this.suppressedUntil};
    }
    family() {
        const active = this.active().window;
        if (!active) return [];
        return global.get_window_actors().map(actor => actor.meta_window).filter(window => {
            for (let current = window; current; current = current.get_transient_for()) if (current === active) return true;
            return false;
        });
    }
    scheduleFocusCheck() {
        if (this.focusTimer) GLib.source_remove(this.focusTimer);
        // Let the panel callback record the same user gesture before reacting to focus loss.
        this.focusTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
            this.focusTimer = 0;
            const active = this.active();
            if (active.ownButtonSuppressed) { this.scheduleFocusCheck(); return GLib.SOURCE_REMOVE; }
            if (shouldDismiss({type: 'focus', inFamily: this.family().includes(global.display.focus_window)}, active)) this.hideAll();
            return GLib.SOURCE_REMOVE;
        });
    }
}
