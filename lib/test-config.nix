# lib/schema.nix and lib/config.nix (nix flake check, config).
{ lib }:
let
  s = import ./schema.nix { inherit lib; };
  c = import ./config.nix { inherit lib; };
  t = s.table {
    keys = {
      name = s.string;
      size = s.int;
      tags = s.strings;
      mode = s.oneOf [ "a" "b" ];
      boxes = s.listOf (s.table { keys = { name = s.string; image = s.string; }; required = [ "name" ]; });
      settings = s.attrsOf (s.attrsOf (s.scalar "a dconf value" (v: !builtins.isAttrs v)));
    };
    required = [ "name" ];
  };
  write = name: text: builtins.toFile name text;
  common = write "common.toml" ''
    name = "n"
    size = 1
    tags = ["a", "b"]
    [settings."org/x"]
    k = 1
    j = "s"
  '';
  host = write "host.toml" ''
    tags = ["c"]
    [settings."org/x"]
    k = 2
  '';
  fails = e: !(builtins.tryEval e).success;
  read = args: c.read ({ type = t; } // args);
in
# Types.
assert s.problems t { name = "n"; } == [ ];
assert s.problems t { } == [ "no name in the file" ];
assert s.problems t { name = 1; } == [ "name must be a string" ];
assert s.problems t { name = "n"; extra = 1; } == [ "unknown key extra in the file" ];
assert s.problems t { name = "n"; mode = "c"; } == [ ''mode must be one of "a", "b"'' ];
assert s.problems t { name = "n"; boxes = [ { name = "a"; } { image = "i"; } ]; }
  == [ "no name in [boxes[2]]" ];
assert s.problems t { name = "n"; boxes = [ { name = "a"; x = 1; } ]; } == [ "unknown key x in [boxes[1]]" ];
assert s.problems t { name = "n"; settings = { "org/x" = { k = { }; }; }; }
  == [ ''settings.org/x.k must be a dconf value'' ];
# Merge: tables by key, scalars and lists replaced.
assert (c.merge "f" "" { a = { x = 1; y = 2; }; l = [ 1 ]; } { a = { y = 3; }; l = [ 2 ]; }).value
  == { a = { x = 1; y = 3; }; l = [ 2 ]; };
assert (c.merge "f" "" { a = { x = 1; }; } { a = 2; }).problems == [ "f: a is a value here, a table before" ];
# Read: defaults, common, host.
assert read { file = common; } == {
  name = "n"; size = 1; tags = [ "a" "b" ]; settings."org/x" = { k = 1; j = "s"; };
};
assert read { file = common; inherit host; defaults = { size = 0; mode = "a"; }; } == {
  name = "n"; size = 1; mode = "a"; tags = [ "c" ]; settings."org/x" = { k = 2; j = "s"; };
};
# The host file need not repeat the required keys; a missing one is fine.
assert (read { file = common; host = write "none.toml" "size = 3"; }).size == 3;
assert (read { file = common; host = ./does-not-exist.toml; }).size == 1;
assert fails (read { file = ./does-not-exist.toml; });
assert (read { file = ./does-not-exist.toml; optional = true; defaults = { name = "d"; }; }).name == "d";
assert fails (read { file = common; host = write "bad.toml" "size = \"big\""; });
assert fails (read { file = write "nameless.toml" "size = 1"; });
assert fails (read { file = common; host = write "conflict.toml" "settings = 1"; });
true
