# lib/ws_marks.nix reads as lib/ws_marks.py does (tests/test_ws_marks.py):
# nix flake check (ws-marks).
{ lib }:
let
  marks = import ./ws_marks.nix { inherit lib; };
  m = marks.read (builtins.toFile "marks.txt" ''
    # header a=yes
    box a=no all=yes
    other	a=yes   all=no  # note b=yes
    plain
    flathub org.example.App b=yes all=ask
  '');
  state = marks.state m;
in
assert state "box" "a" == "no";
assert state "box" "b" == "yes";
assert state "other" "a" == "yes";
assert state "other" "b" == "no";
assert state "plain" "a" == "ask";
assert state "missing" "a" == "ask";
assert state "org.example.App" "b" == "yes";
assert state "org.example.App" "a" == "ask";
assert !(m ? header);
assert marks.has m "box" "b" && !(marks.has m "box" "a");
# overrides.txt: the marks after APP KIND VALUE, yes by default.
assert marks.marksIn " a=no  all=yes " == { a = "no"; all = "yes"; };
assert marks.stateIn { a = "no"; } "a" "yes" == "no";
assert marks.stateIn { a = "no"; } "b" "yes" == "yes";
assert marks.stateIn { all = "no"; } "b" "yes" == "no";
true
