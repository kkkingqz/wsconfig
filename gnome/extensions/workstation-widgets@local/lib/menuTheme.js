import GLib from 'gi://GLib';

function qtColor(color) {
    // Cogl uses RGBA bytes; Qt's eight-digit notation is ARGB.
    return '#' + [color.alpha, color.red, color.green, color.blue]
        .map(value => value.toString(16).padStart(2, '0')).join('');
}
export class MenuTheme {
    constructor(client, actor, context) {
        this.client = client; this.actor = actor; this.context = context;
        this.idle = 0; this.signature = null; this.stopped = false; this.reading = false;
        this.actorSignal = actor.connect('style-changed', () => this.schedule());
        this.contextSignal = context.connect('changed', () => this.schedule());
    }
    schedule() {
        if (this.stopped || this.reading || this.idle) return;
        this.idle = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this.idle = 0; this.sync(); return GLib.SOURCE_REMOVE;
        });
    }
    sync() {
        if (this.stopped || !this.client.snapshot) return;
        let palette;
        this.reading = true;
        try {
            const node = this.actor.get_theme_node();
            palette = {background: qtColor(node.get_background_color()), foreground: qtColor(node.get_foreground_color())};
        } finally { this.reading = false; }
        const signature = `${this.client.snapshot.instanceId}:${this.client.generation}:${JSON.stringify(palette)}`;
        if (this.signature === signature) return;
        this.signature = signature;
        this.client.call('setTheme', palette).catch(() => {
            if (this.signature === signature) this.signature = null;
        });
    }
    destroy() {
        if (this.stopped) return;
        this.stopped = true;
        if (this.idle) GLib.source_remove(this.idle);
        this.idle = 0;
        this.actor.disconnect(this.actorSignal); this.context.disconnect(this.contextSignal);
    }
}
