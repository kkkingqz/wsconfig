# User layer of every host: links into the checkout and terminal CLI; layer
# owners (wsflatpak reads flatpak/flatpak.nix; wsbox, wswin, ws-gnome,
# ws-keyboard*, ws-suspend) stay as they are. What differs between hosts
# comes from facts (nix/hosts/<host>/facts.nix).
{ lib, facts, ... }:
{
  imports = [
    ./links.nix
    ./cli.nix
    ../../terminal/session-colors.nix
    ../../terminal/ssh-colors.nix
    ../../terminal/distrobox-colors.nix
    ../../keyboard/xremap.nix
    ./man.nix
    ../../gnome/gnome-extensions.nix
    ../../flatpak/flatpak.nix
    ../../gnome/gnome.nix
    ../../keyboard/keyboard.nix
    ../../distrobox/distrobox.nix
    ../../windows/apps.nix
    ../../widgets/widgets.nix
  ]
  # ~/VMs (helpws virt) on hosts with VMs.
  ++ lib.optionals (facts.vm == "yes") [ ../../virt/virt.nix ]
  # Pinned sources of the patched t2bce modules (helpws suspend) and of
  # t2gmux (helpws plan-dgpu).
  ++ lib.optionals (facts.hardware == "t2-mbp16") [
    ../../system/kernel/t2bce/t2bce.nix
    ../../system/kernel/t2gmux/t2gmux.nix
  ];

  home.username = facts.user;
  home.homeDirectory = "/home/${facts.user}";
  home.stateVersion = "26.05";

  programs.home-manager.enable = true;
  # No news notification (notify-send) on every switch; read them with
  # `ws news` (plain `home-manager news` looks for ~/.config/home-manager).
  news.display = "silent";

  # Nothing may change the GNOME session or shadow apt tools yet:
  # - targets.genericLinux writes ~/.config/environment.d/10-home-manager.conf
  #   (XDG_DATA_DIRS, NIX_PATH, TERMINFO_DIRS for the whole session) and GPU
  #   drivers; GUI apps come from apt and Flatpak, so it stays off;
  # - programs.man would put Nix man before /usr/bin/man;
  # - xdg.mime would run Nix update-mime-database on ~/.local/share/mime.
  targets.genericLinux.enable = false;
  programs.man.enable = false;
  xdg.mime.enable = false;
}
