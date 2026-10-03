{ config, pkgs, lib, facts, ... }:
let
  runtime = import ./runtime { inherit pkgs; };
  manifest = import ./manifest.nix { inherit lib; registry = import ./registry.nix; qmlRoot = ./quickshell; };
  repo = "${config.home.homeDirectory}/${facts.wsconfig}";
  sessionGuard = pkgs.writeShellScript "widgets-session-guard" ''
    case ":''${XDG_CURRENT_DESKTOP:-}:" in *:GNOME:*) ;; *) exit 1 ;; esac
    test -n "''${WAYLAND_DISPLAY:-}"
  '';
in {
  xdg.configFile."quickshell/workstation-widgets".source = config.lib.file.mkOutOfStoreSymlink "${repo}/widgets/quickshell";
  xdg.configFile."workstation/widgets/manifest.json".text = builtins.toJSON manifest;
  xdg.configFile."workstation/widgets/runtime.json".text = builtins.toJSON {
    schemaVersion = 1;
    qsPath = "${runtime}/bin/qs-widgets";
    configName = "workstation-widgets";
    manifestPath = "${config.xdg.configHome}/workstation/widgets/manifest.json";
    adapter = "gnome";
  };
  systemd.user.services.workstation-widgets = {
    Unit = {
      Description = "Workstation shared widget runtime";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
      StartLimitIntervalSec = 60;
      StartLimitBurst = 5;
    };
    Service = {
      ExecCondition = sessionGuard;
      ExecStart = "${runtime}/bin/qs-widgets --session -n -c workstation-widgets";
      Restart = "on-failure";
      RestartSec = 2;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
