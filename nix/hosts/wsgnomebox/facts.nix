# GNOME desktop in a Docker container on tower (Unraid), RDP login
# (helpws plan-wsgnomebox). No hardware, kernel or boot loader of its own:
# the image is built from this checkout (container/), the system tree goes
# into the image, /nix and the home are directories of tower.
{
  # `ws host` finds the host by it (docker --hostname).
  hostname = "wsgnomebox";
  user = "king";
  wsconfig = "wsconfig";
  # The RTX 3060 of tower through the NVIDIA container runtime.
  hardware = "container-nvidia";
  # No VMs, no native Steam, no Game Mode in the container.
  vm = "no";
  nativeSteam = "no";
  gameMode = "no";
  # Quickshell widgets on the GNOME panel (helpws widgets).
  widgets = "yes";
  # The RDP client sets the size; GNOME scales on its own.
  displayScale = "1";
  # No boot loader, kernel or initramfs: the container starts systemd.
  boot = "container";
  kernelParams = [ ];
  # Set by the installer on a real machine; container/image-setup here.
  timezone = "Europe/Kyiv";

  # The container on the server (ws container build|run|status); ~ in a
  # mount target is the home of user. Data are
  # directories of the server, on NVMe pools: nothing under /mnt/user, so
  # no array disk wakes up (projects is cache only on nvmtwo).
  container = {
    server = "root@192.168.113.113";
    image = "local/wsgnomebox";
    # RDP of gnomebox-desktop is 3389.
    port = "3390";
    mounts = [
      "/mnt/nvm/wsgnomebox/home:~"
      "/mnt/nvm/wsgnomebox/nix:/nix"
      "/mnt/nvm/wsgnomebox/grd:/var/lib/gnome-remote-desktop"
      # password, rdp-user, rdp-password (ws-container-init, ws-rdp-init)
      "/mnt/nvm/wsgnomebox/config:/config:ro"
      "/mnt/nvmtwo/projects:~/Projects"
      "/mnt/nvm/ue5:~/UE5"
    ];
    # The render node mutter and Vulkan use, FUSE for fuse-overlayfs and
    # Flatpak, tun for rootless podman networking (passt).
    devices = [ "/dev/dri/renderD128" "/dev/fuse" "/dev/net/tun" ];
  };
}
