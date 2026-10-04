import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {createState, reduce} from '../../widgets/quickshell/framework/model.mjs';
import {shouldDismiss} from '../../gnome/extensions/workstation-widgets@local/lib/dismissal.mjs';

const assert = (value, message) => { if (!value) throw Error(message); };
// Meta, Mtk and Main require a running Shell. Substitute only these native
// boundaries; execute the production placement class and real runtime reducer.
const sourceFile = Gio.File.new_for_uri(import.meta.url).get_parent().resolve_relative_path('../../gnome/extensions/workstation-widgets@local/lib/windowPlacement.js');
const geometryUri = sourceFile.get_parent().get_child('geometry.mjs').get_uri();
const source = new TextDecoder().decode(sourceFile.load_contents(null)[1])
    .replace("import Meta from 'gi://Meta';", 'const Meta = {WindowType: {DROPDOWN_MENU: 1}};')
    .replace("import Mtk from 'gi://Mtk';", 'const Mtk = {Rectangle: class {constructor(rect) {Object.assign(this, rect);}}};')
    .replace("import * as Main from 'resource:///org/gnome/shell/ui/main.js';", 'const Main = {layoutManager: {findMonitorForActor: () => ({index: 0})}};')
    .replace("from './geometry.mjs'", `from '${geometryUri}'`);
const dir = Gio.File.new_for_path(GLib.dir_make_tmp('widget-placement-XXXXXX'));
const moduleFile = dir.get_child('placement.js');
moduleFile.replace_contents(new TextEncoder().encode(source), null, false, Gio.FileCreateFlags.NONE, null);
let WindowPlacement;
try { ({WindowPlacement} = await import(moduleFile.get_uri())); }
finally { moduleFile.delete(null); dir.delete(null); }

