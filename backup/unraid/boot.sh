#!/bin/bash
# Unraid boot hook for the workstation backup receiver. Run as root at every
# boot, from /boot/config/go:
#
#     bash /boot/config/wsbackup/boot.sh
#
# Unraid restores /etc, /usr/local and the users from its image at boot. This
# re-creates the dedicated SSH users, installs the receiver from the flash
# copy with root ownership and adds their sshd and sudo rules. A repeated run
# changes nothing. It never touches root's own keys or other users.
#
# One user per workstation, each with its own key file, receiver config
# (HOST_ID) and forced command: a key can only ever reach its own host's
# copies. The first workstation keeps the names of the single-host layout.
#
# Flash layout (/boot/config/wsbackup):
#     boot.sh  btrfs-common.bash  unraid/wsbackup-receiver  unraid/catalog.bash
#     receiver.conf  authorized_keys            user wsbackup (mbp16)
#     hosts/HOST/receiver.conf  hosts/HOST/authorized_keys
#                                               user wsbackup-HOST, HOST_ID=HOST
set -euo pipefail
umask 022

src="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
prefix="${WSBACKUP_PREFIX:-}"  # alternate root for checking this script; empty on the server
lib=/usr/local/libexec/wsbackup
receiver="$lib/unraid/wsbackup-receiver"

log() { logger -t wsbackup -- "$*" 2>/dev/null || true; printf 'wsbackup: %s\n' "$*" >&2; }
fail() { log "$*"; exit 1; }

for f in unraid/wsbackup-receiver unraid/catalog.bash btrfs-common.bash; do
    [[ -f "$src/$f" && ! -L "$src/$f" ]] || fail "missing $src/$f"
done

# The workstations, one line each: USER FLASH-DIR CONF KEYS.
hosts=()
if [[ -e "$src/receiver.conf" || -e "$src/authorized_keys" ]]; then
    hosts+=("wsbackup $src $lib/receiver.conf /etc/ssh/wsbackup_authorized_keys")
fi
for d in "$src"/hosts/*/; do
    [[ -d "$d" ]] || continue
    host="$(basename "$d")"
    # It becomes part of a user name: lowercase and short.
    [[ "$host" =~ ^[a-z0-9][a-z0-9_-]{0,22}$ ]] || fail "invalid host directory: $d"
    grep -qx "HOST_ID=$host" "$d/receiver.conf" 2>/dev/null \
        || fail "${d}receiver.conf: HOST_ID must be $host"
    hosts+=("wsbackup-$host ${d%/} $lib/hosts/$host.conf /etc/ssh/wsbackup-${host}_authorized_keys")
done
((${#hosts[@]})) || fail "no workstation: $src/receiver.conf or $src/hosts/HOST/"
for h in "${hosts[@]}"; do
    read -r _ dir _ _ <<<"$h"
    for f in receiver.conf authorized_keys; do
        [[ -f "$dir/$f" && ! -L "$dir/$f" ]] || fail "missing $dir/$f"
    done
done

# 1. The SSH users. Password "*" means no password login, but the account is
# not locked: sshd with PAM rejects locked ("!") accounts even for public
# keys. Its own group keeps each out of the "Match Group root" forwarding
# exception.
for h in "${hosts[@]}"; do
    read -r user _ _ _ <<<"$h"
    if ! id -u "$user" >/dev/null 2>&1; then
        useradd --system --user-group --home-dir /var/empty --no-create-home --shell /bin/bash "$user"
    fi
    usermod -p '*' "$user"
done

# 2. Receiver, configs and keys. Flash permissions are not trusted; install
# root-owned copies.
install -d -o root -g root -m 0755 "$prefix$lib" "$prefix$lib/unraid" "$prefix$lib/hosts"
install -o root -g root -m 0755 "$src/unraid/wsbackup-receiver" "$prefix$receiver"
install -o root -g root -m 0644 "$src/unraid/catalog.bash" "$prefix$lib/unraid/catalog.bash"
install -o root -g root -m 0644 "$src/btrfs-common.bash" "$prefix$lib/btrfs-common.bash"
for h in "${hosts[@]}"; do
    read -r _ dir conf keys <<<"$h"
    install -o root -g root -m 0600 "$dir/receiver.conf" "$prefix$conf"
    install -o root -g root -m 0644 "$dir/authorized_keys" "$prefix$keys"
done

# 3. sudo: exactly the receiver with each user's own config. The receiver
# reads the requested operation from SSH_ORIGINAL_COMMAND, which sudo drops
# unless kept.
tmp="$(mktemp)"
trap 'rm -f "$tmp" "$tmp.sshd"' EXIT
{
    echo "# Managed by /boot/config/wsbackup/boot.sh"
    echo "Defaults!$receiver env_keep += \"SSH_ORIGINAL_COMMAND\""
    for h in "${hosts[@]}"; do
        read -r user _ conf _ <<<"$h"
        echo "$user ALL=(root) NOPASSWD: $receiver $conf"
    done
} >"$tmp"
visudo -cqf "$tmp" || fail 'generated sudoers rule is invalid'
install -o root -g root -m 0440 "$tmp" "$prefix/etc/sudoers.d/wsbackup"

# 4. sshd. Unraid edits only addresses and port in place (rc.sshd), so these
# lines survive its reloads. Match blocks must come last.
cfg="$prefix/etc/ssh/sshd_config"
sed '/^# wsbackup begin/,/^# wsbackup end/d' "$cfg" >"$tmp.sshd"
# Only extend an existing allow list; adding one where none exists would lock others out.
for h in "${hosts[@]}"; do
    read -r user _ _ _ <<<"$h"
    sed -ri "/^AllowUsers /{/[[:space:]]$user([[:space:]]|\$)/!s/\$/ $user/}" "$tmp.sshd"
done
{
    echo "# wsbackup begin (managed by /boot/config/wsbackup/boot.sh)"
    for h in "${hosts[@]}"; do
        read -r user _ conf keys <<<"$h"
        printf '%s\n' \
            "Match User $user" \
            "	AuthorizedKeysFile $keys" \
            "	ForceCommand sudo -n $receiver $conf" \
            "	PasswordAuthentication no" \
            "	KbdInteractiveAuthentication no" \
            "	PermitTTY no" \
            "	AllowTcpForwarding no" \
            "	AllowAgentForwarding no" \
            "	AllowStreamLocalForwarding no" \
            "	X11Forwarding no" \
            "	PermitTunnel no"
    done
    echo "# wsbackup end"
} >>"$tmp.sshd"
if cmp -s "$tmp.sshd" "$cfg"; then
    log 'receiver installed; sshd already configured'
    exit 0
fi
sshd -t -f "$tmp.sshd" || fail 'generated sshd_config is invalid; left unchanged'
cat "$tmp.sshd" >"$cfg"
if [[ -z "$prefix" && -r /var/run/sshd.pid ]]; then
    # Restarts only the listener; open sessions stay connected.
    /etc/rc.d/rc.sshd reload
fi
log 'receiver installed; sshd configured'
