# Shared Btrfs boundary checks; deploy beside both helpers.
die() { printf 'wsbackup: %s\n' "$*" >&2; exit 1; }
token() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]] || die "invalid ID: $1"; }
uuid() { [[ "$1" =~ ^[[:xdigit:]]{8}(-[[:xdigit:]]{4}){3}-[[:xdigit:]]{12}$ ]] || die 'invalid UUID'; }
scope_check() { [[ "$1" == home || "$1" == vms ]] || die 'invalid scope'; }
safe_path() {
    [[ "$1" =~ ^/[A-Za-z0-9_./-]+$ && "$1" != / && "$1" != */../* && "$1" != */.. ]] || die 'unsafe path'
    [[ "$1" != *//* && "$1" != */./* && "$1" != */. && "$1" != */ ]] || die 'unsafe path'
    local p="$1"
    while [[ "$p" != / ]]; do
        [[ ! -L "$p" ]] || die "symlink path: $p"
        p="$(dirname -- "$p")"
    done
}
filesystem_check() {
    [[ -d "$1" ]] || die "directory missing: $1"
    [[ "$(findmnt -nro FSTYPE -T "$1")" == btrfs ]] || die 'expected Btrfs filesystem'
    [[ "$(findmnt -nro UUID -T "$1")" == "$fs_uuid" ]] || die 'wrong filesystem UUID'
}
inspect_snapshot() {
    safe_path "$1"
    filesystem_check "$1"
    local show
    show="$(btrfs subvolume show "$1")"
    snapshot_uuid="$(awk '$1 == "UUID:" {print $2}' <<<"$show")"
    received_uuid="$(awk '$1 == "Received" && $2 == "UUID:" {print $3}' <<<"$show")"
    uuid "$snapshot_uuid"
    [[ "$(btrfs property get -ts "$1" ro)" == 'ro=true' ]] || die 'snapshot is not read-only'
    [[ "$received_uuid" == - ]] && received_uuid=""
    [[ -z "$received_uuid" ]] || uuid "$received_uuid"
}
snapshot_json() {
    printf '{"uuid":"%s","received_uuid":"%s","ro":true}\n' "$snapshot_uuid" "$received_uuid"
}
