import QtQuick
import Quickshell
import "framework"

ShellRoot {
    WidgetController {
        id: controller
        entries: [{id: "example", enabled: true, width: 420, height: 580}]
        testNow: 0
    }
    WidgetIpc { controller: controller }
    Timer {
        interval: 50; running: Quickshell.env("WIDGETS_IPC_TEST") !== "1"
        onTriggered: {
            if (controller.command("show", "missing")) Qt.exit(1);
            if (!controller.command("show", "example")) Qt.exit(1);
            const id = controller.state.widgets.example.requestId;
            if (!controller.dispatch({type: "PLACED", id: "example", requestId: id})) Qt.exit(1);
            if (controller.state.widgets.example.phase !== "opening") Qt.exit(1);
            console.log("QML controller/IPC smoke passed");
            Qt.exit(0);
        }
    }
}
