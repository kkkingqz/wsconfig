# Widget layer (ws help widgets), on hosts with widgets = "yes": the
# Quickshell runtime, QML, GNOME adapter files and ws-widgets come from the
# wswidgets flake input (pinned by flake.lock; ws widgets update); this
# repository chooses the widgets per host (nix/hosts/HOST/widgets.toml,
# ws widgets enable|disable; lib/ws_catalog.py) and enables the adapter
# (gnome/gnome-extensions.nix).
{ lib, wswidgets, wsHost, wsConfig, ... }:
let
  catalog = import ../lib/catalog.nix { inherit lib; hosts = wsConfig + "/nix/hosts"; };
in
{
  imports = [ wswidgets.homeManagerModules.default ];

  programs.wswidgets = {
    enable = true;
    # yes of this host, in order: the panel order. Every widget of the
    # catalog defaults to ask, so only yes enables one.
    widgets = (catalog.choice wsHost "widgets").yes;
  };
}
