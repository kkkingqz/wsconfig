import QtQuick
import Quickshell
import "model.mjs" as Model

Scope {
    id: root
    property var entries: []
    readonly property string instanceId: Quickshell.processId + "-" + Date.now()
    property var state: Model.createState(entries, instanceId, Quickshell.processId)
    readonly property string snapshotJson: JSON.stringify(state)
    property bool animationsEnabled: true
    property real testNow: -1
    signal effectRequested(var effect)
    ElapsedTimer { id: clock }
    Component.onCompleted: clock.restart()
    onEntriesChanged: state = Model.createState(entries, instanceId, Quickshell.processId)

    function dispatch(event): bool {
        const result = Model.reduce(state, event, testNow >= 0 ? testNow : clock.elapsedMs());
        state = result.state;
        for (const effect of result.effects) effectRequested(effect);
        return result.accepted;
    }
    function command(action: string, id: string): bool {
        return dispatch({type: "COMMAND", action, id});
    }
    Timer {
        interval: 50
        repeat: true
        running: root.testNow < 0 && (root.state.selectedId !== null || root.state.adapter.ready)
        onTriggered: root.dispatch({type: "TICK"})
    }
}
