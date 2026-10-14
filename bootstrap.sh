#!/usr/bin/env bash
set -euo pipefail

# First steps on a fresh Ubuntu (helpws rebuild, helpws history-nix):
# @nix subvolume at /nix → apt packages (nix/hosts/apt.txt, nix/hosts/<host>/apt.txt,
# nix/hosts/machine-apt.txt,
# virt/apt.txt, steam/apt.txt, gaming/apt.txt) → VM state on @vms (images,
# nvram, qemu XML bound into libvirt), pool and network (virt/bootstrap.bash)
# → Steam data on @steam (steam/bootstrap.bash) → local backup copies on
# @wsbackup → groups nix-users, libvirt, input → fish as login shell → first
# `ws switch`. The VM parts only with
# vm = true in host.toml [layers], the Steam parts with nativeSteam = true,
# the Game Mode list with gameMode = true. A container host (boot =
# "container") skips what its image or the server holds.
#
# Runs as the desktop user from the checkout at ~/<wsconfig of
# nix/hosts/<host>/host.toml> and calls sudo itself. Every step checks
# the current state first, so a second run changes nothing.
#
#   ./bootstrap.sh [--dry-run]
#
# Afterwards: reboot, then ws system apply → ws apply → log out and
# in → ws apply → ws check.

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.bash
. "$repo/lib/common.bash"
ws_prog=bootstrap
# shellcheck source=lib/apt.bash
. "$repo/lib/apt.bash"
dry_run=false


case "${1:-}" in
    --dry-run) dry_run=true ;;
    "") ;;
    *) die "usage: bootstrap.sh [--dry-run]" ;;
esac

# Commands that change the system; --dry-run only prints them.
run() {
    if [[ "$dry_run" == true ]]; then
        printf 'would run: %s\n' "$*"
    else
        "$@"
    fi
}

[[ $EUID -ne 0 ]] || die "run as the desktop user, not root"
command -v sudo >/dev/null 2>&1 || die "sudo not found"
host="$("$repo/bin/ws" host)"
host_list="$repo/nix/hosts/$host/apt.txt"
toml="nix/hosts/$host/host.toml"
[[ -r "$repo/$toml" ]] || die "no $toml"
# The checkout path is a fact of the host: home-manager links point there.
expected="$HOME/$("$repo/bin/ws" fact wsconfig)" || die "no wsconfig in [host] of $toml"
[[ "$repo" == "$expected" ]] \
    || die "checkout must be $expected (wsconfig in $toml), not $repo"
# VM layer (helpws virt): packages of virt/apt.txt, @vms and libvirt.
# The layers are true or false; ws fact prints them as yes and no.
vm="$("$repo/bin/ws" fact vm)" || die "no vm in [layers] of $toml (true or false)"
[[ "$vm" == yes || "$vm" == no ]] || die "vm in $toml must be true or false, not \"$vm\""
# Native Steam and the Game Mode session (helpws plan-legion-go).
native_steam="$("$repo/bin/ws" fact nativeSteam)" \
    || die "no nativeSteam in [layers] of $toml (true or false)"
[[ "$native_steam" == yes || "$native_steam" == no ]] \
    || die "nativeSteam in $toml must be true or false, not \"$native_steam\""
game_mode="$("$repo/bin/ws" fact gameMode)" \
    || die "no gameMode in [layers] of $toml (true or false)"
[[ "$game_mode" == yes || "$game_mode" == no ]] \
    || die "gameMode in $toml must be true or false, not \"$game_mode\""
[[ "$game_mode" == no || "$native_steam" == yes ]] \
    || die "gameMode = true needs nativeSteam = true in $toml"
echo "Host: $host (vm = $vm, widgets = $("$repo/bin/ws" fact widgets 2>/dev/null), nativeSteam = $native_steam, gameMode = $game_mode)"
# A container host (helpws plan-wsgnomebox): the image holds the apt
# packages, groups and login shell, /nix is a directory of the server; no
# Btrfs, subvolumes or local backup copies.
container=false
[[ "$("$repo/bin/ws" fact boot)" != container ]] || container=true

if [[ "$container" == true ]]; then
    mountpoint -q /nix || die "/nix is not a mount: the container needs it from the server (helpws plan-wsgnomebox)"
else
    [[ "$(findmnt -no FSTYPE /)" == btrfs ]] || die "/ is not Btrfs (rebuild.md, section 3)"
    findmnt -no OPTIONS / | tr ',' '\n' | grep -qx 'subvol=/@' \
        || die "/ is not the subvolume @: first ~/wsconfig/bin/ws btrfs make (helpws rebuild, section 3)"
    [[ ! -e /var/lib/ws-btrfs-layout/old-root ]] \
        || echo "The old root is still on the top level of Btrfs: ws btrfs make removes it."
    root_dev="$(findmnt -no SOURCE / | sed 's/\[.*$//')"
    root_uuid="$(findmnt -no UUID /)"
    [[ -n "$root_uuid" ]] || die "cannot determine the UUID of /"
fi

