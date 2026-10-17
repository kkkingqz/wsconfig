# The core of wsconfig in the store (ws help plan-v2, stage 5): bin/ws,
# libexec/, lib/, the modules with their hooks, extensions and patches, docs,
# template/ (ws setup --new). Not in it: tests/ (with the test configuration
# tests/config). The data is in the configuration repository, read from
# WS_CONFIG.
# .wsconfig-package marks the tree as the core in the store (ws check home).
# mainProgram: `nix run github:kkkingqz/wsconfig/REV#ws -- ARG...` runs bin/ws
# of that revision without a checkout (install.sh, ws help plan-v2, 9.1).
# libexec/gum: the dialogs of ws (lib/ws_ui.py) use the gum of this nixpkgs,
# also under nix run before the first ws apply (ws help plan-v2, 11.0).
# libexec/wsdbus-ctl: the client of the desktop contract for ws-window
# (gnome/wsdbus.nix), also where the profile is not in PATH (xremap launch).
# share/ws/complete.json: the completion of ws, from the usage of its
# commands (lib/ws_complete.py); a usage it cannot read fails the build.
{ lib, runCommand, gum, python3, wsdbusCtl }:
let
  root = ../..;
  # The test configuration and the tests are no part of the core.
  data = [ (root + "/tests") ];
  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.difference root (lib.fileset.unions data);
  };
in
runCommand "wsconfig-core" { meta.mainProgram = "ws"; nativeBuildInputs = [ python3 ]; } ''
  cp -r ${src} $out
  chmod u+w $out
  touch $out/.wsconfig-package
  chmod u+w $out/libexec
  ln -s ${gum}/bin/gum $out/libexec/gum
  ln -s ${lib.getExe wsdbusCtl} $out/libexec/wsdbus-ctl
  mkdir -p $out/share/ws
  python3 $out/lib/ws_complete.py build $out > $out/share/ws/complete.json
''
