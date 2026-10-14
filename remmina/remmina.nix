# Remmina from Nix instead of apt (ws help remmina): package.nix, with H.264
# and files through the RDP clipboard; machine-apt.txt purges the Ubuntu one.
#
# ~/.nix-profile/share is not in XDG_DATA_DIRS (targets.genericLinux is
# off, nix/home/default.nix): the launchers go to ~/.local/share/applications
# with absolute paths, the icons to ~/.local/share/icons. Same desktop IDs
# as the apt package: its MIME types (rdp://, .remmina) and the "Grab all
# keyboard events" permission of GNOME (ws help keyboard) stay.
#
# Copying files from the server mounts FUSE through /usr/bin/fusermount3
# (fuse3, a dependency of flatpak and fuse-overlayfs).
{ lib, pkgs, ... }:
let
  remmina = pkgs.callPackage ./package.nix { };

  launchers = [ "org.remmina.Remmina.desktop" "org.remmina.Remmina-file.desktop" ];
  # The app icons, and the tray icon: Remmina gives the panel an icon name
  # only (org.remmina.Remmina-status), without a theme path, so GNOME Shell
  # looks it up in ~/.local/share/icons; missing, it shows "...".
  icons = map (f: "scalable/apps/${f}") [ "org.remmina.Remmina.svg" "org.remmina.Remmina-symbolic.svg" ]
    ++ map (n: "${n}x${n}/status/org.remmina.Remmina-status.svg") [ "16" "22" "24" "32" "48" "64" ];

  desktop = pkgs.runCommand "remmina-desktop" { } ''
    mkdir -p $out
    for f in ${lib.escapeShellArgs launchers}; do
      sed -E 's|^(Try)?Exec=remmina|\1Exec=${remmina}/bin/remmina|' \
        ${remmina}/share/applications/$f > $out/$f
      if grep -Eq '^(Try)?Exec=[^/]' $out/$f; then
        echo "remmina/remmina.nix: $f still runs a command from PATH" >&2
        exit 1
      fi
    done
  '';

  # Quick connect starts from the default profile (group remmina; "Save as
  # Default" in the profile editor): the best quality. Best is all of the
  # remote desktop (wallpaper, themes, window contents while dragging) plus
  # font smoothing and composition (0x180; Remmina's own 0x80 lacks
  # composition). colordepth 99 lets the server pick its codec (H.264),
  # autodetect has it measure the network.
  pref = {
    "remmina.quality" = "9";
    "remmina.colordepth" = "99";
    "remmina.network" = "autodetect";
    "remmina_pref.rdp_quality_9" = "180";
  };
in
{
  home.packages = [ remmina ];

  xdg.dataFile = lib.listToAttrs (map (f:
    lib.nameValuePair "applications/${f}" { source = "${desktop}/${f}"; }) launchers)
  // lib.listToAttrs (map (f:
    lib.nameValuePair "icons/hicolor/${f}" {
      source = "${remmina}/share/icons/hicolor/${f}";
    }) icons);

  # Only these keys; the rest of remmina.pref is Remmina's.
  home.activation.remminaPref = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    run ${pkgs.python3}/bin/python3 ${./remmina-pref.py} \
      "$HOME/.config/remmina/remmina.pref" \
      ${lib.escapeShellArgs (lib.mapAttrsToList (k: v: "${k}=${v}") pref)}
  '';
}
