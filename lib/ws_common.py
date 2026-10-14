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
