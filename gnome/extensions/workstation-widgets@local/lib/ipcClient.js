import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {acceptSnapshot} from './protocol.mjs';

export function socketPath(config) {
    const prefix = '$XDG_RUNTIME_DIR/';
    const path = config.socketPath?.startsWith(prefix)
        ? `${GLib.get_user_runtime_dir()}/${config.socketPath.slice(prefix.length)}` : config.socketPath;
    if (typeof path !== 'string' || !GLib.path_is_absolute(path)) throw new Error('Invalid widget socket path');
    return path;
}
function verifyEndpoint(path) {
    const file = Gio.File.new_for_path(path);
    // Owner read/write required; any group or other bit is rejected.
    for (const item of [file.get_parent(), file]) {
        const info = item.query_info('unix::uid,unix::mode', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null);
        const mode = info.get_attribute_uint32('unix::mode');
        if (info.get_attribute_uint32('unix::uid') !== new Gio.Credentials().get_unix_user()
            || (mode & 0o077) !== 0 || (mode & 0o600) !== 0o600)
            throw new Error('Widget socket ownership or permissions invalid');
    }
}

export class IpcClient {
    constructor(config, onSnapshot, onUnavailable) {
        this.config = config; this.onSnapshot = onSnapshot; this.onUnavailable = onUnavailable;
        this.snapshot = null; this.generation = 0; this.stopped = false; this.started = false;
        this.pending = new Map(); this.seq = 0; this.retry = 0; this.writes = [];
    }
    start() { if (!this.started && !this.stopped) { this.started = true; this.connect(); } }
    connect() {
        if (this.stopped) return;
        const generation = ++this.generation;
        this.cancel = new Gio.Cancellable(); this.buffer = new Uint8Array(); this.writing = false;
        const fail = () => this.disconnect(generation);
        this.handshake = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
            this.handshake = 0; fail(); return GLib.SOURCE_REMOVE;
        });
        try {
            const path = socketPath(this.config); verifyEndpoint(path);
            const client = new Gio.SocketClient();
            client.connect_async(new Gio.UnixSocketAddress({path}), this.cancel, (source, result) => {
                let connection;
                try {
                    connection = source.connect_finish(result);
                    if (this.stopped || generation !== this.generation) { connection.close(null); return; }
                    const credentials = connection.get_socket().get_credentials();
                    if (credentials.get_unix_user() !== new Gio.Credentials().get_unix_user()) throw new Error('Widget server UID differs');
                    this.peerPid = credentials.get_unix_pid(); this.connection = connection;
                    this.read(generation);
                    this.enqueue({protocolVersion: 2, type: 'hello', role: 'adapter'}, generation);
                } catch (_) { connection?.close(null); fail(); }
            });
        } catch (_) { fail(); }
    }
    read(generation) {
        this.connection.get_input_stream().read_bytes_async(8192, GLib.PRIORITY_DEFAULT, this.cancel, (stream, result) => {
            if (this.stopped || generation !== this.generation) return;
            try {
                const bytes = stream.read_bytes_finish(result).toArray();
                if (!bytes.length) throw new Error('Widget socket closed');
                const combined = new Uint8Array(this.buffer.length + bytes.length);
                combined.set(this.buffer); combined.set(bytes, this.buffer.length);
                let offset = 0;
                for (let i = 0; i < combined.length; i++) {
                    if (i - offset > 65536) throw new Error('Widget frame too large');
                    if (combined[i] !== 10) continue;
                    this.receive(JSON.parse(new TextDecoder().decode(combined.slice(offset, i))), generation);
                    if (this.stopped || generation !== this.generation) return;
                    offset = i + 1;
                }
                this.buffer = combined.slice(offset);
                if (this.buffer.length > 65536) throw new Error('Widget frame too large');
                this.read(generation);
            } catch (_) { this.disconnect(generation); }
        });
    }
    receive(frame, generation) {
        if (frame.protocolVersion !== 2) throw new Error('Unsupported widget protocol');
        if (frame.type === 'snapshot') {
            if (!acceptSnapshot(null, frame.state) || frame.state.pid !== this.peerPid
                || !frame.state.adapter.connected) throw new Error('Invalid widget snapshot');
            const snapshot = acceptSnapshot(this.snapshot, frame.state);
            if (this.handshake) GLib.source_remove(this.handshake);
            this.handshake = 0; this.retry = 0;
            if (snapshot) { this.snapshot = snapshot; this.onSnapshot(snapshot); }
        } else if (frame.type === 'reply') {
            const call = this.pending.get(frame.seq);
            if (!call || typeof frame.ok !== 'boolean') throw new Error('Unexpected widget reply');
            GLib.source_remove(call.timer); this.pending.delete(frame.seq);
            if (frame.ok) call.resolve(frame.result);
            else call.reject(new Error(frame.error || 'Widget command rejected'));
        } else throw new Error('Unexpected widget frame');
    }
    call(method, args = {}) {
        if (this.stopped || !this.snapshot || !this.connection) return Promise.reject(new Error('Widget adapter disconnected'));
        const seq = ++this.seq, generation = this.generation;
        return new Promise((resolve, reject) => {
            const timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
                const call = this.pending.get(seq);
                if (call) { this.pending.delete(seq); reject(new Error('Widget command timed out')); }
                this.disconnect(generation); return GLib.SOURCE_REMOVE;
            });
            this.pending.set(seq, {resolve, reject, timer});
            this.enqueue({protocolVersion: 2, type: 'command', seq, method, args}, generation);
        });
    }
    enqueue(frame, generation) {
        this.writes.push(new TextEncoder().encode(JSON.stringify(frame) + '\n'));
        this.writeNext(generation);
    }
    writeNext(generation) {
        if (this.writing || !this.writes.length || !this.connection || this.stopped) return;
        this.writing = true;
        this.connection.get_output_stream().write_all_async(this.writes.shift(), GLib.PRIORITY_DEFAULT, this.cancel, (stream, result) => {
            if (this.stopped || generation !== this.generation) return;
            try { stream.write_all_finish(result); this.writing = false; this.writeNext(generation); }
            catch (_) { this.disconnect(generation); }
        });
    }
    disconnect(generation) {
        if (this.stopped || generation !== this.generation) return;
        this.generation++; this.cleanup(); this.snapshot = null; this.onUnavailable();
        const delay = [250, 500, 1000, 2000][Math.min(this.retry++, 3)];
        this.reconnect = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => {
            this.reconnect = 0; this.connect(); return GLib.SOURCE_REMOVE;
        });
    }
    cleanup() {
        for (const name of ['handshake', 'reconnect']) { if (this[name]) GLib.source_remove(this[name]); this[name] = 0; }
        this.cancel?.cancel(); this.connection?.close(null); this.connection = null; this.writes = [];
        for (const call of this.pending.values()) { GLib.source_remove(call.timer); call.reject(new Error('Widget connection changed')); }
        this.pending.clear();
    }
    destroy() { this.stopped = true; this.generation++; this.cleanup(); this.snapshot = null; }
    shutdown() { this.destroy(); } // EOF tells the runtime to close immediately.
}
