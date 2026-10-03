# MacBookPro16,1 with T2: Touch Bar native mode, T2 network and firmware,
# the suspend layer (helpws suspend), dGPU power-off at boot.
{ file, ... }:
{
  files = [
    # Screen brightness: the standard udev rule fails on gmux's PNP parent.
    (file "/etc/udev/rules.d/99-z-gmux-backlight.rules" "system/files/udev/99-z-gmux-backlight.rules" "0644")

    # Touch Bar (ws-keyboard-system-apply)
    (file "/etc/udev/rules.d/90-touchbar-native.rules" "system/files/udev/90-touchbar-native.rules" "0644")
    (file "/etc/modprobe.d/tb.conf" "system/files/modprobe/tb.conf" "0644")
    (file "/etc/modprobe.d/touchbar-native.conf" "system/files/modprobe/touchbar-native.conf" "0644")
    (file "/usr/local/libexec/ws-touchbar-fn" "system/files/usr/local/libexec/ws-touchbar-fn" "0755")
    (file "/etc/systemd/system/ws-touchbar-fn.service" "system/files/systemd/system/ws-touchbar-fn.service" "0644")

    # Suspend (ws-suspend apply)
    (file "/etc/systemd/sleep.conf.d/80-deep-only.conf" "system/files/sleep.conf.d/80-deep-only.conf" "0644")
    (file "/etc/udev/rules.d/70-bcm4364-no-d3cold.rules" "system/files/udev/70-bcm4364-no-d3cold.rules" "0644")
    (file "/etc/udev/rules.d/71-tb-xhci-awake.rules" "system/files/udev/71-tb-xhci-awake.rules" "0644")
    (file "/usr/local/sbin/broadcom-aspm-suspend-guard" "system/files/usr/local/sbin/broadcom-aspm-suspend-guard" "0755")
    (file "/usr/lib/systemd/system-sleep/80-broadcom-aspm" "system/files/usr/lib/systemd/system-sleep/80-broadcom-aspm" "0755")
    (file "/etc/systemd/system/broadcom-aspm-restore.service" "system/files/systemd/system/broadcom-aspm-restore.service" "0644")
    # Thunderbolt ACPI regions cached at the right PCI address: resume ~3 s, not ~23 s
    (file "/usr/local/sbin/ws-tb-acpi-seed" "system/files/usr/local/sbin/ws-tb-acpi-seed" "0755")
    (file "/etc/systemd/system/ws-tb-acpi-seed.service" "system/files/systemd/system/ws-tb-acpi-seed.service" "0644")
    # Hibernation: t2bce off before the image, on after it (ws-t2-detach), in
    # the system and in the dracut initrd of a resume boot (update-initramfs -u).
    (file "/usr/local/sbin/ws-t2-detach" "system/files/usr/local/sbin/ws-t2-detach" "0755")
    (file "/usr/lib/systemd/system-sleep/60-ws-t2-hibernate" "system/files/usr/lib/systemd/system-sleep/60-ws-t2-hibernate" "0755")
    (file "/etc/systemd/system/systemd-hibernate.service.d/ws-t2-nofreeze.conf" "system/files/systemd/system/ws-t2-nofreeze.conf" "0644")
    (file "/etc/systemd/system/systemd-hybrid-sleep.service.d/ws-t2-nofreeze.conf" "system/files/systemd/system/ws-t2-nofreeze.conf" "0644")
    (file "/etc/systemd/system/systemd-suspend-then-hibernate.service.d/ws-t2-nofreeze.conf" "system/files/systemd/system/ws-t2-nofreeze.conf" "0644")
    (file "/etc/dracut.conf.d/ws-hibernate.conf" "system/files/dracut/ws-hibernate.conf" "0644")
    (file "/usr/lib/dracut/modules.d/95ws-t2-resume/module-setup.sh" "system/files/dracut/95ws-t2-resume/module-setup.sh" "0755")
    (file "/usr/lib/dracut/modules.d/95ws-t2-resume/ws-t2-resume.sh" "system/files/dracut/95ws-t2-resume/ws-t2-resume.sh" "0755")
    (file "/usr/lib/dracut/modules.d/95ws-t2-resume/ws-t2-resume.service" "system/files/dracut/95ws-t2-resume/ws-t2-resume.service" "0644")
    (file "/usr/lib/dracut/modules.d/95ws-t2-resume/ws-t2-resume-up.service" "system/files/dracut/95ws-t2-resume/ws-t2-resume-up.service" "0644")
    # When: lid and GNOME Suspend -> suspend-then-hibernate (24 h of S3),
    # power key and GNOME Hibernate (workstation-hibernate@local) -> hibernate.
    (file "/etc/systemd/sleep.conf.d/85-ws-hibernate-delay.conf" "system/files/sleep.conf.d/85-ws-hibernate-delay.conf" "0644")
    (file "/etc/systemd/logind.conf.d/ws-sleep-keys.conf" "system/files/logind.conf.d/ws-sleep-keys.conf" "0644")
    (file "/etc/systemd/system/systemd-suspend.service.d/ws-suspend-then-hibernate.conf" "system/files/systemd/system/ws-suspend-then-hibernate.conf" "0644")
    (file "/usr/local/share/polkit-1/rules.d/50-ws-hibernate.rules" "system/files/polkit/50-ws-hibernate.rules" "0644")

    # AMD dGPU off and off the PCI bus when booted with ws.dgpu=off (rEFInd "Ubuntu")
    (file "/usr/local/sbin/ws-dgpu-off" "system/files/usr/local/sbin/ws-dgpu-off" "0755")
    (file "/etc/systemd/system/ws-dgpu-off.service" "system/files/systemd/system/ws-dgpu-off.service" "0644")
    # The AMD's CPU port parked like macOS does, at boot and after resume.
    (file "/usr/local/sbin/ws-dgpu-park" "system/files/usr/local/sbin/ws-dgpu-park" "0755")
    (file "/usr/lib/systemd/system-sleep/70-ws-dgpu-park" "system/files/usr/lib/systemd/system-sleep/70-ws-dgpu-park" "0755")
    # t2gmux (helpws plan-dgpu) is built and installed but never loaded by
    # alias: apple-gmux drives the gmux.
    (file "/etc/modprobe.d/t2gmux.conf" "system/files/modprobe/t2gmux.conf" "0644")

    # T2 base (t2linux setup, captured in phase -1)
    (file "/etc/udev/rules.d/30-amdgpu-pm.rules" "system/files/udev/30-amdgpu-pm.rules" "0644")
    (file "/etc/udev/rules.d/99-network-t2-ncm.rules" "system/files/udev/99-network-t2-ncm.rules" "0644")
    (file "/etc/NetworkManager/conf.d/99-network-t2-ncm.conf" "system/files/NetworkManager/conf.d/99-network-t2-ncm.conf" "0644")
    (file "/etc/modprobe.d/apple-gmux.conf" "system/files/modprobe/apple-gmux.conf" "0644")
    (file "/etc/modules-load.d/t2.conf" "system/files/modules-load.d/t2.conf" "0644")
    (file "/etc/systemd/system/get-apple-firmware.service" "system/files/systemd/system/get-apple-firmware.service" "0644")
  ];

  units = {
    "systemd-backlight@backlight:gmux_backlight.service" = "static";
    "ws-touchbar-fn.service" = "enabled";
    "get-apple-firmware.service" = "enabled";
    "ws-dgpu-off.service" = "enabled";
    "broadcom-aspm-restore.service" = "static";
    "ws-tb-acpi-seed.service" = "enabled";
  };

  # Restarted by every `ws system apply`, as ws-keyboard-system-apply did.
  restart = [
    "ws-touchbar-fn.service"
    # Also start save/restore in the current boot; apply only triggers input udev events.
    "systemd-backlight@backlight:gmux_backlight.service"
  ];
}
