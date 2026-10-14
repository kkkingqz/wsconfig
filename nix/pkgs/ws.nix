# The core of wsconfig in the store (helpws plan-v2, stage 5): bin/ws,
# libexec/, lib/, the modules with their hooks, extensions and patches, docs.
# Not in it: the data of the configuration (nix/hosts, the catalogs,
# flake.lock; the data patterns of bin/ws) and tests. A tool that would
# read data from WS_CORE finds nothing instead of a stale copy; data is
# read from WS_CONFIG.
# .wsconfig-package marks the tree: lib/common.bash then takes WS_CONFIG from
# host.json in the state, not the core itself (a checkout).
{ lib, runCommand }:
let
  root = ../..;
  data = map (p: lib.fileset.maybeMissing (root + p))
    [ "/nix/hosts" "/flatpak/catalog.toml" "/distrobox/catalog.toml" "/windows/apps.toml"
      "/flake.lock" "/tests" ];
  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.difference root (lib.fileset.unions data);
  };
in
runCommand "wsconfig-core" { } ''
  cp -r ${src} $out
  chmod u+w $out
  touch $out/.wsconfig-package
''
