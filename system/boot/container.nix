# A container host (ws help plan-wsgnomebox): systemd is PID 1 of a Docker
# container, the server owns the kernel, the boot and the devices.
# container/Dockerfile installs this tree into the image
# (container/system-install), so a recreated container starts with it; the
# entrypoint and the RDP setup run on every start.
{ file, ... }:
{
  files = [
    (file "/usr/local/sbin/ws-container-init" "system/files/container/ws-container-init" "0755")

    # GNOME Remote Login: TLS and credentials before gnome-remote-desktop.
    (file "/usr/local/sbin/ws-rdp-init" "system/files/container/ws-rdp-init" "0755")
    (file "/etc/systemd/system/ws-rdp-init.service" "system/files/container/ws-rdp-init.service" "0644")
    (file "/etc/systemd/system/gnome-remote-desktop.service.d/10-ws-rdp-init.conf" "system/files/container/10-ws-rdp-init.conf" "0644")

    # Podman (distrobox) on fuse-overlayfs, for root and the user.
    (file "/etc/containers/storage.conf" "system/files/container/storage.conf" "0644")
  ];

  # GDM is the display manager by the package (display-manager.service),
  # as on a real machine.
  units = {
    "gnome-remote-desktop.service" = "enabled";
    # The server owns devices and the network: udev, udisks and colord
    # fail without them, NetworkManager has no link to wait for.
    "systemd-udevd.service" = "masked";
    "systemd-udevd-control.socket" = "masked";
    "systemd-udevd-kernel.socket" = "masked";
    "systemd-udevd-varlink.socket" = "masked";
    "systemd-udev-trigger.service" = "masked";
    "systemd-udev-settle.service" = "masked";
    "tpm-udev.service" = "masked";
    "tpm-udev.path" = "masked";
    "udisks2.service" = "masked";
    "colord.service" = "masked";
    "NetworkManager-wait-online.service" = "masked";
    # Docker configures the network; netplan has nothing to render.
    "netplan-configure.service" = "masked";
    # No Bluetooth adapter in the container (fails on every boot).
    "bluetooth.service" = "masked";
  };
}
