# Virtual machines (helpws virt), on hosts with vm = "yes" in facts.nix. The
# host layer is apt (virt/apt.txt), system/virt.nix and bootstrap.sh: VM
# state on the subvolume @vms with the libvirt paths bound into it (pool
# `default` at /var/lib/libvirt/images, no copy-on-write), NAT network
# `default`, group libvirt. VM definitions are libvirt state, not declared
# here; ws collect keeps their XML. Here: the user side.
{ config, ... }:
{
  # Disk images and ISOs, reachable from $HOME.
  home.file."VMs".source = config.lib.file.mkOutOfStoreSymlink "/var/lib/libvirt/images";
}
