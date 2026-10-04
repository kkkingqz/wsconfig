// Test-only observer: stdout, never an IPC handler in the production runtime.
import QtQuick
import Quickshell
Scope {
    id: root
    required property var hosts
    property string previous: ""
    Timer {
        interval: 40; repeat: true; running: true
        onTriggered: {
            const value = JSON.stringify(Array.from(root.hosts.instances, host => ({id: host.definition.id,
                visible: host.surface.visible, mapped: host.surface.backingWindowVisible,
                width: host.surface.width, height: host.surface.height,
                dpr: host.surface.devicePixelRatio, loaded: host.loaded})));
            if (value !== root.previous) { root.previous = value; console.log("TEST_SURFACES " + value); }
        }
    }
}
