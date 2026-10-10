#!/usr/bin/env bash
set -euo pipefail

# First steps on a fresh Ubuntu (helpws rebuild, helpws history-nix):
# @nix subvolume at /nix → apt packages (nix/hosts/apt.txt, nix/hosts/<host>/apt.txt,
# virt/apt.txt, steam/apt.txt, gaming/apt.txt) → VM state on @vms (images,
# nvram, qemu XML bound into libvirt), pool and network (virt/bootstrap.bash)
# → Steam data on @steam (steam/bootstrap.bash) → local backup copies on
# @wsbackup → groups nix-users, libvirt, input → fish as login shell → first
# `ws switch`. The VM parts only with
# vm = "yes" in facts.nix, the Steam parts with nativeSteam = "yes", the
# Game Mode list with gameMode = "yes".
#
# Runs as the desktop user from the checkout at ~/<wsconfig of
# nix/hosts/<host>/facts.nix> and calls sudo itself. Every step checks
# the current state first, so a second run changes nothing.
#
#   ./bootstrap.sh [--dry-run]
#
# Afterwards: reboot, then ws system apply → ws apply → log out and
# in → ws apply → ws check.

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dry_run=false

die() {
    echo "bootstrap: $*" >&2
    exit 1
}

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
[[ "$(findmnt -no FSTYPE /)" == btrfs ]] || die "/ is not Btrfs (rebuild.md, section 3)"
findmnt -no OPTIONS / | tr ',' '\n' | grep -qx 'subvol=/@' \
    || die "/ is not the subvolume @: first ~/wsconfig/bin/ws btrfs make (helpws rebuild, section 3)"
[[ ! -e /var/lib/ws-btrfs-layout/old-root ]] \
    || echo "The old root is still on the top level of Btrfs: ws btrfs make removes it."

host="$("$repo/bin/ws" host)"
host_list="$repo/nix/hosts/$host/apt.txt"
[[ -r "$repo/nix/hosts/$host/facts.nix" ]] || die "no nix/hosts/$host/facts.nix"
# The checkout path is a fact of the host: home-manager links point there.
expected="$HOME/$("$repo/bin/ws" fact wsconfig)" || die "no wsconfig in nix/hosts/$host/facts.nix"
[[ "$repo" == "$expected" ]] \
    || die "checkout must be $expected (wsconfig in nix/hosts/$host/facts.nix), not $repo"
# VM layer (helpws virt): packages of virt/apt.txt, @vms and libvirt.
vm="$("$repo/bin/ws" fact vm)" || die "no vm in nix/hosts/$host/facts.nix (\"yes\" or \"no\")"
[[ "$vm" == yes || "$vm" == no ]] || die "vm in nix/hosts/$host/facts.nix must be \"yes\" or \"no\", not \"$vm\""
# Native Steam and the Game Mode session (helpws plan-legion-go).
native_steam="$("$repo/bin/ws" fact nativeSteam)" \
    || die "no nativeSteam in nix/hosts/$host/facts.nix (\"yes\" or \"no\")"
[[ "$native_steam" == yes || "$native_steam" == no ]] \
    || die "nativeSteam in nix/hosts/$host/facts.nix must be \"yes\" or \"no\", not \"$native_steam\""
game_mode="$("$repo/bin/ws" fact gameMode)" \
    || die "no gameMode in nix/hosts/$host/facts.nix (\"yes\" or \"no\")"
[[ "$game_mode" == yes || "$game_mode" == no ]] \
    || die "gameMode in nix/hosts/$host/facts.nix must be \"yes\" or \"no\", not \"$game_mode\""
[[ "$game_mode" == no || "$native_steam" == yes ]] \
    || die "gameMode = \"yes\" needs nativeSteam = \"yes\" in nix/hosts/$host/facts.nix"
echo "Host: $host (vm = $vm, nativeSteam = $native_steam, gameMode = $game_mode)"

# Package and PPA lines of the apt lists, without comments.
apt_lines() {
    local f
    local lists=("$repo/nix/hosts/apt.txt" "$host_list")
    [[ "$vm" == no ]] || lists+=("$repo/virt/apt.txt")
    [[ "$native_steam" == no ]] || lists+=("$repo/steam/apt.txt")
    [[ "$game_mode" == no ]] || lists+=("$repo/gaming/apt.txt")
    for f in "${lists[@]}"; do
        [[ -r "$f" ]] && sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' "$f"
    done
    return 0
}

root_dev="$(findmnt -no SOURCE / | sed 's/\[.*$//')"
root_uuid="$(findmnt -no UUID /)"
[[ -n "$root_uuid" ]] || die "cannot determine the UUID of /"

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
    if grep -Eq "^[^#]*[[:space:]]$dir[[:space:]]" /etc/fstab; then
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
subvolume_mount @nix /nix noatime,compress=zstd:1

echo
echo "== 2. apt"
mapfile -t ppas < <(apt_lines | sed -n 's/^ppa://p')
mapfile -t sources < <(apt_lines | sed -n 's/^source://p')
mapfile -t archs < <(apt_lines | sed -n 's/^arch://p')
mapfile -t packages < <(apt_lines | grep -v '^ppa:\|^purge:\|^source:\|^arch:')
mapfile -t purges < <(apt_lines | sed -n 's/^purge://p')
added=false
for ppa in "${ppas[@]}"; do
    if grep -rqsF "ppa.launchpadcontent.net/$ppa/" /etc/apt/sources.list.d/; then
        echo "PPA present: $ppa"
    else
        run sudo add-apt-repository -y --no-update "ppa:$ppa"
        added=true
    fi
