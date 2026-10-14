# Roots and helpers shared by the bash tools (helpws plan-v2, 2.1). A tool
# sources it right after `set`, by its own path; the only place that
# resolves a tool's location:
#
#   . "$(dirname "$(readlink -f "$0")")/../lib/common.bash"
#
# Roots (helpws architecture-v2, 3):
#   WS_CORE    code: bin/, lib/, gnome/extensions, hooks; where this file is
#   WS_CONFIG  data: nix/hosts, the lists and catalogs, host choices
#   WS_STATE   this machine only
# WS_CORE is always where the running code is. WSCONFIG (tests, another
# checkout) sets WS_CONFIG; WS_CONFIG and WS_STATE are exported and kept by
# the tools ws runs. Until stage 5 code and data are one checkout, and
# `repo`, what the tools still use for both, is WS_CONFIG: as before,
# ${WSCONFIG:-the checkout of the tool}.
#
# The state directory name is also in lib/ws_common.py, flake.nix
# (wsState) and terminal/fish/completions/ws.fish; tests/test_common.py
# keeps them equal.

WS_CORE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS_CONFIG="${WSCONFIG:-${WS_CONFIG:-$WS_CORE}}"
WS_STATE="${WS_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/workstation}"
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

nix_bin() {
    command -v nix 2>/dev/null \
        || die "nix not found (apt: nix-bin nix-setup-systemd; helpws history-nix, phase 0)"
}
