import QtQuick
import Quickshell
import Quickshell.Io
Scope {
    id: root
    required property var hosts
    IpcHandler {
        target: "testSurfaces"
        function status(): string {
            return JSON.stringify(Array.from(root.hosts.instances, host => ({id: host.definition.id,
                visible: host.surface.visible, mapped: host.surface.backingWindowVisible,
                width: host.surface.width, height: host.surface.height,
                dpr: host.surface.devicePixelRatio, loaded: host.loaded})));
        }
    }
}
