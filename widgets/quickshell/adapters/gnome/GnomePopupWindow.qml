import QtQuick
import Quickshell
FloatingWindow {
    id: root
    required property string widgetId
    required property var widgetState
    title: "workstation-widgets:" + widgetId
    visible: widgetState.phase !== "closed"
    color: "transparent"
    implicitWidth: widgetState.panelWidth + 24
    implicitHeight: widgetState.panelHeight + 24
    minimumSize: Qt.size(implicitWidth, implicitHeight)
    maximumSize: minimumSize
}
