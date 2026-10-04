import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
    SocketServer {
        active: true
        path: Quickshell.env("WIDGETS_SOCKET")
        handler: Socket {
            id: peer
            onConnectedChanged: {
                console.log(connected ? "CONNECTED" : "EOF");
                if (connected) { write("connected\n"); flush(); }
            }
            parser: SplitParser {
                onRead: line => { peer.write(line + "\n"); peer.flush(); }
            }
        }
    }
}
