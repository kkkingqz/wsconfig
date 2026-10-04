{ config, pkgs, lib, facts, ... }:
let
  runtime = import ./runtime { inherit pkgs; };
  manifest = import ./manifest.nix { inherit lib; registry = import ./registry.nix; qmlRoot = ./quickshell; };
  manifestFile = pkgs.writeText "widget-manifest.json" (builtins.toJSON manifest);
  repo = "${config.home.homeDirectory}/${facts.wsconfig}";
  sessionGuard = pkgs.writeShellScript "widgets-session-guard" ''
    case ":''${XDG_CURRENT_DESKTOP:-}:" in *:GNOME:*) ;; *) exit 1 ;; esac
    test -n "''${WAYLAND_DISPLAY:-}"
  '';
in {
  xdg.configFile."quickshell/workstation-widgets".source = config.lib.file.mkOutOfStoreSymlink "${repo}/widgets/quickshell";
  xdg.dataFile."workstation/widgets/manifest.json".source = manifestFile;
  xdg.dataFile."workstation/widgets/runtime.json".text = builtins.toJSON {
    schemaVersion = 2;
    qsPath = "${runtime}/bin/qs-widgets";
    socketPath = "$XDG_RUNTIME_DIR/workstation-widgets/control.sock";
    manifestPath = "${config.xdg.dataHome}/workstation/widgets/manifest.json";
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
      # A registry change changes the unit, so Home Manager restarts the runtime.
      Environment = [ "WIDGETS_MANIFEST=${manifestFile}" "WIDGETS_SOCKET=%t/workstation-widgets/control.sock" "WIDGETS_CHMOD=${pkgs.coreutils}/bin/chmod" ];
      RuntimeDirectory = "workstation-widgets";
      RuntimeDirectoryMode = "0700";
      UMask = "0077";
      ExecCondition = sessionGuard;
      ExecStart = "${runtime}/bin/qs-widgets --session -n -c workstation-widgets";
      Restart = "on-failure";
      RestartSec = 2;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
