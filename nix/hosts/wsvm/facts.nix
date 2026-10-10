# Test VM of phase 6 (helpws history-nix): clean Ubuntu 26.04 on the
# generic kernel in libvirt on mbp16 (helpws virt), GRUB only.
{
  # `ws host` finds the host by it (the installer's default).
  hostname = "test-Standard-PC-Q35-ICH9-2009";
  user = "test";
  wsconfig = "wsconfig";
  hardware = "generic-pc";
  # No VMs inside the test VM (helpws virt).
  vm = "no";
  # Neither native Steam nor the Game Mode session in the test VM.
  nativeSteam = "no";
  gameMode = "no";
  boot = "grub";
  kernelParams = [ "quiet" "splash" ];
}
