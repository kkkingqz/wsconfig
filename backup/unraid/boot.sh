#!/bin/bash
# Unraid boot hook for the workstation backup receiver. Run as root at every
# boot, from /boot/config/go:
#
#     bash /boot/config/wsbackup/boot.sh
#
# Unraid restores /etc, /usr/local and the users from its image at boot. This
# re-creates the dedicated SSH user, installs the receiver from the flash copy
# with root ownership and adds its sshd and sudo rules. A repeated run changes
# nothing. It never touches root's own keys or other users.
#
# Flash layout (/boot/config/wsbackup):
#     boot.sh  authorized_keys  receiver.conf  btrfs-common.bash
#     unraid/wsbackup-receiver  unraid/catalog.bash
set -euo pipefail
umask 022

src="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
prefix="${WSBACKUP_PREFIX:-}"  # alternate root for checking this script; empty on the server
user=wsbackup
lib=/usr/local/libexec/wsbackup
receiver="$lib/unraid/wsbackup-receiver"
conf="$lib/receiver.conf"
keys=/etc/ssh/wsbackup_authorized_keys
command="sudo -n $receiver $conf"

log() { logger -t wsbackup -- "$*" 2>/dev/null || true; printf 'wsbackup: %s\n' "$*" >&2; }
fail() { log "$*"; exit 1; }

for f in unraid/wsbackup-receiver unraid/catalog.bash btrfs-common.bash receiver.conf authorized_keys; do
    [[ -f "$src/$f" && ! -L "$src/$f" ]] || fail "missing $src/$f"
done

# 1. The SSH user. Password "*" means no password login, but the account is not
# locked: sshd with PAM rejects locked ("!") accounts even for public keys.
# Its own group keeps it out of the "Match Group root" forwarding exception.
if ! id -u "$user" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/empty --no-create-home --shell /bin/bash "$user"
fi
usermod -p '*' "$user"

# 2. Receiver and keys. Flash permissions are not trusted; install root-owned copies.
install -d -o root -g root -m 0755 "$prefix$lib" "$prefix$lib/unraid"
install -o root -g root -m 0755 "$src/unraid/wsbackup-receiver" "$prefix$receiver"
install -o root -g root -m 0644 "$src/unraid/catalog.bash" "$prefix$lib/unraid/catalog.bash"
install -o root -g root -m 0644 "$src/btrfs-common.bash" "$prefix$lib/btrfs-common.bash"
install -o root -g root -m 0600 "$src/receiver.conf" "$prefix$conf"
install -o root -g root -m 0644 "$src/authorized_keys" "$prefix$keys"

# 3. sudo: exactly this command. The receiver reads the requested operation
# from SSH_ORIGINAL_COMMAND, which sudo drops unless kept.
tmp="$(mktemp)"
trap 'rm -f "$tmp" "$tmp.sshd"' EXIT
cat >"$tmp" <<EOF
# Managed by /boot/config/wsbackup/boot.sh
Defaults!$receiver env_keep += "SSH_ORIGINAL_COMMAND"
$user ALL=(root) NOPASSWD: $receiver $conf
EOF
visudo -cqf "$tmp" || fail 'generated sudoers rule is invalid'
install -o root -g root -m 0440 "$tmp" "$prefix/etc/sudoers.d/wsbackup"

# 4. sshd. Unraid edits only addresses and port in place (rc.sshd), so these
# lines survive its reloads. Match blocks must come last.
cfg="$prefix/etc/ssh/sshd_config"
sed '/^# wsbackup begin/,/^# wsbackup end/d' "$cfg" >"$tmp.sshd"
# Only extend an existing allow list; adding one where none exists would lock others out.
sed -ri "/^AllowUsers /{/[[:space:]]$user([[:space:]]|\$)/!s/\$/ $user/}" "$tmp.sshd"
cat >>"$tmp.sshd" <<EOF
# wsbackup begin (managed by /boot/config/wsbackup/boot.sh)
Match User $user
	AuthorizedKeysFile $keys
	ForceCommand $command
	PasswordAuthentication no
	KbdInteractiveAuthentication no
	PermitTTY no
	AllowTcpForwarding no
	AllowAgentForwarding no
	AllowStreamLocalForwarding no
	X11Forwarding no
	PermitTunnel no
# wsbackup end
EOF
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
