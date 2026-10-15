# The core of wsconfig in the store (ws help plan-v2, stage 5): bin/ws,
# libexec/, lib/, the modules with their hooks, extensions and patches, docs.
# Not in it: tests/ (with the test configuration tests/config). The data
# is in the configuration repository, read from WS_CONFIG.
# .wsconfig-package marks the tree as the core in the store (ws check home).
# mainProgram: `nix run github:kkkingqz/wsconfig/REV#ws -- ARG...` runs bin/ws
# of that revision without a checkout (install.sh, ws help plan-v2, 9.1).
{ lib, runCommand }:
let
  root = ../..;
  # The test configuration and the tests are no part of the core.
  data = [ (root + "/tests") ];
  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.difference root (lib.fileset.unions data);
  };
in
runCommand "wsconfig-core" { meta.mainProgram = "ws"; } ''
  cp -r ${src} $out
  chmod u+w $out
  touch $out/.wsconfig-package
''
