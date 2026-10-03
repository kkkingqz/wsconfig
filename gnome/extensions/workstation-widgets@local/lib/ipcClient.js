import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {acceptSnapshot} from './protocol.mjs';

export class IpcClient {
    constructor(config, onSnapshot, onUnavailable, spawn = args => Gio.Subprocess.new(args, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE)) {
        this.config = config; this.onSnapshot = onSnapshot; this.onUnavailable = onUnavailable;
        this.spawn = spawn; this.snapshot = null; this.generation = 0; this.stopped = false;
        this.queue = Promise.resolve(); this.calls = new Set(); this.retry = 0;
    }
    args() { return [this.config.qsPath, '-c', this.config.configName, 'ipc']; }
    async call(target, method, args = []) {
        const generation = this.generation;
        const run = async () => {
            if (this.stopped || generation !== this.generation) throw new Error('IPC connection changed');
            const process = this.spawn([...this.args(), 'call', '--', target, method, ...args.map(String)]);
            const cancellable = new Gio.Cancellable();
            const record = {process, cancellable, timer: 0}; this.calls.add(record);
            record.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => { record.timer = 0; cancellable.cancel(); process.force_exit(); return GLib.SOURCE_REMOVE; });
            try {
                return await new Promise((resolve, reject) => process.communicate_utf8_async(null, cancellable, (p, result) => {
                    try {
                        const [, stdout, stderr] = p.communicate_utf8_finish(result);
                        if (!p.get_successful()) throw new Error(stderr.trim() || 'IPC call failed');
                        if (generation !== this.generation || this.stopped) throw new Error('stale IPC reply');
                        resolve(stdout.trim());
                    } catch (error) { reject(error); }
                }));
            } finally { if (record.timer) GLib.source_remove(record.timer); this.calls.delete(record); }
        };
        const promise = this.queue.then(run);
        this.queue = promise.catch(() => {});
        return promise;
    }
    start() { this.connect(); }
    receive(line, generation) {
        if (this.stopped || generation !== this.generation) return;
        const snapshot = acceptSnapshot(this.snapshot, JSON.parse(line));
        if (snapshot) { this.snapshot = snapshot; this.onSnapshot(snapshot); }
    }
    async connect() {
        const generation = ++this.generation;
        try {
            this.listener = this.spawn([...this.args(), 'listen', '--', 'widgets', 'stateChanged']);
            this.readerCancel = new Gio.Cancellable();
            const stream = new Gio.DataInputStream({base_stream: this.listener.get_stdout_pipe()});
            const read = () => stream.read_line_async(GLib.PRIORITY_DEFAULT, this.readerCancel, (s, result) => {
                if (generation !== this.generation || this.stopped) return;
                try {
                    const [line] = s.read_line_finish_utf8(result);
                    if (line === null) throw new Error('IPC listener ended');
                    this.receive(line, generation); read();
                } catch (_) { this.disconnect(generation); }
            });
            read();
            // Install the reader before requesting the authoritative snapshot.
            this.receive(await this.call('widgets', 'status'), generation);
            if (!this.snapshot) throw new Error('invalid runtime snapshot');
            const ok = await this.call('widgetAdapter', 'adapterReady', [this.snapshot.instanceId]);
            if (ok !== 'true') throw new Error('adapter rejected');
            if (generation !== this.generation || this.stopped) return;
            this.retry = 0;
            this.lease = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
                this.call('widgetAdapter', 'renewAdapterLease', [this.snapshot.instanceId]).catch(() => this.disconnect(generation));
                return GLib.SOURCE_CONTINUE;
            });
        } catch (_) { this.disconnect(generation); }
    }
    disconnect(generation) {
        if (this.stopped || generation !== this.generation) return;
        this.cleanup(); this.generation++; this.snapshot = null; this.onUnavailable();
        const delay = [250, 500, 1000, 2000][Math.min(this.retry++, 3)];
        this.reconnect = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => { this.reconnect = 0; this.connect(); return GLib.SOURCE_REMOVE; });
    }
    cleanup() {
        for (const name of ['lease', 'reconnect']) { if (this[name]) GLib.source_remove(this[name]); this[name] = 0; }
        this.readerCancel?.cancel(); this.listener?.force_exit(); this.listener = null;
        for (const record of this.calls) { if (record.timer) GLib.source_remove(record.timer); record.timer = 0; record.cancellable.cancel(); record.process.force_exit(); }
    }
    destroy() { this.stopped = true; this.generation++; this.cleanup(); this.snapshot = null; }
}
