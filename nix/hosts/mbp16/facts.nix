# What this machine differs in from the others. New facts are added only
# when a second machine actually needs another value.
{
  # `ws host` finds the host by it.
  hostname = "MacBookPro-k";
  user = "king";
  # The checkout of this repository, relative to $HOME. home-manager links
  # into it, bootstrap.sh insists on it; scripts find it from their own path.
  wsconfig = "wsconfig";
  hardware = "t2-mbp16";
  # Virtual machines (helpws virt): "yes" sets up the VM layer — packages of
  # virt/apt.txt, @vms with libvirt (bootstrap.sh), OVMF descriptor, ~/VMs,
  # ws check virt; "no" leaves it out.
  vm = "yes";
  boot = "refind-grub-recovery";
  kernelParams = [
    "quiet" "splash" "intel_iommu=on" "iommu=pt" "pm_async=off"
    # Hibernation: /swap/swapfile in @swap on the root filesystem; the
    # offset is its first page (ws-suspend swap-setup prints both;
    # helpws suspend, Hibernate). A new swapfile means a new offset.
    "resume=UUID=0cfd2add-849f-47b9-865d-2ac821ca529c" "resume_offset=31286754"
  ];
  # Only the default rEFInd entry "Ubuntu": ws-dgpu-off.service powers the
  # AMD dGPU off and parks its CPU port, and the kernel owns ASPM with the
  # powersave policy (L1 on Thunderbolt, Clock PM; helpws suspend, ASPM).
  # amdgpu is not loaded at all there: ws-dgpu-off removes the card from
  # the bus and gmux cuts its power without it (amdgpu took ~9 s only to be
  # switched off, and GDM waits for ws-dgpu-off; helpws workstation, GRAPHICS).
  # "Ubuntu (AMD)" (refind.conf) and GRUB (recovery) boot without them.
  refindDefaultParams = [
    "ws.dgpu=off" "modprobe.blacklist=amdgpu"
    "pcie_aspm=force" "pcie_aspm.policy=powersave"
  ];
  # Btrfs with @, @home, @nix; root= in refind_linux.conf.
  rootUuid = "0cfd2add-849f-47b9-865d-2ac821ca529c";
  # rEFInd ESP (nvme0n1p3), not mounted in normal operation.
  refindEspPartuuid = "b3575417-21a5-43db-9c6e-dc2dd5510c76";
}
