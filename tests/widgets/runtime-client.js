import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {IpcClient} from '../../gnome/extensions/workstation-widgets@local/lib/ipcClient.js';
const config = JSON.parse(GLib.getenv('WIDGETS_TEST_CONFIG'));
const delay = ms => new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => { resolve(); return GLib.SOURCE_REMOVE; }));
function assert(v, message) { if (!v) throw new Error(message); }
async function wait(test, timeout = 3000) {
    const deadline = GLib.get_monotonic_time() + timeout * 1000;
    while (!test()) { if (GLib.get_monotonic_time() > deadline) throw new Error('runtime state timed out'); await delay(25); }
}
const client = new IpcClient(config, () => {}, () => {});
try {
    // A public command may arrive before the adapter. No native surface may
    // map until the adapter has the verified PID and its effect guard installed.
    let initial;
    const bootDeadline = GLib.get_monotonic_time() + 3000000;
    while (!initial) {
        try { initial = JSON.parse(await client.call('widgets', 'status')); }
        catch (error) { if (GLib.get_monotonic_time() > bootDeadline) throw error; await delay(25); }
    }
    assert(!initial.adapter.ready, 'fresh runtime has no adapter');
    assert(await client.call('widgets', 'show', ['example']) === 'true', 'pre-adapter show accepted');
    await delay(100);
    const waiting = JSON.parse(await client.call('testSurfaces', 'status'));
    assert(waiting.every(surface => !surface.visible && !surface.mapped), 'no surface maps before adapter lease');
    await client.call('widgets', 'hideAll');
    for (const id of ['__proto__', 'constructor']) {
        assert(await client.call('widgets', 'hide', [id]) === 'false', 'inherited ID rejected in Qt runtime');
    }
    client.start();
    await wait(() => client.snapshot?.adapter.ready);
    assert(client.snapshot.pid === Number(GLib.getenv('WIDGETS_TEST_PID')), 'IPC addresses the launched runtime PID');
    for (const id of ['example', 'compact']) {
        assert(await client.call('widgets', 'show', [id]) === 'true', 'show accepted');
        await wait(() => client.snapshot.widgets[id].phase === 'preparing');
        const requestId = client.snapshot.widgets[id].requestId;
        assert(await client.call('widgetAdapter', 'placed', [id, requestId]) === 'true', 'placement accepted');
        if (id === 'example') {
            await wait(() => client.snapshot.widgets[id].phase === 'opening');
            const generation = client.generation, instance = client.snapshot.instanceId;
            client.listener.force_exit();
            await wait(() => client.generation > generation && client.snapshot?.adapter.ready);
            assert(client.snapshot.instanceId === instance && client.snapshot.widgets[id].requestId === requestId, 'reconnect preserves authoritative instance and request');
        }
        await wait(() => client.snapshot.widgets[id].phase === 'open');
        const surfaces = JSON.parse(await client.call('testSurfaces', 'status'));
        const surface = surfaces.find(s => s.id === id);
        assert(surface?.visible && surface.mapped && surface.loaded, 'actual surface mapped: ' + JSON.stringify(surfaces));
        assert(surface.width === client.snapshot.widgets[id].panelWidth + 24 && surface.height === client.snapshot.widgets[id].panelHeight + 24, 'actual surface dimensions');
        print('Actual surface: ' + JSON.stringify(surface));
        await delay(300);
        assert(await client.call('widgets', 'hide', [id]) === 'true', 'hide accepted');
        await wait(() => client.snapshot.widgets[id].phase === 'closed');
    }
    await client.call('widgets', 'show', ['example']);
    await wait(() => client.snapshot.widgets.example.phase === 'preparing');
    await client.call('widgetAdapter', 'placed', ['example', client.snapshot.widgets.example.requestId]);
    await wait(() => client.snapshot.widgets.example.phase === 'open');
    client.destroy();
    await delay(6200);
    const process = Gio.Subprocess.new([config.qsPath, '-c', config.configName, 'ipc', 'call', '--', 'widgets', 'status'], Gio.SubprocessFlags.STDOUT_PIPE);
    const output = await new Promise((resolve, reject) => process.communicate_utf8_async(null, null, (p, r) => { try { resolve(p.communicate_utf8_finish(r)[1]); } catch (e) { reject(e); } }));
    const state = JSON.parse(output);
    assert(state.widgets.example.phase === 'closed' && !state.adapter.ready, 'lease loss must unmap panel');
    print('Production registry, real GJS subscription, both animations and lease expiry passed');
} finally { client.destroy(); }
