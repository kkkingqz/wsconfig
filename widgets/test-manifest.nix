{ lib }:
let
  entry = { id = "example"; label = "Example"; iconName = "view-grid-symbolic";
    component = "shell.qml"; width = 420; height = 580; };
  make = registry: import ./manifest.nix { inherit lib registry; qmlRoot = ../tests/widgets/probe; };
  accepts = registry: (builtins.tryEval (builtins.deepSeq (make registry) true)).success;
in
assert accepts [ entry ];
assert !(accepts [ entry entry ]);
assert !(accepts [ (entry // { width = 0; }) ]);
assert !(accepts [ (entry // { width = 1.5; }) ]);
assert !(accepts [ (entry // { panelPosition = "outside"; }) ]);
assert !(accepts [ (entry // { component = "../shell.qml"; }) ]);
assert !(accepts [ (entry // { component = "missing.qml"; }) ]);
true
