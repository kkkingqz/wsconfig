import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
    FloatingWindow {
        id: window
        title: "workstation-widgets:probe"
        visible: false
        color: "transparent"
        implicitWidth: 420
        implicitHeight: 580
        minimumSize: Qt.size(420, 580)
        maximumSize: Qt.size(420, 580)

        Rectangle {
            anchors.fill: parent
            color: "#242424"
            radius: 16
            Text { anchors.centerIn: parent; text: "Quickshell runtime probe"; color: "white" }
        }
        IpcHandler {
            target: "probe"
            function status(): string {
                return JSON.stringify({width: window.width, height: window.height,
                    dpr: window.devicePixelRatio, pid: Quickshell.processId, visible: window.visible});
            }
            function show(): void { window.visible = true; stateChanged(status()); }
            function hide(): void { window.visible = false; stateChanged(status()); }
            signal stateChanged(snapshot: string);
        }
    }
}