done
# Other repositories of the host: nix/hosts/<host>/apt/NAME.sources (deb822)
# with its key NAME.asc, installed as ws-NAME; the file must point
# Signed-By at the installed key.
for name in "${sources[@]}"; do
    src="$repo/nix/hosts/$host/apt/$name.sources"
    key="$repo/nix/hosts/$host/apt/$name.asc"
    [[ -r "$src" && -r "$key" ]] \
        || die "source:$name needs nix/hosts/$host/apt/$name.sources and $name.asc"
    grep -qx "Signed-By: /etc/apt/keyrings/ws-$name.asc" "$src" \
        || die "nix/hosts/$host/apt/$name.sources: Signed-By must be /etc/apt/keyrings/ws-$name.asc"
    if cmp -s "$src" "/etc/apt/sources.list.d/ws-$name.sources" \
        && cmp -s "$key" "/etc/apt/keyrings/ws-$name.asc"; then
        echo "source present: $name"
    else
        run sudo install -D -m0644 "$key" "/etc/apt/keyrings/ws-$name.asc"
        run sudo install -D -m0644 "$src" "/etc/apt/sources.list.d/ws-$name.sources"
        added=true
    fi
done
# ws-NAME belongs to bootstrap.sh: one whose source: line is gone goes too,
# or apt would keep installing from it.
for f in /etc/apt/sources.list.d/ws-*.sources; do
    [[ -e "$f" ]] || continue
    name="${f##*/ws-}"
    name="${name%.sources}"
    [[ " ${sources[*]} " == *" $name "* ]] && continue
    run sudo rm -f "$f" "/etc/apt/keyrings/ws-$name.asc"
    added=true
done
for arch in "${archs[@]}"; do
    if dpkg --print-foreign-architectures | grep -qx "$arch"; then
        echo "architecture present: $arch"
    else
        run sudo dpkg --add-architecture "$arch"
        added=true
    fi
done
# Right after the first boot of a fresh install unattended-upgrades holds
# the dpkg lock for minutes: wait for it instead of failing (phase 6, wsvm).
apt_get=(sudo apt-get -o DPkg::Lock::Timeout=600)
missing=()
for pkg in "${packages[@]}"; do
    # "hold ok installed" counts too (linux-t2 is held).
    dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q ' ok installed$' \
        || missing+=("$pkg")
done
if ((${#missing[@]})); then
    run "${apt_get[@]}" update
    run "${apt_get[@]}" install -y --no-install-recommends "${missing[@]}"
else
    [[ "$added" == false ]] || run "${apt_get[@]}" update
    echo "all ${#packages[@]} packages installed"
fi
# A listed package the standard install already has as a dependency
# (python3-gi) stays auto-installed: apt autoremove could take it.
mapfile -t auto < <(apt-mark showauto "${packages[@]}" 2>/dev/null)
if ((${#auto[@]})); then
    run sudo apt-mark -o DPkg::Lock::Timeout=600 manual "${auto[@]}"
else
    echo "all listed packages marked manual"
fi
present=()
for pkg in "${purges[@]}"; do
    if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q ' installed$'; then
        present+=("$pkg")
    else
        echo "not installed: $pkg"
    fi
done
((${#present[@]} == 0)) || run "${apt_get[@]}" purge -y "${present[@]}"

echo
echo "== 3. VM state on @vms, libvirt (helpws virt)"
if [[ "$vm" == yes ]]; then
    . "$repo/virt/bootstrap.bash"
else
    echo "vm = \"$vm\" in nix/hosts/$host/facts.nix: no VM layer"
fi

echo
echo "== 4. Steam data on @steam (helpws plan-legion-go)"
if [[ "$native_steam" == yes ]]; then
    . "$repo/steam/bootstrap.bash"
else
    echo "nativeSteam = \"$native_steam\" in nix/hosts/$host/facts.nix: no apt Steam"
fi

echo
echo "== 5. Local backup copies on @wsbackup (helpws backup)"
# A top-level subvolume of its own, like @vms: nested in @, the parents of
# the incremental backup would leave with @ on a Timeshift or Live USB
# restore. Only the local side; the receiver is helpws backup.
backup_root=/var/lib/workstation-backup
subvolume_mount @wsbackup "$backup_root" noatime
if [[ "$(stat -c %a "$backup_root" 2>/dev/null)" == 700 ]]; then
    echo "$backup_root is 0700"
else
    run sudo chmod 0700 "$backup_root"
fi
run sudo bash "$repo/backup/wsbackup-source" --uuid "$root_uuid" --root "$backup_root" init

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
# input: xremap reads the keyboards (/dev/input/event*).
groups=(nix-users input)
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
echo "Done. Reboot (groups ${groups[*]}; PATH from 00-nix.fish), then:"
echo "  ws system apply     # system files (sudo)"
echo "  ws apply            # user layer; log out and in; ws apply again"
echo "  ws check"
