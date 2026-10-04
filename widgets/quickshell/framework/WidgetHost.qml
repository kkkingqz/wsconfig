import QtQuick
import Quickshell
import "../adapters/gnome"
Scope {
    id: root
    required property var definition
    required property WidgetController controller
    readonly property var widgetState: controller.state.widgets[definition.id]
    property alias surface: window
    property alias widgetContext: context
    readonly property bool loaded: loader.status === Loader.Ready
    readonly property real progress: frame.progress
    readonly property bool scrollRequired: frame.scrollRequired
    property bool loadRequested: false
    onWidgetStateChanged: { if (widgetState && widgetState.phase === "preparing") loadRequested = true; }
    onLoadRequestedChanged: { if (loadRequested) Qt.callLater(loadContent); }
    function loadContent() {
        if (loader.status === Loader.Null) loader.setSource(Qt.resolvedUrl("../" + definition.component), {context});
    }
    QtObject {
        id: context
        readonly property string widgetId: root.definition.id
        readonly property int contentWidth: Math.max(0, root.widgetState.panelWidth - Style.padding * 2)
        readonly property int contentHeight: Math.max(0, root.widgetState.panelHeight - Style.padding * 2)
        readonly property real devicePixelRatio: window.devicePixelRatio
        readonly property string phase: root.widgetState.phase
        function requestClose() { root.controller.command("hide", widgetId); }
    }
    GnomePopupWindow {
        id: window
        widgetId: root.definition.id
        widgetState: root.widgetState
        adapterReady: root.controller.state.adapter.connected
        mask: Region { x: Style.gutter; y: Style.gutter; width: frame.width; height: Math.floor(frame.revealedHeight); radius: Style.radius }
        onClosed: context.requestClose()
        PopupFrame {
            id: frame
            x: Style.gutter; y: Style.gutter
            width: root.widgetState.panelWidth; height: root.widgetState.panelHeight
            widgetId: root.definition.id; widgetState: root.widgetState; controller: root.controller
            focus: true
            Keys.onEscapePressed: event => { context.requestClose(); event.accepted = true; }
        }
        Loader {
            id: loader
            parent: frame.body
            width: context.contentWidth
            onStatusChanged: {
                if (status === Loader.Error) root.controller.dispatch({type: "AVAILABLE", id: root.definition.id, value: false, reason: "QML component failed"});
            }
        }
    }
}
