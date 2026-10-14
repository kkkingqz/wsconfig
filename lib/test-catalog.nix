# lib/catalog.nix reads the host files as lib/ws_catalog.py does
# (tests/test_ws_catalog.py): nix flake check (catalog).
{ lib }:
let
  catalog = import ./catalog.nix { inherit lib; hosts = ../tests/fixtures/catalog; };
  state = catalog.state;
in
assert state "a" "boxes" "arch" "ask" == "yes";
assert state "a" "boxes" "proton" "yes" == "no";
assert state "a" "boxes" "t2bce-build" "no" == "no";
assert state "a" "boxes" "other" "ask" == "ask";
assert state "a" "boxes" "other" "yes" == "yes";
# No file: every position has its default.
assert state "b" "boxes" "arch" "ask" == "ask";
assert state "missing" "boxes" "arch" "no" == "no";
# The order of yes is kept: the panel order of the widgets.
assert (catalog.choice "b" "widgets").yes == [ "compact" "example" ];
assert catalog.has "a" "boxes" "wine" "ask" && !(catalog.has "a" "boxes" "proton" "yes");
true
