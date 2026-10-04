import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
const loop = new GLib.MainLoop(null, false);
let connection;
new Gio.SocketClient().connect_async(new Gio.UnixSocketAddress({path: ARGV[0]}), null, (client, result) => {
    try {
        connection = client.connect_finish(result);
        const input = new Gio.DataInputStream({base_stream: connection.get_input_stream()});
        input.read_line_async(GLib.PRIORITY_DEFAULT, null, (stream, reply) => {
            const [line] = stream.read_line_finish_utf8(reply);
            if (line !== 'connected') throw new Error('unexpected greeting');
            print('ASYNC_CONNECTED');
        });
    } catch (error) { printerr(error); loop.quit(); }
});
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => { print('MAIN_LOOP_RESPONSIVE'); return GLib.SOURCE_REMOVE; });
loop.run();
