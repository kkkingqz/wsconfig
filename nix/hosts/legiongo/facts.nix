# Lenovo Legion Go (gen 1, 8APU1, DMI 83E1): handheld on Ubuntu 26.04 with
# the XanMod kernel, GRUB only (helpws plan-legion-go).
{
  # `ws host` finds the host by it (set in the installer).
  hostname = "legiongo";
  user = "king";
  wsconfig = "wsconfig";
  hardware = "legion-go";
  # No VMs on the handheld (helpws virt).
  vm = "no";
  # Native Steam (steam/apt.txt, i386, data on @steam in
  # ~/.local/share/Steam; ws check steam) and the Game Mode
  # session (gaming/apt.txt, system/gaming.nix; helpws plan-legion-go).
  nativeSteam = "yes";
  gameMode = "yes";
  boot = "grub";
  # Not for xremap (keyboard/xremap.nix): the virtual keyboard InputPlumber
  # makes of the controller (src/input/target/keyboard.rs). The controllers
  # themselves InputPlumber hides.
  xremapIgnore = [ "InputPlumber Keyboard" ];
  kernelParams = [
    "quiet" "splash"
    # Xbox controllers over Bluetooth (as Bazzite does everywhere).
    "bluetooth.disable_ertm=1"
    # XanMod defaults to the performance governor. power-profiles-daemon
    # sets governor, EPP and boost per profile once it runs; this covers the
    # boot before it and a stopped PPD.
    "cpufreq.default_governor=powersave"
    # Swap: zswap in front of /swap/swapfile (ws-suspend swap-setup 16g).
    # zstd is built into XanMod; in the generic fallback kernel it is a
    # module and zswap may start with lzo.
    "zswap.enabled=1" "zswap.compressor=zstd"
  ];
}
