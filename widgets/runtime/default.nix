{ pkgs }:
pkgs.writeShellApplication {
  name = "qs-widgets";
    text = ''
      if [[ "''${1:-}" == --session ]]; then
        shift
        case ":''${XDG_CURRENT_DESKTOP:-}:" in *:GNOME:*) ;; *) echo "Widgets require GNOME" >&2; exit 78 ;; esac
        [[ -n "''${WAYLAND_DISPLAY:-}" ]] || { echo "Widgets require Wayland" >&2; exit 78; }
      fi
    export QT_QPA_PLATFORM="''${QT_QPA_PLATFORM:-wayland}"
    export QT_WAYLAND_DISABLE_WINDOWDECORATION=1
    # GLVND needs a driver from the same Nix closure, scoped to this process.
    export __EGL_VENDOR_LIBRARY_FILENAMES=${pkgs.mesa}/share/glvnd/egl_vendor.d/50_mesa.json
    exec ${pkgs.lib.getExe pkgs.quickshell} "$@"
  '';
}
