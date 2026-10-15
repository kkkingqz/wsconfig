# Subvolumes of the root filesystem, each mounted by a line of /etc/fstab
# (ws help rebuild, section 3): @nix, @vms, @steam, @wsbackup. Sourced by
# ws setup (libexec/ws-prepare) and by install.sh, which fetches this file
# of its own revision before Nix is there (ws help plan-v2, 9.3).
#
# Needs die. With btrfs_dry_run=true the changes are only printed.

btrfs_dry_run="${btrfs_dry_run:-false}"

btrfs_run() {
    if [[ "$btrfs_dry_run" == true ]]; then
        printf 'would run: %s\n' "$*"
    else
        "$@"
    fi
}

# Subvolume NAME of the root filesystem mounted at DIR by an fstab line with
# OPTIONS. DIR must not hold data yet: it would be hidden by the mount. A
# second run changes nothing.
subvolume_mount() {
    local name="$1" dir="$2" options="$3" top=/run/btrfs-top line dev uuid
    if findmnt -no OPTIONS "$dir" 2>/dev/null | tr ',' '\n' | grep -qx "subvol=/$name"; then
        echo "$dir is mounted from $name"
        return
    fi
    [[ "$(findmnt -no FSTYPE /)" == btrfs ]] || die "/ is not Btrfs (ws help rebuild, section 3)"
    dev="$(findmnt -no SOURCE / | sed 's/\[.*$//')"
    uuid="$(findmnt -no UUID /)"
    [[ -n "$uuid" ]] || die "cannot determine the UUID of /"
    if [[ -e "$dir" ]] && [[ -n "$(sudo find "$dir" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
        die "$dir exists, is not empty and is not $name; move its content away first"
    fi
    btrfs_run sudo install -d "$top"
    btrfs_run sudo mount -o subvolid=5 "$dev" "$top"
    if [[ "$btrfs_dry_run" == false ]] && sudo btrfs subvolume show "$top/$name" >/dev/null 2>&1; then
        echo "$name already exists"
    else
        btrfs_run sudo btrfs subvolume create "$top/$name"
    fi
    btrfs_run sudo umount "$top"
    btrfs_run sudo rmdir "$top"
    if grep -Eq "^[^#]*[[:space:]]${dir}[[:space:]]" /etc/fstab; then
        echo "$dir already in fstab"
    else
        line="UUID=$uuid  $dir  btrfs  subvol=$name,$options  0 0"
        if [[ "$btrfs_dry_run" == true ]]; then
            echo "would append to /etc/fstab: $line"
        else
            sudo cp -a /etc/fstab "/etc/fstab.before-$name-$(date +%Y%m%d-%H%M%S)"
            printf '%s\n' "$line" | sudo tee -a /etc/fstab >/dev/null
        fi
    fi
    btrfs_run sudo install -d -m0755 "$dir"
    btrfs_run sudo systemctl daemon-reload
    btrfs_run sudo mount "$dir"
}
