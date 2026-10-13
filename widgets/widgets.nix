# Widget layer (helpws widgets), on hosts with widgets = "yes": the
# Quickshell runtime, QML, GNOME adapter files and ws-widgets come from the
# wswidgets flake (~/Projects/wswidgets); this repository only chooses the
# widgets (widgets.txt) and enables the adapter (gnome/gnome-extensions.nix).
{ lib, wswidgets, ... }:
let
  # One ID per line, # comments; the order is the panel order.
  ids = lib.filter (l: l != "")
    (map (l: lib.trim (builtins.head (lib.splitString "#" l)))
      (lib.splitString "\n" (builtins.readFile ./widgets.txt)));
in
{
  imports = [ wswidgets.homeManagerModules.default ];

  programs.wswidgets = {
    enable = true;
    widgets = ids;
  };
}
