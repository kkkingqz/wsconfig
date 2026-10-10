# Every machine: uinput access for xremap, ntsync for Proton in distrobox,
# Timeshift snapshots in GRUB. VM files: system/virt.nix (vm = "yes").
# watch: system files the workstation depends on but does not install;
# ws-baseline records them with the installed ones.
{ file, ... }:
{
  watch = [
    "/etc/default/keyboard" # edited by ws system apply (GDM/login: EN only)
    "/etc/fstab"
  ];

  files = [
    (file "/etc/udev/rules.d/99-workstation-uinput.rules" "system/files/udev/99-workstation-uinput.rules" "0644")
    (file "/etc/modules-load.d/ntsync.conf" "system/files/modules-load.d/ntsync.conf" "0644")

    # No snaps: snapd is purged (nix/hosts/apt.txt) and pinned out.
    (file "/etc/apt/preferences.d/ws-no-snapd" "system/files/apt/ws-no-snapd" "0644")

    # Timeshift (@ and @home): its snapshots in the GRUB menu, refreshed after
    # every snapshot; after a restore the default subvolume follows the new @
    # (rEFInd boots from it). Settings stay Timeshift's (GUI).
    (file "/etc/grub.d/42_ws_timeshift" "system/files/grub.d/42_ws_timeshift" "0755")
    (file "/etc/timeshift/backup-hooks.d/50-ws-update-grub" "system/files/timeshift/50-ws-update-grub" "0755")
    (file "/etc/timeshift/restore-hooks.d/50-ws-default-subvolume" "system/files/timeshift/50-ws-default-subvolume" "0755")
  ];
}
