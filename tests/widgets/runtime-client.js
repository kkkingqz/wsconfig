import GLib from 'gi://GLib';
import System from 'system';
import {IpcClient} from '../../gnome/extensions/workstation-widgets@local/lib/ipcClient.js';
const config = JSON.parse(GLib.getenv('WIDGETS_TEST_CONFIG'));
const delay = ms => new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => { resolve(); return GLib.SOURCE_REMOVE; }));
function assert(v, message) { if (!v) throw new Error(message); }
async function wait(test, timeout = 5000) {
    const deadline = GLib.get_monotonic_time() + timeout * 1000;
    while (!test()) { if (GLib.get_monotonic_time() > deadline) throw new Error('runtime state timed out'); await delay(20); }
}
const client = new IpcClient(config, () => {}, () => {});
async function run() {
try {
    client.start(); await wait(() => client.snapshot?.adapter.connected);
    if (GLib.getenv('WIDGETS_IDLE_SECONDS')) {
        print('IDLE_READY');
        await delay(Number(GLib.getenv('WIDGETS_IDLE_SECONDS')) * 1000);
    } else {
        assert(client.snapshot.pid === Number(GLib.getenv('WIDGETS_TEST_PID')), 'socket addresses launched PID');
        for (const id of ['example', 'compact']) {
            assert(await client.call('toggle', {id}) === true, 'toggle accepted');
            await wait(() => client.snapshot.widgets[id].phase === 'preparing');
            await delay(100); // Let the surface map before manual acknowledgement.
            const requestId = client.snapshot.widgets[id].requestId;
            assert(await client.call('placed', {id, requestId}) === true, 'placement accepted');
            await wait(() => client.snapshot.widgets[id].phase === 'open');
            await delay(250);
            if (id === 'example') {
                const instance = client.snapshot.instanceId;
                print('RESTART_READY');
                await wait(() => client.snapshot?.adapter.connected && client.snapshot.instanceId !== instance);
                assert(client.snapshot.widgets[id].phase === 'closed', 'restart restores closed state');
                print('RESTART_PASSED');
            } else {
                assert(await client.call('toggle', {id}) === true, 'second click closes');
                await wait(() => client.snapshot.widgets[id].phase === 'closed');
            }
        }
        await client.call('toggle', {id:'example'});
        await wait(() => client.snapshot.widgets.example.phase === 'preparing');
        await client.call('placed', {id:'example', requestId:client.snapshot.widgets.example.requestId});
        await wait(() => client.snapshot.widgets.example.phase === 'open');
        await delay(100);
        print('OPEN_BEFORE_EOF');
    }
} finally { client.destroy(); }

}
// Shell has a normal GLib main loop. Top-level await in standalone GJS can
// spin while waiting; use the same event-loop setup for honest idle metrics.
const loop = new GLib.MainLoop(null, false);
let exitCode = 0;
run().then(() => loop.quit(), error => { printerr(error.stack); exitCode = 1; loop.quit(); });
loop.run();
System.exit(exitCode);
