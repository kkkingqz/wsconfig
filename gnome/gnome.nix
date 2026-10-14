# GNOME appearance and Ubuntu Dock: the values are gnome/config.toml (and
# hosts/HOST/gnome.toml), what the user edits; home-manager writes them
# with `dconf load` on every `ws apply`. Here: the keys of the hardware,
# the check against the keys of other owners and settings.json.
#
# ws-gnome check compares the session with ~/.local/share/wsconfig/gnome/
# settings.json ([{schema, key, value}], value as gsettings get prints it),
# built from the same attribute set.
{ config, lib, pkgs, facts, wsHost, wsConfig, ... }:
let
  gnome = import ./config.nix { inherit lib wsHost wsConfig; };

  profile = lib.recursiveUpdate (gnome.settings or { }) (lib.optionalAttrs (facts.hardware == "t2-mbp16") {
    # The power key hibernates (ws help suspend, Hibernate); logind does the
    # same outside a session (system/files/logind.conf.d/ws-sleep-keys.conf).
    "org/gnome/settings-daemon/plugins/power" = {
      power-button-action = "hibernate";
    };
  });

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

  checkProfile = pkgs.writeText "gnome-settings.json" (builtins.toJSON
    (lib.flatten (lib.mapAttrsToList (dir: keys:
      lib.mapAttrsToList (key: value: {
        schema = lib.replaceStrings [ "/" ] [ "." ] dir;
        inherit key;
        value = toString (lib.hm.gvariant.mkValue value);
      }) keys) profile)));
in
{
  assertions = [{
    assertion = overlap == [ ];
    message = "dconf.settings overlaps keys of other owners: "
      + lib.concatStringsSep ", " overlap;
  }];

  dconf.settings = profile;

  xdg.dataFile."wsconfig/gnome/settings.json".source = checkProfile;
}
