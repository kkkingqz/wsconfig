pragma Singleton
import QtQuick
QtObject {
    property SystemPalette systemPalette: SystemPalette { colorGroup: SystemPalette.Active }
    property var theme: null
    readonly property int gutter: 12
    readonly property int padding: 16
    readonly property int radius: 16
    readonly property int animationMs: 300
    readonly property color background: theme ? theme.background : systemPalette.window
    readonly property color foreground: theme ? theme.foreground : systemPalette.windowText
    readonly property color mutedForeground: Qt.rgba(foreground.r, foreground.g, foreground.b, foreground.a * 0.7)
    function applyTheme(value) {
        if (theme?.background === value.background && theme?.foreground === value.foreground) return;
        theme = {background: value.background, foreground: value.foreground};
    }
}
