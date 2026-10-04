{ lib, registry, qmlRoot }:
let
  entries = map (raw: { enabled = true; unloadOnClose = false; panelPosition = "right"; panelOrder = 0; } // raw) registry;
  safeFile = value:
    let
      parts = lib.splitString "/" value;
      walk = root: rest:
        let name = builtins.head rest;
            type = (builtins.readDir root).${name} or "missing";
        in if builtins.length rest == 1 then type == "regular"
           else type == "directory" && walk (root + "/${name}") (builtins.tail rest);
    in builtins.isString value && builtins.match "[a-zA-Z0-9_./-]+\\.qml" value != null
       && lib.all (p: p != "" && p != "." && p != "..") parts && walk qmlRoot parts;
  valid = e:
    builtins.isString e.id && builtins.match "[a-z][a-z0-9-]*" e.id != null
    && builtins.isBool e.enabled && builtins.isBool e.unloadOnClose
    && lib.all (x: builtins.isInt x && x > 0) [ e.width e.height ]
    && lib.elem e.panelPosition [ "left" "center" "right" ] && builtins.isInt e.panelOrder
    && lib.all (x: builtins.isString x && x != "") [ e.label e.iconName ]
    && safeFile e.component;
  ids = map (e: e.id) entries;
in
assert lib.assertMsg (lib.all valid entries) "invalid widget registry entry or unsafe/missing QML component";
assert lib.assertMsg (builtins.length ids == builtins.length (lib.unique ids)) "duplicate widget ID";
{ schemaVersion = 1; widgets = entries; }
