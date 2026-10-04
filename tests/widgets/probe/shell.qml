import QtQuick
import Quickshell
ShellRoot {
    FloatingWindow {
        id: window
        title: "workstation-widgets:probe"
        visible: true
        color: "transparent"
        implicitWidth: 420; implicitHeight: 580
        minimumSize: Qt.size(420, 580); maximumSize: Qt.size(420, 580)
        Rectangle {
            anchors.fill: parent; color: "#242424"; radius: 16
            Text { anchors.centerIn: parent; text: "Quickshell runtime probe"; color: "white" }
        }
    }
    Timer {
        interval: 500; running: true
        onTriggered: {
            console.log("PROBE_STATUS " + JSON.stringify({width: window.width, height: window.height,
                dpr: window.devicePixelRatio, pid: Quickshell.processId, visible: window.visible}));
            Qt.exit(0);
        }
    }
}
