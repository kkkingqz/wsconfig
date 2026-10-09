import QtQuick
import Quickshell
import Quickshell.Io
import "wire.mjs" as Wire

Scope {
    id: root
    required property WidgetController controller
    property var adapter: null
    // The service runs with UMask=0077 inside a 0700 runtime directory, so the
    // socket is created owner-only (0700); clients verify that before connecting.
    readonly property string socketPath: Quickshell.env("WIDGETS_SOCKET") || Quickshell.env("XDG_RUNTIME_DIR") + "/workstation-widgets/control.sock"
    function execute(method, args) {
        switch (method) {
        case "status": return controller.state;
        case "show": case "hide": case "toggle": case "hideAll": return controller.command(method, args.id || "");
        case "placed": return controller.dispatch({type: "PLACED", id: args.id, requestId: args.requestId});
        case "placementFailed": return controller.dispatch({type: "FAILED", id: args.id, requestId: args.requestId, reason: args.reason});
        case "setGeometry": return controller.dispatch({type: "GEOMETRY", id: args.id, requestId: args.requestId, width: args.width, height: args.height});
        case "setAnimations": controller.animationsEnabled = args.enabled; return true;
        case "setTheme": Style.applyTheme(args); return true;
        }
    }
    Connections {
        target: root.controller
        function onSnapshotJsonChanged() { if (root.adapter) root.adapter.snapshot(); }
    }
    SocketServer {
        id: server
        path: root.socketPath
        active: true
        handler: Socket {
            id: peer
            property string role: ""
            property bool used: false
            property bool rejected: false
            function closePeer() { rejected = true; connected = false; }
            function send(frame) { write(JSON.stringify(Object.assign({protocolVersion: 2}, frame)) + "\n"); flush(); }
            function snapshot() { send({type: "snapshot", state: root.controller.state}); }
            onConnectedChanged: {
                if (!connected) rejected = true;
                if (!connected && root.adapter === peer) {
                    root.adapter = null;
                    root.controller.dispatch({type: "ADAPTER_DISCONNECTED"});
                }
            }
            function receive(line) {
                if (rejected) return;
                let frame;
                try { frame = JSON.parse(line); } catch (_) { closePeer(); return; }
                if (!role) {
                    const next = Wire.validateHello(frame);
                    if (!next) { closePeer(); return; }
                    role = next;
                    if (role === "adapter") {
                        const old = root.adapter;
                        root.adapter = peer;
                        if (old) old.closePeer();
                        // Dispatch broadcasts the initial snapshot on first connection.
                        const revision = root.controller.state.revision;
                        root.controller.dispatch({type: "ADAPTER_CONNECTED"});
                        if (root.controller.state.revision === revision) snapshot();
                    } else send({type: "hello", pid: root.controller.state.pid, instanceId: root.controller.state.instanceId});
                    return;
                }
                if ((role === "adapter" && root.adapter !== peer) || (role === "cli" && used)) { closePeer(); return; }
                used = true;
                if (!Wire.validateCommand(frame, role)) {
                    send({type: "reply", seq: frame?.seq || 0, ok: false, error: "invalid or unauthorized command"});
                    if (role === "cli") closePeer();
                    return;
                }
                send({type: "reply", seq: frame.seq, ok: true, result: root.execute(frame.method, frame.args)});
                if (role === "cli") closePeer();
            }
            // Split complete byte lines before decoding UTF-8. Decoding each
            // arbitrary chunk loses code points split across socket reads.
            parser: SplitParser {
                onRead: line => {
                    if (peer.rejected) return;
                    if (line.length > 65536) { peer.closePeer(); return; }
                    peer.receive(line);
                }
            }
        }
    }
}
