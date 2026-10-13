# Screen brightness after a session starts (t2-mbp16, helpws workstation,
# GRAPHICS). systemd-backlight restores the saved level into gmux at boot,
# and gmux_backlight keeps reporting it, but the panel comes up at another
# level once the display manager turns it on (2026-10-13: sysfs, gmux and
# mutter all said 19805 while the screen was much brighter; writing the
# value again made the panel follow). The same happens on every logout:
# the login screen turns the panel on again.
#
# So when the GNOME session is up, write the current value once more,
# through logind like mutter does. backlight_update_status runs even for
# an unchanged value; mutter sees the same value and changes nothing.
{ pkgs, ... }:
let
  reapply = pkgs.writeShellScript "ws-backlight-reapply" ''
    set -eu
    device=/sys/class/backlight/gmux_backlight
    [ -r "$device/brightness" ] || exit 0
    exec /usr/bin/busctl call org.freedesktop.login1 \
      /org/freedesktop/login1/session/auto org.freedesktop.login1.Session \
      SetBrightness ssu backlight gmux_backlight "$(cat "$device/brightness")"
  '';
in
{
  systemd.user.services.ws-backlight-reapply = {
    Unit = {
      Description = "Apply the restored screen brightness to the panel";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" "gnome-session-initialized.target" ];
    };
    Service = {
      Type = "oneshot";
      ExecStart = "${reapply}";
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
