import QtQuick
import Quickshell
import Quickshell.Io
import "manifest.mjs" as Manifest
Scope {
    id: root
    property string path: Quickshell.env("WIDGETS_MANIFEST") || (Quickshell.env("XDG_DATA_HOME") || Quickshell.env("HOME") + "/.local/share") + "/workstation/widgets/manifest.json"
    property var entries: []
    property string error: ""
    FileView {
        path: root.path
        onLoaded: {
            try { root.entries = Manifest.validateManifest(JSON.parse(text())); root.error = ""; }
            catch (e) { root.error = String(e); console.error(root.error); }
        }
        onLoadFailed: error => { root.error = "Manifest read failed: " + error; console.error(root.error); }
    }
}
