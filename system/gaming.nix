# Hosts with gameMode = "yes" (helpws plan-legion-go, 3.4, 4.3): the system
# files of the Game Mode session switch. They are inert until `wsgame
# install` (stage 6) brings sddm, steamos-manager and gamescope-session:
# setup.sh runs ws system apply at stage 4 already. Installing sddm makes it
# the display manager (debconf), so no unit is switched here. The session
# names of steamos-manager (platform.toml [session]: ubuntu.desktop,
# gamescope-session-plus@steam) come with its package (gaming/).
{ facts, file, text, ... }:
{
  files = [
    # SDDM: autologin into GNOME, again after each logout (Relogin), which
    # is how steamos-manager switches: its zz-holo-autologin.conf (default
    # mode) and zzt-holo-temp-login.conf (one switch) sort after this file.
    # The greeter is Wayland (Ubuntu 26.04 has no Xorg server by default).
    (text "/etc/sddm.conf.d/10-ws-autologin.conf" ''
      # Game Mode session switch (system/gaming.nix, helpws plan-legion-go).
      [General]
      DisplayServer=wayland

      [Autologin]
      User=${facts.user}
      Session=ubuntu.desktop
      Relogin=true
    '' "0644")
    # Steam's session switch, "Return to Game Mode" in GNOME.
    (file "/usr/libexec/os-session-select" "system/files/gaming/os-session-select" "0755")
    (file "/usr/local/bin/return-to-gamemode" "system/files/gaming/return-to-gamemode" "0755")
    (file "/usr/local/share/applications/ws-return-to-game-mode.desktop" "system/files/gaming/ws-return-to-game-mode.desktop" "0644")
    # The power key: powerbuttond in Game Mode, gsd-power in GNOME.
    (file "/etc/systemd/logind.conf.d/ws-power-key.conf" "system/files/logind.conf.d/ws-power-key.conf" "0644")
  ];
}
