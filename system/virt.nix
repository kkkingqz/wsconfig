# Hosts with vm = "yes" (helpws virt): UEFI for VMs with variables in qcow2,
# so libvirt can take internal snapshots of UEFI guests (bootstrap.sh makes
# the qcow2 template on @vms).
{ file, ... }:
{
  files = [
    (file "/etc/qemu/firmware/30-edk2-x86_64-secure-enrolled-qcow2-vars.json" "system/files/qemu/firmware/30-edk2-x86_64-secure-enrolled-qcow2-vars.json" "0644")
  ];
}
