import QtQuick
import Quickshell
import "framework"

ShellRoot {
    function backgroundOf(host) {
        function find(item) {
            if (item.color !== undefined) return item.color;
            for (const child of item.children || []) {
                const color = find(child);
                if (color !== null) return color;
            }
            return null;
        }
        return find(host.surface.contentItem);
    }
    WidgetController {
        id: controller
        entries: [{id: "example", enabled: true, width: 420, height: 580}]
        testNow: Quickshell.env("WIDGETS_IPC_TEST") === "1" ? -1 : 0
    }
    WidgetIpc { controller: controller }
    WidgetController {
        id: panels
        entries: [
            {id: "large", enabled: true, width: 420, height: 580, component: "widgets/example/Widget.qml"},
            {id: "small", enabled: true, width: 320, height: 240, component: "widgets/compact/Widget.qml", unloadOnClose: true},
            {id: "broken", enabled: true, width: 100, height: 100, component: "broken/Widget.qml"}]
        testNow: 0
    }
    WidgetHost { id: large; definition: panels.entries[0]; controller: panels }
    WidgetHost { id: small; definition: panels.entries[1]; controller: panels }
    WidgetHost { definition: panels.entries[2]; controller: panels }
    Connections {
        target: Style
        function onThemeChanged() {
            if (Quickshell.env("WIDGETS_IPC_TEST") !== "1") return;
            if (!Qt.colorEqual(backgroundOf(large), Style.theme.background)
                || !Qt.colorEqual(large.widgetContext.foreground, Style.theme.foreground)) {
                console.error("socket theme did not reach popup/content"); Qt.exit(1);
            }
            console.log("QML native theme applied: " + Style.background + "/" + Style.foreground);
        }
    }
    Timer {
        id: gentleStart
        interval: 60
        onTriggered: {
            if (!(small.progress > 0 && small.progress < 0.3)) {
                console.error("reveal must start gently; progress=" + small.progress);
                Qt.exit(1);
                return;
            }
            const progress = small.progress;
            panels.command("toggle", "small");
            if (panels.state.widgets.small.phase !== "closing" || small.progress !== progress) Qt.exit(1);
            panels.command("toggle", "small");
            if (panels.state.widgets.small.phase !== "opening" || small.progress !== progress) Qt.exit(1);
            console.log("gentle reveal and continuous toggle reversal passed");
        }
    }
    Timer {
        property int stage: 0
        property int ticks: 0
        interval: 100; repeat: true; running: Quickshell.env("WIDGETS_IPC_TEST") !== "1"
        onTriggered: {
            function check(value, message) { if (!value) { console.error(message); Qt.exit(1); } }
            check(++ticks < 100, "QML lifecycle timed out");
            if (stage === 1 && panels.state.widgets.small.phase === "opening") return;
            if (stage === 2 && panels.state.widgets.small.phase === "closing") return;
            if (stage === 3 && panels.state.widgets.large.phase === "opening") return;
            if (stage === 4 && panels.state.widgets.large.phase === "closing") return;
            if (stage === 0) {
                check(typeof Style.applyTheme === "function", "native theme application missing");
                Style.applyTheme({background: "#80203040", foreground: "#fff0f1f2"});
                check(Qt.colorEqual(backgroundOf(large), "#80203040"), "popup uses native background including alpha");
                check(Qt.colorEqual(large.widgetContext.foreground, "#fff0f1f2"), "widget context uses native foreground");
                check(!large.loaded && !small.loaded, "components lazy until first open");
                check(panels.state.widgets.broken.available, "unopened broken component not loaded");
                panels.command("show", "small");
                check(!small.surface.visible, "surface must stay unmapped until adapter has verified runtime PID");
                panels.command("hide", "small");
                panels.dispatch({type: "ADAPTER_CONNECTED"});
                panels.command("show", "broken");
                panels.command("show", "large");
                panels.command("hide", "large");
                check(large.widgetContext.contentWidth === 388 && small.widgetContext.contentHeight === 208, "logical context sizes");
                panels.command("show", "small");
                check(small.surface.visible && small.progress === 0, "transparent preparing");
                panels.dispatch({type: "GEOMETRY", id: "small", requestId: panels.state.widgets.small.requestId, width: 160, height: 120});
                check(small.widgetContext.contentWidth === 128 && small.widgetContext.contentHeight === 88, "clamped logical context");
                panels.dispatch({type: "PLACED", id: "small", requestId: panels.state.widgets.small.requestId});
                gentleStart.restart();
            } else if (stage === 1) {
                const requestId = panels.state.widgets.small.requestId;
                Style.applyTheme({background: "#fff6f5f4", foreground: "#ff222226"});
                check(Qt.colorEqual(backgroundOf(small), "#fff6f5f4"), "open popup does not follow theme change");
                check(Qt.colorEqual(small.widgetContext.foreground, "#ff222226"), "open content foreground remains dark-theme color");
                check(panels.state.widgets.small.requestId === requestId, "theme change restarts widget lifecycle");
                check(panels.state.widgets.small.phase === "open", "animation completed: " + JSON.stringify(panels.state) + " progress=" + small.progress);
                check(large.loaded && small.loaded, "components load on first open and persist");
                check(!panels.state.widgets.broken.available, "broken isolated on first open");
                check(small.surface.width === 184 && small.surface.height === 144, "clamped fixed surface");
                check(small.scrollRequired, "clamped content remains scrollable");
                small.widgetContext.requestClose();
                check(small.surface.visible && panels.state.widgets.small.phase === "closing", "closing remains mapped");
            } else if (stage === 2) {
                check(!small.surface.visible && panels.state.widgets.small.phase === "closed", "closed unmapped");
                check(!small.loaded, "unloadOnClose releases content");
                panels.command("show", "small");
                stage = 20; return;
            } else if (stage === 20) {
                check(small.loaded, "unloaded content loads again on reopen");
                panels.command("hide", "small");
                panels.animationsEnabled = false;
                panels.command("show", "large");
                panels.dispatch({type: "PLACED", id: "large", requestId: panels.state.widgets.large.requestId});
                stage = 3; return;
            } else if (stage === 3) {
                check(panels.state.widgets.large.phase === "open" && large.progress === 1, "animations disabled opens");
                large.widgetContext.requestClose();
            } else {
                check(!large.surface.visible && panels.state.widgets.large.phase === "closed", "animations disabled closes");
                console.log("QML components, failure isolation, context and animation passed");
                Qt.exit(0);
            }
            stage++;
        }
    }
    Timer {
        interval: 50; running: Quickshell.env("WIDGETS_IPC_TEST") !== "1"
        onTriggered: {
            if (controller.command("show", "missing")) Qt.exit(1);
            if (controller.command("hide", "__proto__") || controller.command("hide", "constructor")) Qt.exit(1);
            if (controller.dispatch({type: "AVAILABLE", id: "__proto__", value: false})) Qt.exit(1);
            if (({}).phase !== undefined) Qt.exit(1);
            controller.dispatch({type: "ADAPTER_CONNECTED"});
            if (!controller.command("show", "example")) Qt.exit(1);
            const id = controller.state.widgets.example.requestId;
            if (!controller.dispatch({type: "PLACED", id: "example", requestId: id})) Qt.exit(1);
            if (controller.state.widgets.example.phase !== "opening") Qt.exit(1);
            console.log("QML controller/IPC smoke passed");
        }
    }
}
