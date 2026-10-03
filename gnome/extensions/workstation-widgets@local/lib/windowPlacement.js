import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Mtk from 'gi://Mtk';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {placePopup} from './geometry.mjs';

export class WindowPlacement {
    constructor(client, buttons) { this.client = client; this.buttons = buttons; this.jobs = new Map(); this.timestamp = 0; this.generation = 0; }
    find(snapshot, id) {
        return global.get_window_actors().map(a => a.meta_window).find(w => w.get_pid() === snapshot.pid && w.get_title() === `workstation-widgets:${id}`);
    }
    update(snapshot) {
        this.snapshot = snapshot;
        for (const [key, job] of this.jobs) {
            const state = snapshot.widgets[job.id];
            const phases = job.reposition ? ['opening', 'open'] : ['preparing'];
            if (snapshot.instanceId !== job.instance || state?.requestId !== job.requestId || !phases.includes(state?.phase)) { GLib.source_remove(job.timer); this.jobs.delete(key); }
        }
        for (const [id, state] of Object.entries(snapshot.widgets)) {
            const key = `${snapshot.instanceId}:${id}:${state.requestId}`;
            if (state.phase !== 'preparing' || this.jobs.has(key)) continue;
            this.queueJob(id, state, snapshot);
        }
    }
    reposition() {
        const snapshot = this.snapshot;
        if (!snapshot?.selectedId) return;
        const state = snapshot.widgets[snapshot.selectedId];
        if (['opening', 'open'].includes(state.phase)) this.queueJob(snapshot.selectedId, state, snapshot, true);
    }
    queueJob(id, state, snapshot, reposition = false) {
            const key = `${snapshot.instanceId}:${id}:${state.requestId}`;
            if (this.jobs.has(key)) return;
            const job = {id, instance: snapshot.instanceId, requestId: state.requestId, start: GLib.get_monotonic_time(), busy: false, geometry: null, reposition};
            this.jobs.set(key, job);
            job.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 25, () => {
                if (GLib.get_monotonic_time() - job.start > 1900000) { this.jobs.delete(key); this.fail(job, 'GNOME placement timed out'); return GLib.SOURCE_REMOVE; }
                if (!job.busy) this.place(job, snapshot).catch(error => { this.fail(job, String(error)); });
                return GLib.SOURCE_CONTINUE;
            });
    }
    async place(job, snapshot) {
        const window = this.find(snapshot, job.id);
        const button = this.buttons.getButton(job.id);
        if (!window || !button) return;
        job.busy = true;
        try {
            const state = this.snapshot.widgets[job.id];
            const [x, y] = button.get_transformed_position();
            const [width, height] = button.get_transformed_size();
            const monitor = Main.layoutManager.findMonitorForActor(button);
            const area = window.get_work_area_for_monitor(monitor.index);
            const rect = r => new Mtk.Rectangle(r);
            const requested = window.protocol_to_stage_rect(rect({x: 0, y: 0, width: state.width + 24, height: state.height + 24}));
            const gutter = window.protocol_to_stage_rect(rect({x: 0, y: 0, width: 12, height: 12})).width;
            const position = placePopup({x, y, width, height}, area, requested, 8, gutter);
            const protocol = window.stage_to_protocol_rect(rect(position));
            const panelWidth = Math.max(1, protocol.width - 24), panelHeight = Math.max(1, protocol.height - 24);
            const signature = `${panelWidth}:${panelHeight}`;
            if (job.geometry !== signature) {
                if (await this.client.call('widgetAdapter', 'setGeometry', [job.id, job.requestId, panelWidth, panelHeight]) !== 'true') return;
                job.geometry = signature;
                return;
            }
            if (!this.jobs.has(`${job.instance}:${job.id}:${job.requestId}`)) return;
            window.hide_from_window_list();
            window.set_type(Meta.WindowType.DROPDOWN_MENU);
            window.make_above();
            window.move_resize_frame(false, position.x, position.y, position.width, position.height);
            const actual = window.get_frame_rect();
            if (['x', 'y', 'width', 'height'].some(k => Math.abs(actual[k] - position[k]) > 1)) return;
            if (job.reposition) {
                GLib.source_remove(job.timer);
                this.jobs.delete(`${job.instance}:${job.id}:${job.requestId}`);
            } else {
                window.activate(this.timestamp || global.get_current_time());
                await this.client.call('widgetAdapter', 'placed', [job.id, job.requestId]);
            }
        } finally { job.busy = false; }
    }
    fail(job, reason) { this.client.call('widgetAdapter', 'placementFailed', [job.id, job.requestId, reason]).catch(() => {}); }
    destroy() { this.generation++; for (const job of this.jobs.values()) GLib.source_remove(job.timer); this.jobs.clear(); this.snapshot = null; }
}
