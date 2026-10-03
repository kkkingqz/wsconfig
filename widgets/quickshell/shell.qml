import QtQuick
import Quickshell
import "framework"
ShellRoot {
    WidgetRegistry { id: registry }
    WidgetController { id: widgetController; entries: registry.entries }
    WidgetIpc { controller: widgetController }
    Variants {
        model: registry.entries.filter(entry => entry.enabled)
        WidgetHost {
            required property var modelData
            definition: modelData
            controller: widgetController
        }
    }
}
