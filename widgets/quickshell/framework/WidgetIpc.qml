import QtQuick
import Quickshell
import Quickshell.Io

Scope {
    required property WidgetController controller
    id: root
    IpcHandler {
        id: publicIpc
        target: "widgets"
        function toggle(id: string): bool { return root.controller.command("toggle", id); }
        function show(id: string): bool { return root.controller.command("show", id); }
        function hide(id: string): bool { return root.controller.command("hide", id); }
        function hideAll(): void { root.controller.command("hideAll", ""); }
        function status(): string { return root.controller.snapshotJson; }
        signal stateChanged(snapshot: string)
    }
    Connections {
        target: root.controller
        function onSnapshotJsonChanged() { publicIpc.stateChanged(root.controller.snapshotJson); }
    }
    IpcHandler {
        target: "widgetAdapter"
        function adapterReady(instanceId: string): bool { return root.controller.dispatch({type: "LEASE", instanceId}); }
        function renewAdapterLease(instanceId: string): bool { return root.controller.dispatch({type: "LEASE", instanceId}); }
        function placed(id: string, requestId: int): bool { return root.controller.dispatch({type: "PLACED", id, requestId}); }
        function placementFailed(id: string, requestId: int, reason: string): bool { return root.controller.dispatch({type: "FAILED", id, requestId, reason}); }
        function setGeometry(id: string, requestId: int, width: int, height: int): bool { return root.controller.dispatch({type: "GEOMETRY", id, requestId, width, height}); }
        function setAnimationsEnabled(enabled: bool): void { root.controller.animationsEnabled = enabled; }
    }
}
