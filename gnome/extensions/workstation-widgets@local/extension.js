import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {PanelButtons} from './lib/panelButtons.js';
import {IpcClient} from './lib/ipcClient.js';
import {WindowPlacement} from './lib/windowPlacement.js';
import {validateManifest} from './lib/manifest.mjs';

function readJson(path) {
    const [ok, bytes] = Gio.File.new_for_path(path).load_contents(null);
    if (!ok) throw new Error(`Cannot read ${path}`);
    return JSON.parse(new TextDecoder().decode(bytes));
}
export default class WorkstationWidgets extends Extension {
    enable() {
        try {
            const root = GLib.build_filenamev([GLib.get_user_config_dir(), 'workstation', 'widgets']);
            const config = readJson(`${root}/runtime.json`);
            if (config.schemaVersion !== 1 || config.adapter !== 'gnome' || config.configName !== 'workstation-widgets'
                || typeof config.qsPath !== 'string' || !GLib.path_is_absolute(config.qsPath)) throw new Error('Invalid widget runtime config');
            const entries = validateManifest(readJson(config.manifestPath));
            this.client = new IpcClient(config, snapshot => {
                this.buttons.update(snapshot); this.placement.update(snapshot);
            }, () => { this.buttons.update(null); this.placement.destroy(); });
            this.buttons = new PanelButtons(entries, (id, timestamp) => {
                this.placement.timestamp = timestamp;
                this.client.call('widgets', 'toggle', [id]).catch(error => console.error(`Workstation Widgets: ${error}`));
            });
            this.placement = new WindowPlacement(this.client, this.buttons);
            this.client.start();
        } catch (error) { console.error(`Workstation Widgets: ${error}`); this.disable(); }
    }
    disable() {
        this.client?.call('widgets', 'hideAll').catch(() => {});
        this.placement?.destroy(); this.buttons?.destroy(); this.client?.destroy();
        this.client = null; this.buttons = null; this.placement = null;
    }
}
