# shellcheck shell=bash disable=SC2154 # repo: the check's own
# Result contract of the owner checks, sourced by them. ws check runs every
# owner with --json and reads only the object printed by check_finish:
#   {"status": "pass|warn|fail", "passes": N, "warnings": N, "failures": N,
#    "messages": [{"level": "pass|warn|fail|info", "text": "..."}]}
# Without --json the same messages are printed for people; that text may
# change freely.

check_json=false
check_n_pass=0
check_n_warn=0
check_n_fail=0
check_messages=()

# --json: stdout carries only the JSON object (fd 3); everything else a
# check prints goes to stderr.
check_json_mode() {
    check_json=true
    exec 3>&1 1>&2
}

check_msg() {
    check_messages+=("$1"$'\t'"$2")
    [[ "$check_json" == true ]] || printf '  %-5s %s\n' "${1^^}" "$2"
}

pass() { ((check_n_pass += 1)); check_msg pass "$*"; }
warn() { ((check_n_warn += 1)); check_msg warn "$*"; }
fail() { ((check_n_fail += 1)); check_msg fail "$*"; }
info() { check_msg info "$*"; }

section() {
    [[ "$check_json" == true ]] || printf '\n%s\n%s\n' "$1" \
        '------------------------------------------------------------------------'
}

have() { command -v "$1" >/dev/null 2>&1; }

# A string fact of this host (ws fact: hardware, boot, ...), empty when the
# host is unknown. Checks of hardware parts (T2, Touch Bar, dGPU) run only on
# the hardware that has them. Needs $repo.
host_fact() { "$repo/bin/ws" fact "$1" 2>/dev/null; }

# Prints the summary (text or JSON); returns 1 when a check failed.
check_finish() {
    local status=pass
    ((check_n_warn == 0)) || status=warn
    ((check_n_fail == 0)) || status=fail
    if [[ "$check_json" == true ]]; then
        printf '%s\0' "${check_messages[@]}" | python3 -c '
import json, sys
msgs = [m.split("\t", 1) for m in sys.stdin.read().split("\0") if m]
print(json.dumps({"status": sys.argv[1], "passes": int(sys.argv[2]),
    "warnings": int(sys.argv[3]), "failures": int(sys.argv[4]),
    "messages": [{"level": l, "text": t} for l, t in msgs]}))
' "$status" "$check_n_pass" "$check_n_warn" "$check_n_fail" >&3
    else
        printf '\n  PASS=%d WARN=%d FAIL=%d\n' "$check_n_pass" "$check_n_warn" "$check_n_fail"
    fi
    ((check_n_fail == 0))
}
