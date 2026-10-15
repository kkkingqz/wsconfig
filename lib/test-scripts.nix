# lib/scripts.nix reads scripts/ as lib/ws_catalog.py does
# (tests/test_wsscript.py): nix flake check (scripts).
{ lib }:
let
  scripts = import ./scripts.nix { inherit lib; };
  fixture = ../tests/fixtures/scripts;
  catalog = import ./catalog.nix { inherit lib; hosts = fixture + "/hosts"; };
  s = scripts.read (fixture + "/scripts");
  forHost = host: scripts.forHost {
    dir = fixture + "/scripts";
    inherit catalog host;
    reserved.ws = "the ws of the core";
  };
  a = forHost "a";
  b = forHost "b";
in
# Hidden files, catalog.toml and lib/ are no scripts; a bad name is an error.
assert s.names == [ "a" "b.py" "ws" ];
assert s.default "b.py" == "yes" && s.default "a" == "ask";
assert lib.any (e: lib.hasPrefix "scripts/-bad:" e) s.errors;
assert lib.any (e: lib.hasPrefix "scripts/tools/:" e) s.errors;
assert lib.length s.errors == 2;
# yes of the host and default yes; a reserved name of the host is an error.
assert a.names == [ "a" "b.py" ];
assert lib.any (e: lib.hasPrefix "scripts/ws: ~/.local/bin/ws is the ws of the core" e) a.errors;
# No choice file: only default yes, nothing reserved chosen.
assert b.names == [ "b.py" ] && lib.length b.errors == 2;
# No scripts/ at all.
assert (scripts.read (fixture + "/missing")).names == [ ];
true
