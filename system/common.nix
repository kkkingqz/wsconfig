# Every machine: uinput access for xremap, ntsync for Proton in distrobox,
# Timeshift snapshots in GRUB. VM files: system/virt.nix (vm = "yes").
# A container (boot = "container", ws help plan-wsgnomebox) has no udev,
# kernel modules, GRUB or Timeshift of its own: only the snapd pin.
# watch: system files the workstation depends on but does not install;
# ws-baseline records them with the installed ones.
{ lib, facts, file, ... }:
let
  machine = facts.boot != "container";
in
{
  watch = [
    "/etc/default/keyboard" # edited by ws apply system (GDM/login: EN only)
    "/etc/fstab"
  ];

  files = lib.optionals machine [
    (file "/etc/udev/rules.d/99-workstation-uinput.rules" "system/files/udev/99-workstation-uinput.rules" "0644")
    (file "/etc/modules-load.d/ntsync.conf" "system/files/modules-load.d/ntsync.conf" "0644")
    # Login screen without automatic brightness: it must not replace the level
    # systemd-backlight restores at boot and the session leaves at logout.
    # Next to the package's 00-upstream-settings, as that file asks;
    # compiled by gdm's generate-config (ws apply system runs it).
    (file "/usr/share/gdm/dconf/95-ws-greeter" "system/files/gdm/95-ws-greeter" "0644")
  ] ++ [
    # No snaps: snapd is purged (system/apt.txt) and pinned out.
    (file "/etc/apt/preferences.d/ws-no-snapd" "system/files/apt/ws-no-snapd" "0644")
  ] ++ lib.optionals machine [
    # Timeshift (@ and @home): its snapshots in the GRUB menu, refreshed after
    # every snapshot; after a restore the default subvolume follows the new @
    # (rEFInd boots from it). Settings stay Timeshift's (GUI).
    (file "/etc/grub.d/42_ws_timeshift" "system/files/grub.d/42_ws_timeshift" "0755")
    (file "/etc/timeshift/backup-hooks.d/50-ws-update-grub" "system/files/timeshift/50-ws-update-grub" "0755")
    (file "/etc/timeshift/restore-hooks.d/50-ws-default-subvolume" "system/files/timeshift/50-ws-default-subvolume" "0755")
  ];
}
