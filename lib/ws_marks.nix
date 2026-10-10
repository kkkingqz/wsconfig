# The workstation marks of the managed lists (lib/ws_marks.py) for Nix:
# flatpak/apps.txt and distrobox/hosts.txt, KEY... HOST=yes|no|ask ...
# all=STATE. Desktop entries of an app or a box are linked only on a
# workstation that has it. The tools validate the lines; this only reads.
{ lib }:
let
  isMark = t: builtins.match "[A-Za-z0-9][A-Za-z0-9_-]*=(yes|no|ask)" t != null;

  tokens = text: lib.filter (t: lib.isString t && t != "") (builtins.split "[[:space:]]+" text);
  pair = t: let p = lib.splitString "=" t; in lib.nameValuePair (lib.head p) (lib.last p);

  entry = raw:
    let ts = tokens (lib.head (lib.splitString "#" raw)); in
    {
      key = lib.filter (t: !isMark t) ts;
      marks = lib.listToAttrs (map pair (lib.filter isMark ts));
    };
in
rec {
  # { HOST = STATE; } of the marks in TEXT (what follows the key fields of a
  # line whose key may itself look like a mark: overrides.txt).
  marksIn = text: lib.listToAttrs (map pair (lib.filter isMark (tokens text)));

  # STATE of HOST in MARKS: the own mark, else all=, else DEFAULT (ask for
  # apps and boxes, yes for overrides).
  stateIn = marks: host: default: marks.${host} or (marks.all or default);

  # NAME -> { HOST = STATE; } of FILE; the last key field names the line
  # (APP, container).
  read = file: lib.listToAttrs (map (e: lib.nameValuePair (lib.last e.key) e.marks)
    (lib.filter (e: e.key != [ ]) (map entry (lib.splitString "\n" (builtins.readFile file)))));

  # yes, no or ask of NAME on HOST, as ws_marks.py state: the own mark, else
  # all=, else ask.
  state = marks: name: host: stateIn (marks.${name} or { }) host "ask";

  has = marks: name: host: state marks name host == "yes";
}
