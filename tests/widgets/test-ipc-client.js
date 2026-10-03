import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {IpcClient} from '../../gnome/extensions/workstation-widgets@local/lib/ipcClient.js';
const config = {qsPath: '/unused/qs', configName: 'test'};
function assert(v) { if (!v) throw new Error('IPC transport assertion'); }
function spawn(command) { return Gio.Subprocess.new(command, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE); }
export const tests = {
    argumentArrayAndQueue: async () => {
        const calls = [];
        const client = new IpcClient(config, () => {}, () => {}, args => { calls.push(args); return spawn([GLib.find_program_in_path('sh'), '-c', 'printf true']); });
        const results = await Promise.all([client.call('widgets', 'show', ['id with spaces']), client.call('widgets', 'hide', ['id with spaces'])]);
        assert(results.every(r => r === 'true') && calls[0].slice(-2).join('|') === 'show|id with spaces' && calls[1].slice(-2).join('|') === 'hide|id with spaces');
        client.destroy();
    },
    timeout: async () => {
        const client = new IpcClient(config, () => {}, () => {}, () => spawn([GLib.find_program_in_path('sleep'), '10']));
        const start = GLib.get_monotonic_time();
        let failed = false;
        try { await client.call('widgets', 'status'); } catch (_) { failed = true; }
        assert(failed && GLib.get_monotonic_time() - start < 3000000);
        client.destroy();
    },
    staleReader: () => {
        let received = 0;
        const client = new IpcClient(config, () => received++, () => {});
        client.generation = 2;
        client.receive('invalid JSON', 1);
        assert(received === 0);
        client.destroy();
    },
};
