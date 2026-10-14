# xremap: binary (nix/pkgs/xremap.nix), config and user service from Nix.
#
# - xremap.yml: keyboard/xremap.yml of the configuration when it has one,
#   else the preset's keyboard/presets/PRESET-xremap.yml of the core (its
#   bindings launch tools of the core and emit the chords of the preset's
#   shortcuts). Built into the store with @core@ replaced by the core in
#   the store (nix/pkgs/ws.nix); an edit takes effect on `ws apply`, which
#   restarts the service because its unit changes.
# - The unit is the former systemd/user/xremap.service. home-manager owns the
#   unit and its graphical-session.target.wants link; ws-keyboard still decides
#   whether xremap runs: `ws-keyboard restore` and a failed apply create
#   ~/.local/state/wsconfig/keyboard/xremap.disabled, apply/start remove it.
# - ~/.local/bin/xremap stays for `ws-keyboard devices` and the status tools.
{ lib, pkgs, xremap, facts, wsState, core, wsHost, wsConfig, ... }:
let
  kb = (import ./config.nix { inherit lib wsHost wsConfig; }).data;
  own = wsConfig + "/keyboard/xremap.yml";
  source = if builtins.pathExists own then own else ./presets + "/${kb.preset}-xremap.yml";

  # Input devices of the host xremap must not grab (host.toml
  # xremapIgnore): virtual keyboards of other remappers, e.g. InputPlumber
  # on legiongo. ";" between names, which may hold spaces.
  ignore = facts.xremapIgnore or [ ];

  xremapYml = pkgs.writeText "xremap.yml"
    (builtins.replaceStrings [ "@core@" ] [ "${core}" ]
      (builtins.readFile source));
in
{
  home.file.".local/bin/xremap".source = "${xremap}/bin/xremap";

  systemd.user.services.xremap = {
    Unit = {
      Description = "Workstation macOS-style keyboard remapping";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
      StartLimitIntervalSec = 120;
      StartLimitBurst = 8;
      ConditionPathExists = "!%h/${wsState}/keyboard/xremap.disabled";
    };
    Service = {
      Type = "simple";
      Environment = [
        "PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin"
        "XREMAP_BIN=${xremap}/bin/xremap"
        "XREMAP_CONFIG=${xremapYml}"
        # xremap --desktop and --watch (formerly config/keyboard/settings.conf).
        "XREMAP_DESKTOP=gnome"
        "XREMAP_WATCH=config,device"
      ] ++ lib.optional (ignore != [ ])
        # Quoted: systemd splits Environment= at spaces.
        ("\"XREMAP_IGNORE=" + lib.concatStringsSep ";" ignore + "\"");
      ExecStart = "/usr/bin/bash ${core}/libexec/ws-xremap";
      Restart = "on-failure";
      RestartSec = 5;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
