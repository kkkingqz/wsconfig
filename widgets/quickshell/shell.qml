import QtQuick
import Quickshell
import "framework"
ShellRoot {
    id: root
    // The config is a live symlink into the repository: a checkout or edit would
    // hot-reload the runtime, and the reloaded SocketServer loses its socket.
    settings.watchFiles: false
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
