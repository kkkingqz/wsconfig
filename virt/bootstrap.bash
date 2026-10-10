# shellcheck shell=bash
# Step 3 of bootstrap.sh on hosts with vm = "yes" (helpws virt): VM state on
# @vms, libvirt pool and network. Sourced by bootstrap.sh: uses its run, die,
# subvolume_mount, dry_run, repo, host.

# Everything a VM is made of lives on the subvolume @vms, outside the
# snapshots of @: a rollback of @ leaves disks, definitions and UEFI
# variables alone. @vms is mounted at /var/lib/vms; libvirt sees its own
# paths through bind mounts:
#   images/  /var/lib/libvirt/images  disks, ISOs (pool default; no CoW,
#                                     qcow2 on CoW Btrfs fragments)
#   qemu/    /var/lib/libvirt/qemu    UEFI variables (nvram/), snapshot
#                                     metadata, saved states
#   swtpm/   /var/lib/libvirt/swtpm   TPM state of each VM
#   xml/     /etc/libvirt/qemu        VM and network XML, autostart links
#   firmware/                         template of UEFI variables in qcow2
vms=/var/lib/vms
images=/var/lib/libvirt/images
binds=("images $images" "qemu /var/lib/libvirt/qemu" "swtpm /var/lib/libvirt/swtpm" "xml /etc/libvirt/qemu")
virsh=(sudo virsh -q -c qemu:///system)
libvirt_units=(libvirtd.service libvirtd.socket libvirtd-ro.socket libvirtd-admin.socket)

bound() {
    [[ "$(findmnt -no SOURCE "$2" 2>/dev/null)" == *"[/@vms/$1]" ]]
}
layout_done=true
for b in "${binds[@]}"; do
    bound $b || layout_done=false
done
# Layout of 2026-09-28: @vms mounted at the images directory itself.
old_layout=false
[[ "$(findmnt -no SOURCE "$images" 2>/dev/null)" == *"[/@vms]" ]] && old_layout=true

stopped=false
if [[ "$layout_done" == false ]] && systemctl is-active --quiet libvirtd.service 2>/dev/null; then
    # root: the user may not have the libvirt group in this session yet.
    running="$(sudo virsh -q -c qemu:///system list --name 2>/dev/null || true)"
    running="$(sed '/^$/d' <<<"$running")"
    [[ -z "$running" ]] || die "shut down the running VMs first and wait for \"shut off\" (virsh -c qemu:///system domstate NAME): $(echo $running)"
    run sudo systemctl stop "${libvirt_units[@]}"
    stopped=true
fi

if [[ "$old_layout" == true ]]; then
    echo "moving @vms from $images to $vms"
    run sudo umount "$images"
    if [[ "$dry_run" == true ]]; then
        echo "would drop the fstab line of $images"
    else
        sudo cp -a /etc/fstab "/etc/fstab.before-vms-layout-$(date +%Y%m%d-%H%M%S)"
        sudo sed -i "\\|^[^#]*[[:space:]]$images[[:space:]]|d" /etc/fstab
    fi
    run sudo systemctl daemon-reload
fi
subvolume_mount @vms "$vms" noatime
run sudo chmod 0755 "$vms"

if [[ "$old_layout" == true ]]; then
    # The images were the top of @vms: move them into images/ (same
    # subvolume, so a rename; files keep their no-CoW attribute).
    run sudo install -d "$vms/images"
    run sudo chattr +C "$vms/images"
    if [[ "$dry_run" == true ]]; then
        echo "would move the top of $vms into $vms/images"
    else
        sudo find "$vms" -mindepth 1 -maxdepth 1 ! -name images ! -name qemu ! -name swtpm ! -name xml ! -name firmware \
            -exec mv -t "$vms/images" {} +
    fi
fi

# Bind SUBDIR of @vms onto TARGET. The first time, what the package or an
# earlier install left in TARGET is moved into @vms; the old directory stays
# as TARGET.before-vms.
for b in "${binds[@]}"; do
    set -- $b
    sub="$1" target="$2" store="$vms/$1"
    if bound "$sub" "$target"; then
        echo "$target is @vms/$sub"
        continue
    fi
    if [[ "$dry_run" == true ]]; then
        echo "would bind $store onto $target (moving its content into @vms first)"
    else
        sudo install -d "$store" "$target"
        if [[ -z "$(sudo find "$store" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
            sudo chown --reference="$target" "$store"
            sudo chmod --reference="$target" "$store"
            # Sockets of earlier runs (libvirt stopped, VMs off) are stale.
            sudo find "$target" -type s -delete
            sudo cp -a "$target"/. "$store"/
        elif [[ -n "$(sudo find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
            die "both $store and $target hold data; merge them by hand"
        fi
        if [[ -n "$(sudo find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
            old="$target.before-vms-$(date +%Y%m%d-%H%M%S)"
            sudo mv "$target" "$old"
            sudo install -d "$target"
            sudo chown --reference="$old" "$target"
            sudo chmod --reference="$old" "$target"
            echo "old $target kept as $old"
        fi
    fi
    if grep -Eq "^[^#]*[[:space:]]$target[[:space:]]" /etc/fstab; then
        echo "$target already in fstab"
    else
        line="$store  $target  none  bind,x-systemd.requires-mounts-for=$vms  0 0"
        if [[ "$dry_run" == true ]]; then
            echo "would append to /etc/fstab: $line"
        else
            printf '%s\n' "$line" | sudo tee -a /etc/fstab >/dev/null
        fi
    fi
    run sudo systemctl daemon-reload
    run sudo mount "$target"
done

if [[ "$dry_run" == false ]] && lsattr -d "$images" 2>/dev/null | cut -d' ' -f1 | grep -q C; then
    echo "$images: no copy-on-write"
else
    run sudo chattr +C "$images"
fi
if [[ "$(stat -c '%U:%G %a' "$images" 2>/dev/null)" == "root:libvirt 2775" ]]; then
    echo "$images: root:libvirt 2775"
else
    run sudo chown root:libvirt "$images"
    run sudo chmod 2775 "$images"
fi
# UEFI variables in qcow2: libvirt takes internal snapshots of a UEFI VM
# only with them and cannot convert the raw template of the ovmf package
# itself. The descriptor in /etc/qemu/firmware (ws system apply) points
# new VMs here; rerun after an ovmf update changes the template.
vars=/usr/share/OVMF/OVMF_VARS_4M.ms.fd
vars_qcow2="$vms/firmware/OVMF_VARS_4M.ms.qcow2"
if [[ -r "$vars_qcow2" ]] && qemu-img compare -q -f raw -F qcow2 "$vars" "$vars_qcow2" 2>/dev/null; then
    echo "$vars_qcow2 matches $vars"
else
    run sudo install -d -m 0755 "$vms/firmware"
    run sudo qemu-img convert -f raw -O qcow2 "$vars" "$vars_qcow2"
    run sudo chmod 0644 "$vars_qcow2"
    echo "$vars_qcow2 made from $vars"
fi
[[ "$stopped" == false ]] || run sudo systemctl start "${libvirt_units[@]}"

# Output first, then grep: grep -q stops reading, virsh gets SIGPIPE, and
# pipefail would count the match as a failure.
info_of() {
    [[ "$dry_run" == false ]] || return 0
    "${virsh[@]}" "$@" 2>/dev/null || true
}
if [[ -n "$(info_of pool-info default)" ]]; then
    echo "pool default defined"
else
    run "${virsh[@]}" pool-define-as default dir --target "$images"
fi
if grep -Eq '^Autostart:[[:space:]]+yes' <<<"$(info_of pool-info default)"; then
    echo "pool default autostarts"
else
    run "${virsh[@]}" pool-autostart default
fi
if grep -Eq '^State:[[:space:]]+running' <<<"$(info_of pool-info default)"; then
    echo "pool default running"
else
    run "${virsh[@]}" pool-start default
fi
# NAT network of the package (virbr0); Wi-Fi cannot be bridged.
if grep -Eq '^Autostart:[[:space:]]+yes' <<<"$(info_of net-info default)"; then
    echo "network default autostarts"
else
    run "${virsh[@]}" net-autostart default
fi
if grep -Eq '^Active:[[:space:]]+yes' <<<"$(info_of net-info default)"; then
    echo "network default active"
else
    run "${virsh[@]}" net-start default
fi

# virt-manager defines a pool for each directory picked with "Browse Local";
# through ~/VMs (a link to the images) qemu gets paths in HOME (0750) and
# must be able to pass through it: search only, not read.
if getfacl -p "$HOME" 2>/dev/null | grep -qx 'user:libvirt-qemu:--x'; then
    echo "qemu may pass through $HOME"
else
    run setfacl -m u:libvirt-qemu:x "$HOME"
fi
