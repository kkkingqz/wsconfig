#!/usr/bin/env python3
"""A new configuration from the template of the core (ws setup --new, ws
help plan-v2, 9.7):

    ws_template.py new --core CORE --metadata FILE DIR

DIR (new or empty) gets the files of CORE/template/ and a flake.lock that
pins the core at the revision of FILE (`nix flake metadata --json
github:kkkingqz/wsconfig/REV`) and nixpkgs, home-manager and wswidgets as
the flake.lock of that core does: the set its CI built. The inputs of the
core follow those of the configuration (template/flake.nix), as in the
lock `nix flake lock` writes. Nothing existing is overwritten.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

# The input of the core in template/flake.nix.
CORE_INPUT = "wsconfig"


def lock(core_lock, locked):
    """flake.lock of the configuration from the lock of the core and the
    locked reference of the core."""
    nodes = {k: v for k, v in core_lock["nodes"].items() if k != core_lock["root"]}
    inputs = dict(core_lock["nodes"][core_lock["root"]].get("inputs", {}))
    if CORE_INPUT in nodes or CORE_INPUT in inputs:
        raise ValueError(f"the lock of the core has an input {CORE_INPUT} already")
    for name, node in inputs.items():
        if not isinstance(node, str):
            raise ValueError(f"input {name} of the core follows another one: not a template input")
    nodes[CORE_INPUT] = {
        # template/flake.nix: inputs.wsconfig.inputs.NAME.follows = "NAME".
        "inputs": {name: [name] for name in sorted(inputs)},
        "locked": locked,
        "original": {k: locked[k] for k in ("owner", "repo", "type")},
    }
    inputs[CORE_INPUT] = CORE_INPUT
    nodes["root"] = {"inputs": dict(sorted(inputs.items()))}
    return {"nodes": dict(sorted(nodes.items())), "root": "root", "version": core_lock.get("version", 7)}


def new(core, metadata, target):
    core, target = Path(core), Path(target)
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"ws_template: {target} exists and is not empty: nothing is overwritten")
    # Attributes of nix itself (__final) are no part of a lock file.
    locked = {k: v for k, v in json.loads(Path(metadata).read_text())["locked"].items()
              if not k.startswith("__")}
    if locked.get("type") != "github" or not locked.get("rev"):
        raise SystemExit(f"ws_template: not a locked GitHub revision: {locked}")
    data = lock(json.loads((core / "flake.lock").read_text()), locked)
    shutil.copytree(core / "template", target, symlinks=False, dirs_exist_ok=True)
    for p in [target, *target.rglob("*")]:
        # The store copy is read-only.
        p.chmod(0o755 if p.is_dir() else 0o644)
    (target / "hosts").mkdir(exist_ok=True)
    # As nix writes it: sorted keys, two spaces.
    (target / "flake.lock").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return target


def main(argv):
    ap = argparse.ArgumentParser(prog="ws_template.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--core", required=True)
    n.add_argument("--metadata", required=True)
    n.add_argument("dir")
    a = ap.parse_args(argv)
    try:
        print(new(a.core, a.metadata, a.dir))
    except ValueError as e:
        raise SystemExit(f"ws_template: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
