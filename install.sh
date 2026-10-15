#!/usr/bin/env bash
set -euo pipefail

# The first command on a fresh Ubuntu 26.04 with / on Btrfs (ws help setup),
# in a terminal:
#
#   wget -qO- https://raw.githubusercontent.com/kkkingqz/wsconfig/main/install.sh \
#     | bash -s -- --repo URL|PATH | --new [DIR] [--host NAME] [--core REV]
#
# What ws needs before it runs: git, gh, python3-tomlkit, xdg-terminal-exec,
# sg (util-linux-extra); the subvolume @nix at /nix, then Nix of apt and
# its daemon, the group nix-users. Then ws setup of the core in the store
# at one revision, which stays until the end of setup (ws help plan-v2,
# 9.0 and 9.4): REV of --core (a branch, a tag or a commit; main without
# it) is resolved once to its commit, built into the GC root
# ~/.local/state/wsconfig/setup/ws and recorded in .../setup/core. The
# other arguments are those of ws setup. A second run changes nothing it
# did already.

core_git="${WS_INSTALL_GIT:-https://github.com/kkkingqz/wsconfig.git}"
core_raw="${WS_INSTALL_RAW:-https://raw.githubusercontent.com/kkkingqz/wsconfig}"
core_flake="${WS_INSTALL_FLAKE:-github:kkkingqz/wsconfig}"
os_release="${WS_INSTALL_OS_RELEASE:-/etc/os-release}"
state="${XDG_STATE_HOME:-$HOME/.local/state}/wsconfig/setup"

die() {
    printf 'install.sh: %s\n' "$*" >&2
    exit 1
}

say() {
    printf '\n== %s\n' "$*"
}

ref=main
args=()
while (($#)); do
    case "$1" in
        --core) (($# >= 2)) || die "--core needs a REV"; ref="$2"; shift 2 ;;
        *) args+=("$1"); shift ;;
    esac
done

[[ $EUID -ne 0 ]] || die "run as the desktop user, not root"
# shellcheck disable=SC1090 # the file of the system
version="$(. "$os_release" && echo "${ID:-}-${VERSION_ID:-}")"
[[ "$version" == ubuntu-26.04 ]] || die "Ubuntu 26.04 only (this is $version)"
[[ "$(findmnt -no FSTYPE /)" == btrfs ]] \
    || die "/ is not Btrfs: install Ubuntu with Btrfs for / (ws help rebuild, section 2)"
command -v sudo >/dev/null 2>&1 || die "sudo not found"
sudo -v || die "sudo needed"

installed() {
    [[ "$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null)" == "install ok installed" ]]
}

apt_install() {
    local -a missing=()
    local p
    for p in "$@"; do
        installed "$p" || missing+=("$p")
    done
    ((${#missing[@]})) || return 0
    say "apt: ${missing[*]}"
    sudo apt-get update
    sudo apt-get install -y "${missing[@]}"
}

apt_install git gh python3-tomlkit xdg-terminal-exec util-linux-extra

# The revision: a commit as it is, else the branch or the tag of the core.
if [[ "$ref" =~ ^[0-9a-f]{40}$ ]]; then
    rev="$ref"
else
    rev="$(git ls-remote "$core_git" "refs/heads/$ref" "refs/tags/$ref" "refs/tags/$ref^{}" \
        | sort -k2 | awk 'END { print $1 }')" || die "git ls-remote $core_git failed (network?)"
    [[ -n "$rev" ]] || die "the core has no branch or tag $ref"
fi
echo "Core: $ref → $rev"

# @nix before Nix: the store is a subvolume of its own, out of the
# snapshots of / (ws help rebuild, section 3). lib/btrfs.bash of the same
# revision.
say "/nix on the subvolume @nix"
btrfs_lib="$(mktemp)"
trap 'rm -f "$btrfs_lib"' EXIT
wget -qO "$btrfs_lib" "$core_raw/$rev/lib/btrfs.bash" || die "cannot fetch lib/btrfs.bash of $rev"
# shellcheck source=lib/btrfs.bash
. "$btrfs_lib"
subvolume_mount @nix /nix noatime,compress=zstd:1

apt_install nix-bin nix-setup-systemd

say "Nix: the daemon and the group nix-users"
if systemctl is-enabled --quiet nix-daemon.socket 2>/dev/null; then
    echo "nix-daemon.socket enabled"
else
    sudo systemctl enable nix-daemon.socket
fi
if systemctl is-active --quiet nix-daemon.socket; then
    echo "nix-daemon.socket active"
else
    # The postinst of nix-setup-systemd starts nix-daemon.service before the
    # socket, which then refuses to listen: socket activation, as after a
    # reboot.
    sudo systemctl stop nix-daemon.service
    sudo systemctl start nix-daemon.socket
fi
user="$(id -un)"
if getent group nix-users | cut -d: -f4 | tr ',' '\n' | grep -qx "$user"; then
    echo "$user is in nix-users"
else
    sudo usermod -aG nix-users "$user"
fi

# The group reaches this session only through sg (a new login has it).
as_nix_user() {
    local cmd
    cmd="$(printf '%q ' "$@")"
    if id -nG | tr ' ' '\n' | grep -qx nix-users; then
        "$@"
    else
        sg nix-users -c "$cmd"
    fi
}

say "ws $rev"
mkdir -p "$state"
export NIX_CONFIG="experimental-features = nix-command flakes"
as_nix_user nix build --out-link "$state/ws" "$core_flake/$rev#ws" \
    || die "nix build $core_flake/$rev#ws failed"
echo "$rev" > "$state/core"

# The terminal of wget | bash; WS_SETUP_TTY replaces it (tests), ws setup
# reads it then.
[[ -n "${WS_SETUP_TTY:-}" ]] || exec </dev/tty
rm -f "$btrfs_lib"
trap - EXIT
if id -nG | tr ' ' '\n' | grep -qx nix-users; then
    exec "$state/ws/bin/ws" setup "${args[@]}"
fi
exec sg nix-users -c "exec $(printf '%q ' "$state/ws/bin/ws" setup "${args[@]}")"
