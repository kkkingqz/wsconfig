import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {buttonPresentation} from './buttons.mjs';
export class PanelButtons {
    constructor(entries, onToggle) {
        this.buttons = new Map();
        this.entries = new Map(entries.map(entry => [entry.id, entry]));
        for (const entry of entries.filter(e => e.enabled).sort((a, b) => a.panelOrder - b.panelOrder)) {
            const button = new PanelMenu.Button(0, entry.label, true);
            button.accessible_name = entry.label;
            button.widgetIcon = new St.Icon({icon_name: entry.iconName, style_class: 'system-status-icon'});
            button.add_child(button.widgetIcon);
            button.connect('button-press-event', () => { onToggle(entry.id, global.get_current_time()); return Clutter.EVENT_STOP; });
            button.connect('key-press-event', (_actor, event) => {
                if ([Clutter.KEY_Return, Clutter.KEY_space].includes(event.get_key_symbol())) { onToggle(entry.id, event.get_time()); return Clutter.EVENT_STOP; }
                return Clutter.EVENT_PROPAGATE;
            });
            Main.panel.addToStatusArea(`workstation-widget-${entry.id}`, button, entry.panelOrder, entry.panelPosition);
            this.buttons.set(entry.id, button);
        }
        this.update(null);
    }
    getButton(id) { return this.buttons.get(id); }
    contains(actor) { return [...this.buttons.values()].some(button => actor && (actor === button || button.contains(actor))); }
    update(snapshot) {
        for (const [id, button] of this.buttons) {
            const entry = this.entries.get(id);
            const presentation = buttonPresentation(snapshot, id, entry.label);
            button.reactive = presentation.reactive;
            button.accessible_name = presentation.accessibleName;
            button.widgetIcon.icon_name = presentation.error ? 'dialog-warning-symbolic' : entry.iconName;
            if (presentation.active) button.add_style_pseudo_class('active');
            else button.remove_style_pseudo_class('active');
        }
    }
    destroy() { for (const button of this.buttons.values()) button.destroy(); this.buttons.clear(); }
}