# Subvolume NAME of the root filesystem mounted at DIR by an fstab line with
# OPTIONS. DIR must not hold data yet: it would be hidden by the mount.
subvolume_mount() {
    local name="$1" dir="$2" options="$3" top=/run/btrfs-top line
    if findmnt -no OPTIONS "$dir" 2>/dev/null | tr ',' '\n' | grep -qx "subvol=/$name"; then
        echo "$dir is mounted from $name"
        return
    fi
    if [[ -e "$dir" ]] && [[ -n "$(sudo find "$dir" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
        die "$dir exists, is not empty and is not $name; move its content away first"
    fi
    run sudo install -d "$top"
    run sudo mount -o subvolid=5 "$root_dev" "$top"
    if [[ "$dry_run" == false ]] && sudo btrfs subvolume show "$top/$name" >/dev/null 2>&1; then
        echo "$name already exists"
    else
        run sudo btrfs subvolume create "$top/$name"
    fi
    run sudo umount "$top"
    run sudo rmdir "$top"
    if grep -Eq "^[^#]*[[:space:]]${dir}[[:space:]]" /etc/fstab; then
        echo "$dir already in fstab"
    else
        line="UUID=$root_uuid  $dir  btrfs  subvol=$name,$options  0 0"
        if [[ "$dry_run" == true ]]; then
            echo "would append to /etc/fstab: $line"
        else
            sudo cp -a /etc/fstab "/etc/fstab.before-$name-$(date +%Y%m%d-%H%M%S)"
            printf '%s\n' "$line" | sudo tee -a /etc/fstab >/dev/null
        fi
    fi
    run sudo install -d -m0755 "$dir"
    run sudo systemctl daemon-reload
    run sudo mount "$dir"
}

echo
echo "== 1. /nix on subvolume @nix"
if [[ "$container" == true ]]; then
    echo "/nix is a directory of the server"
else
    subvolume_mount @nix /nix noatime,compress=zstd:1
fi

echo
echo "== 2. apt"
if [[ "$container" == true ]]; then
    # Installed here they would be gone with the next container.
    echo "in the image (container/Dockerfile); ws check apt compares the lists"
else
    apt_install
fi

echo
echo "== 3. VM state on @vms, libvirt (helpws virt)"
if [[ "$vm" == yes ]]; then
    . "$repo/virt/bootstrap.bash"
else
    echo "vm = false in $toml: no VM layer"
fi

echo
echo "== 4. Steam data on @steam (helpws plan-legion-go)"
if [[ "$native_steam" == yes ]]; then
    . "$repo/steam/bootstrap.bash"
else
    echo "nativeSteam = false in $toml: no apt Steam"
fi

echo
echo "== 5. Local backup copies on @wsbackup (helpws backup)"
# A top-level subvolume of its own, like @vms: nested in @, the parents of
# the incremental backup would leave with @ on a Timeshift or Live USB
# restore. Only the local side; the receiver is helpws backup.
backup_root=/var/lib/workstation-backup
if [[ "$container" == true ]]; then
    echo "container: its data are directories of the server"
else
    subvolume_mount @wsbackup "$backup_root" noatime
    if [[ "$(stat -c %a "$backup_root" 2>/dev/null)" == 700 ]]; then
        echo "$backup_root is 0700"
    else
        run sudo chmod 0700 "$backup_root"
    fi
    run sudo bash "$repo/backup/wsbackup-source" --uuid "$root_uuid" --root "$backup_root" init
fi

echo
echo "== 6. Nix daemon and groups"
if systemctl is-enabled --quiet nix-daemon.socket 2>/dev/null; then
    echo "nix-daemon.socket enabled"
else
    run sudo systemctl enable nix-daemon.socket
fi
if systemctl is-active --quiet nix-daemon.socket; then
    echo "nix-daemon.socket active"
else
    # The postinst of nix-setup-systemd starts nix-daemon.service before the
    # socket, which then refuses to listen ("service already active"): hand
    # the daemon over to socket activation, as after a reboot.
    run sudo systemctl stop nix-daemon.service
    run sudo systemctl start nix-daemon.socket
fi
user="$(id -un)"
# input: xremap reads the keyboards (/dev/input/event*); a container gets
# its keys over RDP, not from /dev/input.
groups=(nix-users)
[[ "$container" == true ]] || groups+=(input)
[[ "$vm" == no ]] || groups+=(libvirt)
for group in "${groups[@]}"; do
    if getent group "$group" | cut -d: -f4 | tr ',' '\n' | grep -qx "$user"; then
        echo "$user is in $group"
    else
        run sudo usermod -aG "$group" "$user"
    fi
done

echo
echo "== 7. Login shell"
if [[ "$(getent passwd "$user" | cut -d: -f7)" == /usr/bin/fish ]]; then
    echo "login shell is fish"
else
    run sudo chsh -s /usr/bin/fish "$user"
fi

echo
echo "== 8. First ws switch"
# Before the first switch there is no ~/.config/nix/nix.conf yet, and the
# nix-users membership applies only to new logins: sg (util-linux-extra on
# Ubuntu 26.04) runs the switch with it when this session lacks the group.
# Files home-manager would replace are kept as *.pre-hm.
switch="NIX_CONFIG='experimental-features = nix-command flakes' '$repo/bin/ws' switch -b pre-hm"
if id -nG | tr ' ' '\n' | grep -qx nix-users; then
    run bash -c "$switch"
elif [[ "$dry_run" == true ]]; then
    echo "would run: sg nix-users -c \"$switch\""
else
    sg nix-users -c "$switch"
fi

echo
# New groups reach only processes of a new systemd user manager, and GNOME
# starts from it; a log out keeps the old one while another session of the
# user (ssh) is open.
if [[ "$container" == true ]]; then
    # The system tree is in the image (container/system-install).
    echo "Done. Log out and in (PATH from 00-nix.fish), then:"
else
    echo "Done. Reboot (groups ${groups[*]}; PATH from 00-nix.fish), then:"
    echo "  ws system apply     # system files (sudo)"
fi
echo "  ws apply            # user layer; log out and in; ws apply again"
echo "  ws check"
