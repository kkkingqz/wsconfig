import QtQuick
import Quickshell
import "framework"
ShellRoot {
    id: root
    property var definitions: []
    function configure() {
        if (!widgetController) return;
        // Populate lifecycle state before Variants constructs any window.
        widgetController.entries = registry.entries;
        definitions = registry.entries;
    }
    Component.onCompleted: configure()
    WidgetRegistry { id: registry; onEntriesChanged: root.configure() }
    WidgetController { id: widgetController }
    WidgetIpc { controller: widgetController }
    Variants {
        model: root.definitions.filter(entry => entry.enabled)
        WidgetHost {
            required property var modelData
            definition: modelData
            controller: widgetController
        }
    }
}
