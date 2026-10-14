# GNOME appearance and Ubuntu Dock profile. home-manager writes it with `dconf load` on every
# `ws switch`: a manual change of these keys is reverted by the next switch,
# and a key removed here is reset to its default.
#
# Values are written explicitly even where they equal the Ubuntu default, so
# a changed distribution default does not reach this machine unnoticed.
#
# Deliberately not here (other owners or user choice): display scale and
# monitors.xml, Mutter experimental-features, input sources and keyboard
# shortcuts (ws-keyboard-apply, with restore), Tiling Assistant bindings
# (ws-tiling-apply), wallpaper. Enabled extensions are declared in
# gnome-extensions.nix, also as dconf.settings.
#
# ws-gnome check compares the session with ~/.local/share/workstation/gnome/
# settings.conf (SCHEMA|KEY|VALUE), built from the same attribute set.
{ config, lib, pkgs, facts, ... }:
let
  profile = {
    "org/gnome/desktop/interface" = {
      color-scheme = "prefer-dark";
      accent-color = "orange";
      gtk-theme = "Yaru-dark";
      icon-theme = "Yaru-dark";
      cursor-theme = "Yaru";
      font-name = "Ubuntu Sans 11";
      document-font-name = "Sans 11";
      monospace-font-name = "Ubuntu Sans Mono 11";
    };

    # Ubuntu Dock: working baseline captured 2026-09-23.
    "org/gnome/shell/extensions/dash-to-dock" = {
      dock-position = "BOTTOM";
      dock-fixed = true;
      autohide = true;
      intellihide = true;
      dash-max-icon-size = 50;
      show-show-apps-button = true;
      show-favorites = true;
      show-running = true;
      show-trash = false;
      show-mounts = true;
      multi-monitor = true;
      click-action = "focus-minimize-or-appspread";
    };
  } // lib.optionalAttrs (facts.hardware == "t2-mbp16") {
    # The power key hibernates (helpws suspend, Hibernate); logind does the
    # same outside a session (system/files/logind.conf.d/ws-sleep-keys.conf).
    "org/gnome/settings-daemon/plugins/power" = {
      power-button-action = "hibernate";
    };
  };

  # Keys that scripts set (keyboard, tiling) or that stay unmanaged;
  # dconf.settings must not fight them.
  foreignDirs = [
    "org/gnome/desktop/input-sources"
    "org/gnome/desktop/wm/keybindings"
    "org/gnome/shell/keybindings"
    "org/gnome/settings-daemon/plugins/media-keys"
    "org/gnome/shell/extensions/tiling-assistant"
  ];
  foreignKeys = [
    "org/gnome/desktop/interface/text-scaling-factor"
    "org/gnome/mutter/experimental-features"
    "org/gnome/mutter/overlay-key"
    "org/gnome/shell/extensions/dash-to-dock/hot-keys"
  ];
  declared = lib.concatLists (lib.mapAttrsToList
    (dir: keys: map (key: "${dir}/${key}") (lib.attrNames keys))
    config.dconf.settings);
  overlap = lib.filter (path:
    lib.elem path foreignKeys
    || lib.any (dir: lib.hasPrefix "${dir}/" path) foreignDirs) declared;

  checkProfile = pkgs.writeText "gnome-settings.conf" (''
    # Built from gnome/gnome.nix; read by ws-gnome check.
    # SCHEMA|KEY|VALUE as printed by gsettings get
  '' + lib.concatStrings (lib.mapAttrsToList (dir: keys:
    lib.concatStrings (lib.mapAttrsToList (key: value:
      "${lib.replaceStrings [ "/" ] [ "." ] dir}|${key}|${toString (lib.hm.gvariant.mkValue value)}\n")
      keys)) profile));
in
{
  assertions = [{
    assertion = overlap == [ ];
    message = "dconf.settings overlaps keys of other owners: "
      + lib.concatStringsSep ", " overlap;
  }];

  dconf.settings = profile;

  xdg.dataFile."workstation/gnome/settings.conf".source = checkProfile;
}
