# Widget layer (helpws widgets), on hosts with widgets = "yes": the
# Quickshell runtime, QML, GNOME adapter files and ws-widgets come from the
# wswidgets flake input (pinned by flake.lock; wswidgets update); this
# repository chooses the widgets per workstation (widgets.txt, wswidgets
# enable|disable) and enables the adapter (gnome/gnome-extensions.nix).
{ lib, wswidgets, wsHost, ... }:
let
  marks = import ../lib/ws_marks.nix { inherit lib; };
  # ID HOST=STATE... all=STATE per line, # comments; the file order is the
  # panel order, so the lines are read in order (ws_marks.read is a set).
  lines = lib.filter (l: l != "")
    (map (l: lib.trim (builtins.head (lib.splitString "#" l)))
      (lib.splitString "\n" (builtins.readFile ./widgets.txt)));
  idOf = line: builtins.head (lib.splitString " " (builtins.replaceStrings [ "\t" ] [ " " ] line));
  enabled = line: marks.stateIn (marks.marksIn line) wsHost "ask" == "yes";
  ids = map idOf (lib.filter enabled lines);
in
{
  imports = [ wswidgets.homeManagerModules.default ];

  programs.wswidgets = {
    enable = true;
    widgets = ids;
  };
}
