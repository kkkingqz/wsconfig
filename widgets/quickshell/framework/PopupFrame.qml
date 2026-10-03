import QtQuick
import QtQuick.Controls
Item {
    id: root
    required property var widgetState
    required property WidgetController controller
    required property string widgetId
    property alias body: body
    property real progress: 0
    readonly property real revealedHeight: height * progress
    readonly property bool scrollRequired: scroll.contentHeight > scroll.availableHeight
    function reconcile() {
        animation.stop();
        const phase = widgetState.phase;
        if (phase === "closed" || phase === "preparing") { progress = 0; return; }
        if (phase === "open") { progress = 1; return; }
        const target = phase === "opening" ? 1 : 0;
        animation.requestId = widgetState.requestId;
        animation.phase = phase;
        if (!controller.animationsEnabled || Math.abs(target - progress) < 0.001) {
            progress = target;
            Qt.callLater(finish, animation.requestId, phase);
        } else {
            animation.from = progress; animation.to = target;
            animation.duration = Style.animationMs * Math.abs(target - progress);
            animation.start();
        }
    }
    function finish(requestId, phase) { controller.dispatch({type: "FINISHED", id: widgetId, requestId, phase}); }
    // Lease renewals change snapshots; only target changes restart animation.
    readonly property string animationKey: widgetState.phase + ":" + widgetState.requestId
    onAnimationKeyChanged: reconcile()
    Connections { target: root.controller; function onAnimationsEnabledChanged() { root.reconcile(); } }
    NumberAnimation {
        id: animation
        property int requestId
        property string phase
        target: root; property: "progress"; easing.type: Easing.OutCubic
        onFinished: root.finish(requestId, phase)
    }
    Item {
        width: root.width; height: root.revealedHeight
        clip: true; opacity: root.progress
        Rectangle {
            width: root.width; height: root.height; radius: Style.radius
            color: Style.background
            ScrollView {
                id: scroll
                anchors.fill: parent; anchors.margins: Style.padding
                clip: true
                contentWidth: availableWidth
                contentHeight: body.height
                Item { id: body; width: scroll.availableWidth; height: Math.max(scroll.availableHeight, childrenRect.height) }
            }
        }
    }
}
