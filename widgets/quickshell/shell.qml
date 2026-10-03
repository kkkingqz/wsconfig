import QtQuick
import Quickshell
import "framework"
ShellRoot {
    WidgetRegistry { id: registry }
    WidgetController { id: controller; entries: registry.entries }
    WidgetIpc { controller: controller }
    Variants {
        model: registry.entries.filter(entry => entry.enabled)
        WidgetHost {
            required property var modelData
            definition: modelData
            controller: controller
        }
    }
}