async function fixture(run) {
    const previousGlobal = globalThis.global;
    const shell = {display: {focus_window: {}}, get_current_time: () => 1000};
    globalThis.global = shell;
    let state = createState([{id: 'example', enabled: true, width: 420, height: 580}, {id: 'compact', enabled: true, width: 320, height: 240}], 'runtime', 42);
    const activationTimes = [];
    let grantFocus = false;
    const windows = Object.fromEntries(['example', 'compact'].map(id => [id, {
        get_pid: () => 42, get_title: () => `workstation-widgets:${id}`,
        get_work_area_for_monitor: () => ({x: 0, y: 0, width: 1920, height: 1080}),
        protocol_to_stage_rect: r => r, stage_to_protocol_rect: r => r,
        hide_from_window_list() {}, set_type() {}, make_above() {},
        move_resize_frame(_user, x, y, width, height) { this.frame = {x, y, width, height}; },
        get_frame_rect() { return this.frame; },
        activate(timestamp) { activationTimes.push(timestamp); if (grantFocus) shell.display.focus_window = this; },
    }]));
    shell.get_window_actors = () => Object.values(windows).map(meta_window => ({meta_window}));
    const button = {get_transformed_position: () => [900, 0], get_transformed_size: () => [30, 30]};
    let placement;
    const dispatch = event => { state = reduce(state, event, 0).state; placement.update(state); };
    placement = new WindowPlacement({call: async (method, args) => {
        const type = {setGeometry: 'GEOMETRY', placed: 'PLACED', placementFailed: 'FAILED'}[method];
        const result = reduce(state, {type, ...args}, 0);
        state = result.state; placement.update(state); return result.accepted;
    }}, {getButton: () => button});
    dispatch({type: 'ADAPTER_CONNECTED'});
    const prepare = async id => {
        dispatch({type: 'COMMAND', action: 'show', id});
        const job = [...placement.jobs.values()][0];
        await placement.place(job, state); // geometry handshake
        return job;
    };
    try { await run({placement, shell, windows, activationTimes, prepare, dispatch, state: () => state, grantFocus: () => {grantFocus = true;}}); }
    finally { placement.destroy(); if (previousGlobal === undefined) delete globalThis.global; else globalThis.global = previousGlobal; }
}
export const tests = {
    openingWaitsForNativeFocus: () => fixture(async ({placement, shell, windows, prepare, state}) => {
        const job = await prepare('example');
        await placement.place(job, state());
        assert(state().widgets.example.phase === 'preparing', 'placed starts animation before native focus is acquired');
        assert(!shouldDismiss({type: 'focus', inFamily: false}, {phase: state().widgets.example.phase}), 'old window focus loss dismisses new preparation');
        shell.display.focus_window = windows.example;
        await placement.place(job, state());
        assert(state().widgets.example.phase === 'opening', 'focus acquisition does not release opening');
        shell.display.focus_window = {};
        assert(shouldDismiss({type: 'focus', inFamily: false}, {phase: state().widgets.example.phase}), 'real focus loss after opening no longer dismisses');
    }),
    clickTimestampIsNotReusedForCliOpen: () => fixture(async ({placement, prepare, state, dispatch, activationTimes, grantFocus}) => {
        grantFocus(); placement.timestamp = 77;
        let job = await prepare('example'); await placement.place(job, state());
        dispatch({type: 'COMMAND', action: 'hide', id: 'example'});
        dispatch({type: 'FINISHED', id: 'example', requestId: state().widgets.example.requestId, phase: 'closing'});
        job = await prepare('compact'); await placement.place(job, state());
        assert(activationTimes.join(',') === '77,1000', `stale click timestamp activates later CLI window: ${activationTimes}`);
    }),
    closingClickDoesNotLeaveAnActivationTimestamp: () => fixture(async ({placement, prepare, state, dispatch, activationTimes, grantFocus}) => {
        grantFocus(); placement.timestamp = 77;
        let job = await prepare('example'); await placement.place(job, state());
        placement.timestamp = 88; // second panel click closes; no placement job
        dispatch({type: 'COMMAND', action: 'hide', id: 'example'});
        dispatch({type: 'FINISHED', id: 'example', requestId: state().widgets.example.requestId, phase: 'closing'});
        job = await prepare('compact'); await placement.place(job, state());
        assert(activationTimes.join(',') === '77,1000', `closing click leaks its timestamp to CLI: ${activationTimes}`);
    }),
    queuedSwitchKeepsItsOwnClickTimestamp: () => fixture(async ({placement, prepare, state, dispatch, activationTimes, grantFocus}) => {
        grantFocus(); placement.timestamp = 77;
        let job = await prepare('example'); await placement.place(job, state());
        placement.timestamp = 88;
        dispatch({type: 'COMMAND', action: 'show', id: 'compact'});
        dispatch({type: 'FINISHED', id: 'example', requestId: state().widgets.example.requestId, phase: 'closing'});
        job = [...placement.jobs.values()][0];
        await placement.place(job, state()); await placement.place(job, state());
        assert(activationTimes.join(',') === '77,88', 'pending switch loses its own panel gesture');
    }),
    missingFocusUsesExistingPlacementTimeout: () => fixture(async ({prepare, state, placement}) => {
        await prepare('example');
        await new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2100, () => {resolve(); return GLib.SOURCE_REMOVE;}));
        assert(state().widgets.example.phase === 'closed', 'unfocused popup never times out');
        assert(state().lastError?.id === 'example', 'missing focus timeout is not reported');
        assert(placement.jobs.size === 0, 'placement timer survives failed opening');
    }),
    repositionDoesNotStealFocus: () => fixture(async ({placement, shell, prepare, state, grantFocus}) => {
        grantFocus(); const job = await prepare('example'); await placement.place(job, state());
        const other = {}; shell.display.focus_window = other;
        placement.reposition(); const reposition = [...placement.jobs.values()][0];
        await placement.place(reposition, state()); await placement.place(reposition, state());
        assert(shell.display.focus_window === other, 'reposition steals focus');
        assert(placement.jobs.size === 0, 'reposition waits for unrelated focus');
    }),
};
