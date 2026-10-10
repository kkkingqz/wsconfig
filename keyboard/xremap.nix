# xremap: binary (nix/pkgs/xremap.nix), config and user service from Nix.
#
# - xremap.yml is built into the store with @repo@ replaced by the checkout
#   path of this home; an edit takes effect on `ws switch`, which restarts the
#   service because its unit changes.
# - The unit is the former systemd/user/xremap.service. home-manager owns the
#   unit and its graphical-session.target.wants link; ws-keyboard still decides
#   whether xremap runs: `ws-keyboard restore` and a failed apply create
#   ~/.local/state/workstation/keyboard/xremap.disabled, apply/start remove it.
# - ~/.local/bin/xremap stays for `ws-keyboard devices` and the status tools.
{ config, lib, pkgs, xremap, facts, ... }:
let
  home = config.home.homeDirectory;
  repo = "${home}/${facts.wsconfig}";
  # Input devices of the host xremap must not grab (facts.nix
  # xremapIgnore): virtual keyboards of other remappers, e.g. InputPlumber
  # on legiongo. ";" between names, which may hold spaces.
  ignore = facts.xremapIgnore or [ ];

  xremapYml = pkgs.writeText "xremap.yml"
    (builtins.replaceStrings [ "@repo@" ] [ repo ]
      (builtins.readFile ./xremap.yml));
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
      ConditionPathExists = "!%h/.local/state/workstation/keyboard/xremap.disabled";
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
      ExecStart = "/usr/bin/bash ${repo}/bin/ws-xremap";
      Restart = "on-failure";
      RestartSec = 5;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
