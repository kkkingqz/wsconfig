# The desktop contract of wsdbus (github:kkkingqz/wsdbus, pinned by
# flake.lock): wsdbus-ctl and the GNOME provider extension
# wsdbus@kkkingqz.github.io. gnome-extensions.nix enables the extension
# (source nix); ws-window (libexec/wsdbus-ctl of the core) acts on the
# windows of the focused application through it, the widgets follow the
# lock screen and the colour scheme (widgets/widgets.nix).
{ wsdbus, ... }:
{
  imports = [ wsdbus.homeManagerModules.default ];

  programs.wsdbus.enable = true;
}
