"""Roots and helpers shared by the Python tools (ws help plan-v2, 2.1); the
counterpart of lib/common.bash. A tool in libexec/ imports it after putting
lib/ on sys.path by its own location:

    sys.path.insert(0, str(Path(os.path.realpath(__file__)).parent.parent / "lib"))
    import ws_common

CORE is where the running code is, CONFIG the data (hosts, the lists
and catalogs), STATE this machine only. WSCONFIG (tests, another checkout)
sets CONFIG; WS_CONFIG and WS_STATE from ws are kept. Otherwise CONFIG is
the config of host.json in STATE, else ~/wsconfig: the core in the store
(PACKAGE_MARK) and a checkout of the core hold no data (ws help plan-v2,
8.11).
"""
import os
from pathlib import Path
import sys

# The state directory name; lib/common.bash, lib/mkconfig.nix (wsState) and
# terminal/fish/completions/ws.fish have it too (tests/test_common.py).
STATE_NAME = "wsconfig"

# A file at the root of the core in the store (nix/pkgs/ws.nix).
PACKAGE_MARK = ".wsconfig-package"
# At the root of a configuration: its schema version (ws help plan-v2, 8.5).
SCHEMA_FILE = "wsconfig.toml"
# The record of this machine in STATE: {"host": ID, "config": PATH}
# (ws_facts.py record writes it).
HOST_RECORD = "host.json"

CORE = Path(__file__).resolve().parent.parent


def state_dir():
    """WS_STATE, else $XDG_STATE_HOME/wsconfig; read when called, so a
    test can set the environment after import."""
    if os.environ.get("WS_STATE"):
        return Path(os.environ["WS_STATE"])
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(base) / STATE_NAME


def host_record():
    """host.json of the state as a dict; {} when it is missing or broken."""
    import json
    try:
        data = json.loads((state_dir() / HOST_RECORD).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def config_root(core=CORE):
    """The data root (see the module text)."""
    env = os.environ.get("WSCONFIG") or os.environ.get("WS_CONFIG")
    if env:
        return Path(env)
    recorded = host_record().get("config")
    if isinstance(recorded, str) and recorded:
        return Path(recorded)
    return Path.home() / "wsconfig"


CONFIG = config_root()


def git_add_new(path):
    """A file a command just created in a Git checkout (a host choice made
    for the first time): git add it, as ws apply adds nothing of a
    configuration of its own (ws help plan-v2, 8.6). Outside a checkout or
    without git nothing happens."""
    import subprocess
    path = Path(path)
    if not any((d / ".git").exists() for d in path.parents):
        return
    try:
        subprocess.run(["git", "-C", str(path.parent), "add", "--", path.name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except OSError:
        pass


def schema_problem(config=None):
    """Why this core cannot read the configuration (wsconfig.toml and
    lib/wsconfig-schema.toml, ws help plan-v2, 8.5), None when it can."""
    import tomllib
    supported = tomllib.loads((CORE / "lib/wsconfig-schema.toml").read_text())["supported"]
    path = Path(config or CONFIG) / SCHEMA_FILE
    reads = ", ".join(map(str, supported))
    try:
        version = tomllib.loads(path.read_text()).get("schema")
    except FileNotFoundError:
        return f"{path}: missing; this core reads schema {reads} (ws help plan-v2, 8.5)"
    except (OSError, tomllib.TOMLDecodeError) as e:
        return f"{path}: {e}"
    if version not in supported:
        return (f"{path}: the configuration is schema {version}, this core reads {reads}: "
                "it needs a migration")
    return None


def apply_module(*modules):
    """A command of a module changed what this host should have: ws apply
    MODULE... builds and applies it (ws help plan-v2, stage 6); nothing
    inside ws apply (WS_APPLYING). WS_APPLY_CMD replaces the command
    (tests). Exits with its status when it fails."""
    import shlex
    import subprocess
    if os.environ.get("WS_APPLYING"):
        return
    print(f"\napplying: ws apply {' '.join(modules)}", flush=True)
    cmd = shlex.split(os.environ["WS_APPLY_CMD"]) if os.environ.get("WS_APPLY_CMD") \
        else [str(CORE / "bin/ws"), "apply"]
    rc = subprocess.run([*cmd, *modules]).returncode
    if rc:
        raise SystemExit(rc)


def die(prog, message):
    """PROG: MESSAGE on stderr, exit 1 (die of lib/common.bash): SystemExit
    with a text prints it and exits 1; callers may catch it."""
    raise SystemExit(f"{prog}: {message}")


# Manifests that Nix writes for the tools are JSON (builtins.toJSON; ws help
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
    #   ws_common.py config       the data root (lib/common.bash)
    #   ws_common.py schema       exit 2 with the message when the core
    #                             cannot read the configuration
    if sys.argv[1:] == ["config"]:
        out = [str(CONFIG)]
    elif sys.argv[1:] == ["schema"]:
        problem = schema_problem()
        if problem:
            print(problem, file=sys.stderr)
            sys.exit(2)
        out = []
    elif len(sys.argv) >= 3 and sys.argv[1] == "get":
        out = lines(get(load(sys.argv[2]), *sys.argv[3:]))
    elif len(sys.argv) >= 4 and sys.argv[1] == "rows":
        out = rows(get(load(sys.argv[2]), *sys.argv[4:]), sys.argv[3].split(","))
    else:
        print("usage: ws_common.py get FILE [KEY...] | rows FILE FIELD,... [KEY...] | config | schema",
              file=sys.stderr)
        sys.exit(64)
    for line in out:
        print(line)
