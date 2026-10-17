# User layer of every host: links into the checkout and terminal CLI; layer
# owners (wsflatpak reads flatpak/flatpak.nix; wsbox, wswin, ws-gnome,
# ws-keyboard*, ws-suspend) stay as they are. What differs between hosts
# comes from facts (hosts/<host>/host.toml, lib/host.nix).
{ lib, facts, ... }:
{
  imports = [
    ./links.nix
    ./cli.nix
    ../../terminal/session-colors.nix
    ../../terminal/ssh-colors.nix
    ../../terminal/distrobox-colors.nix
    ./man.nix
    ../../gnome/gnome-extensions.nix
    ../../gnome/wsdbus.nix
    ../../flatpak/flatpak.nix
    ../../gnome/gnome.nix
    ../../keyboard/keyboard.nix
    ../../distrobox/distrobox.nix
    ../../windows/apps.nix
    # The scripts of the configuration, run by name (ws help scripts).
    ../../scripts/scripts.nix
    # Sources of the Game Mode packages: built anywhere, installed only with
    # gameMode = "yes" (wsgame, ws help gaming).
    ../../gaming/sources.nix
  ]
  # xremap reads /dev/input; a container host gets its keys over RDP
  # (keyboard/keyboard.nix, ws help plan-wsgnomebox).
  ++ lib.optionals (facts.boot != "container") [ ../../keyboard/xremap.nix ]
  # The RDP client of a real machine; a container host is the RDP server
  # (ws help remmina, ws help plan-wsgnomebox).
  ++ lib.optionals (facts.boot != "container") [ ../../remmina/remmina.nix ]
  # Quickshell widgets from wswidgets (ws help widgets) on hosts with them.
  ++ lib.optionals facts.widgets [ ../../widgets/widgets.nix ]
  # ~/VMs (ws help virt) on hosts with VMs.
  ++ lib.optionals facts.vm [ ../../virt/virt.nix ]
  # Pinned sources of the patched t2bce modules (ws help suspend) and of
  # t2gmux (ws help plan-dgpu); the brightness that the panel ignores at boot
  # and logout, written again in the session (ws help workstation, GRAPHICS).
  ++ lib.optionals (facts.hardware == "t2-mbp16") [
    ../../system/kernel/t2bce/t2bce.nix
    ../../system/kernel/t2gmux/t2gmux.nix
    ../../gnome/backlight.nix
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
  #   drivers; GUI apps come from apt and Flatpak, so it stays off (the one
  #   Nix GUI app, Remmina, links its own launchers: remmina/remmina.nix);
  # - programs.man would put Nix man before /usr/bin/man;
  # - xdg.mime would run Nix update-mime-database on ~/.local/share/mime.
  targets.genericLinux.enable = false;
  programs.man.enable = false;
  xdg.mime.enable = false;
}
