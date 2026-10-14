"""Roots and helpers shared by the Python tools (helpws plan-v2, 2.1); the
counterpart of lib/common.bash. A tool in bin/ imports it after putting
lib/ on sys.path by its own location:

    sys.path.insert(0, str(Path(os.path.realpath(__file__)).parent.parent / "lib"))
    import ws_common

CORE is where the running code is, CONFIG the data (nix/hosts, the lists
and catalogs), STATE this machine only. WSCONFIG (tests, another checkout)
sets CONFIG; WS_CONFIG and WS_STATE from ws are kept. Until stage 5 CORE
and CONFIG are one checkout.
"""
import os
from pathlib import Path
import sys

# The state directory name; lib/common.bash, flake.nix (wsState) and
# terminal/fish/completions/ws.fish have it too (tests/test_common.py).
STATE_NAME = "workstation"

CORE = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get("WSCONFIG") or os.environ.get("WS_CONFIG") or CORE)


def state_dir():
    """WS_STATE, else $XDG_STATE_HOME/workstation; read when called, so a
    test can set the environment after import."""
    if os.environ.get("WS_STATE"):
        return Path(os.environ["WS_STATE"])
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(base) / STATE_NAME


def die(prog, message):
    """PROG: MESSAGE on stderr, exit 1 (die of lib/common.bash): SystemExit
    with a text prints it and exits 1; callers may catch it."""
    raise SystemExit(f"{prog}: {message}")


# Manifests that Nix writes for the tools are JSON (builtins.toJSON; helpws
# plan-v2, 2.6). An entry of a list is found by its "name".
def get(data, *keys):
    """The value at KEYS, or None."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list):
            data = next((e for e in data if isinstance(e, dict) and e.get("name") == key), None)
        else:
            return None
        if data is None:
            return None
    return data


def lines(value):
    """How the bash tools read a value: a scalar as itself, an object as
    its keys, a list as the names (or values) of its entries."""
    if value is None:
        return []
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, dict):
        return list(value)
    if isinstance(value, list):
        return [e["name"] if isinstance(e, dict) and "name" in e else str(e) for e in value]
    return [str(value)]


def load(path):
    """A manifest, or None when it is missing or not JSON."""
    import json
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def rows(value, fields):
    """The FIELDS of each entry of a list, tab-separated: for `while IFS=$'\\t'
    read`."""
    if not isinstance(value, list):
        return []
    return ["\t".join(str(e.get(f, "")) if isinstance(e, dict) else "" for f in fields)
            for e in value]


if __name__ == "__main__":
    # For the bash tools (no jq on the hosts); nothing is printed for a
    # missing file or key:
    #   ws_common.py get FILE [KEY...]
    #   ws_common.py rows FILE FIELD,FIELD... [KEY...]
    if len(sys.argv) >= 3 and sys.argv[1] == "get":
        out = lines(get(load(sys.argv[2]), *sys.argv[3:]))
    elif len(sys.argv) >= 4 and sys.argv[1] == "rows":
        out = rows(get(load(sys.argv[2]), *sys.argv[4:]), sys.argv[3].split(","))
    else:
        print("usage: ws_common.py get FILE [KEY...] | rows FILE FIELD,... [KEY...]", file=sys.stderr)
        sys.exit(64)
    for line in out:
        print(line)
