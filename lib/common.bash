# Roots and helpers shared by the bash tools (ws help plan-v2, 2.1). A tool
# sources it right after `set`, by its own path; the only place that
# resolves a tool's location:
#
#   . "$(dirname "$(readlink -f "$0")")/../lib/common.bash"
#
# Roots (ws help architecture-v2, 3):
#   WS_CORE    code: bin/ws, libexec/, lib/, gnome/extensions, hooks; where this file is
#   WS_CONFIG  data: hosts, the lists and catalogs, host choices
#   WS_STATE   this machine only
# WS_CORE is always where the running code is: a checkout (~/wsconfig/bin/ws)
# or the core in the store (nix/pkgs/ws.nix, ~/.local/bin/ws). WSCONFIG
# (tests, another checkout) sets WS_CONFIG; WS_CONFIG and WS_STATE are
# exported and kept by the tools ws runs. Otherwise WS_CONFIG is the
# checkout itself when it holds a configuration (wsconfig.toml: code and
# data in one repository until stage 8.11), and for the core in the store
# or a checkout of the core alone the config of WS_STATE/host.json, else
# ~/wsconfig (config_root of lib/ws_common.py). `repo`, what the tools use for the
# data, is WS_CONFIG.
#
# The state directory name is also in lib/ws_common.py, lib/mkconfig.nix
# (wsState) and terminal/fish/completions/ws.fish; tests/test_common.py
# keeps them equal.

WS_CORE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS_STATE="${WS_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/wsconfig}"
if [[ -n "${WSCONFIG:-${WS_CONFIG:-}}" ]]; then
    WS_CONFIG="${WSCONFIG:-$WS_CONFIG}"
elif [[ ! -e "$WS_CORE/.wsconfig-package" && -e "$WS_CORE/wsconfig.toml" ]]; then
    WS_CONFIG="$WS_CORE"
else
    WS_CONFIG="$(WS_STATE="$WS_STATE" python3 "$WS_CORE/lib/ws_common.py" config)"
fi
export WS_CORE WS_CONFIG WS_STATE
# shellcheck disable=SC2034 # read by the tools that source this file
repo="$WS_CONFIG"

# Prefix of die: the command name, or what the tool sets (ws_prog="ws btrfs").
ws_prog="${0##*/}"

die() {
    printf '%s: %s\n' "$ws_prog" "$*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

# --core PATH of ws apply, diff, update, news and checkpoint (ws help
# plan-v2, 8.6): the configuration builds with the core checkout PATH
# instead of the revision its flake.lock pins; flake.lock stays as it is.
# WS_CORE_PATH carries it to the tools ws runs. nix_args: what every nix
# call on the configuration adds. A Git checkout is taken as git+file (the
# tracked files, uncommitted changes included, as a flake sees itself),
# anything else as path:.
# shellcheck disable=SC2034 # read by the tools that source this file
nix_args=()
use_core() {
    [[ -d "$1" ]] || die "--core $1: no such directory"
    WS_CORE_PATH="$(cd "$1" && pwd)"
    [[ -n "$(python3 "$WS_CORE/lib/ws_common.py" get "$WS_CONFIG/flake.lock" nodes root inputs wsconfig)" ]] \
        || die "--core: the configuration $WS_CONFIG has no flake input wsconfig (only a configuration repository of its own has one, ws help plan-v2, 8.9)"
    export WS_CORE_PATH
    # shellcheck disable=SC2034 # read by the tools that source this file
    if git -C "$WS_CORE_PATH" rev-parse --show-toplevel >/dev/null 2>&1; then
        nix_args=(--override-input wsconfig "git+file:$WS_CORE_PATH")
    else
        nix_args=(--override-input wsconfig "path:$WS_CORE_PATH")
    fi
}
[[ -z "${WS_CORE_PATH:-}" ]] || use_core "$WS_CORE_PATH"

# A configuration of its own (ws help plan-v2, 8.6): its root has no bin/ws.
# Every file it tracks is then data; a checkout of core and data together
# (until 8.11) tells them apart by the data patterns of bin/ws.
separate_config() {
    [[ ! -e "$WS_CONFIG/bin/ws" ]]
}

# Runs a tool of the core by name: ws (bin/) or an internal executor
# (libexec/), as the step tables of ws name them.
ws_run() {
    local name="$1"
    shift
    if [[ "$name" == ws ]]; then
        "$WS_CORE/bin/ws" "$@"
    else
        "$WS_CORE/libexec/$name" "$@"
    fi
}

# The flake sees only files known to git; a new .nix file that is not added
# would silently be missing from the build.
check_untracked() {
    local untracked
    if separate_config; then
        # A configuration of its own: every file is the flake's.
        untracked="$(git -C "$repo" ls-files --others --exclude-standard)"
    else
        untracked="$(git -C "$repo" ls-files --others --exclude-standard -- \
            '*.nix' flake.lock)"
    fi
    [[ -z "$untracked" ]] || die "untracked flake files (git add them first):
$untracked"
}

# A command of a module changed what this host should have: ws apply
# MODULE... builds and applies it (ws help plan-v2, stage 6). Nothing inside
# ws apply (WS_APPLYING): it applies everything itself. WS_APPLY_CMD
# replaces the command (tests).
apply_module() {
    [[ -z "${WS_APPLYING:-}" ]] || return 0
    printf '\napplying: ws apply %s\n' "$*"
    # shellcheck disable=SC2086 # WS_APPLY_CMD is a command line
    ${WS_APPLY_CMD:-"$WS_CORE/bin/ws" apply} "$@"
}

nix_bin() {
    command -v nix 2>/dev/null \
        || die "nix not found (apt: nix-bin nix-setup-systemd; ws help history-nix, phase 0)"
}

# A value of a JSON manifest from Nix: manifest_get FILE KEY... prints a
# scalar, the keys of an object or the names of a list, one per line
# (lib/ws_common.py; no jq on the hosts).
manifest_get() {
    python3 "$WS_CORE/lib/ws_common.py" get "$@"
}

# The FIELDs of each entry of a list, tab-separated, one entry per line:
# manifest_rows FILE FIELD,FIELD... KEY...
manifest_rows() {
    python3 "$WS_CORE/lib/ws_common.py" rows "$@"
}
