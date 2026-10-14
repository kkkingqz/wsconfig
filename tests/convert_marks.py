#!/usr/bin/env python3
"""One-off converter of the workstation marks (lib/ws_marks.py) into the
host choices (lib/ws_catalog.py), helpws plan-v2, stage 3. Goes with
ws_marks.py in 3.5.

    convert_marks.py CONFIG LIST MODULE [--fixed N]

Reads CONFIG/LIST (NAME... HOST=STATE... all=STATE), writes
CONFIG/nix/hosts/HOST/MODULE.toml for every own yes or no in line order and
prints NAME DEFAULT per line: all= of the line, else ask (the catalog
default). An own ask equal to the default is dropped; one that differs
cannot be written and stops the conversion. Then it checks that every host
of CONFIG/nix/hosts has the same state of every name as before.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ws_catalog  # noqa: E402
import ws_marks  # noqa: E402


def hosts(config):
    return sorted(p.name for p in (Path(config) / "nix/hosts").iterdir() if (p / "facts.nix").exists())


def name_of(marked, line):
    return " ".join(line.key) if marked.fixed else line.key[-1]


def convert(config, marked, module, all_hosts):
    defaults = {}
    choices = {h: ws_catalog.Choice(module, h, config) for h in all_hosts}
    for line in marked.entries():
        name = name_of(marked, line)
        default = line.marks.get(ws_marks.ALL, marked.default)
        defaults[name] = default
        for host, state in line.marks.items():
            if host == ws_marks.ALL:
                continue
            if host not in choices:
                raise SystemExit(f"{marked.path}: {name}: unknown host {host}")
            if state == "ask":
                if default != "ask":
                    raise SystemExit(f"{marked.path}: {name}: {host}=ask with all={default}")
                continue
            choices[host].set(name, state)
    for choice in choices.values():
        choice.save()
    return defaults


def check(config, marked, module, defaults, all_hosts):
    """The state of every name on every host, before and after."""
    bad = []
    for host in all_hosts:
        choice = ws_catalog.Choice(module, host, config)
        for line in marked.entries():
            name = name_of(marked, line)
            before = marked.line_state(line, host)
            after = choice.state(name, defaults[name])
            if before != after:
                bad.append(f"{host} {name}: {before} -> {after}")
    return bad


def main(argv):
    if len(argv) not in (3, 5):
        print(__doc__, file=sys.stderr)
        return 64
    config, path, module = Path(argv[0]), argv[1], argv[2]
    fixed = int(argv[4]) if len(argv) == 5 else None
    options = ws_marks.OVERRIDES if fixed else {}
    marked = ws_marks.MarkedList(config / path, **options)
    all_hosts = hosts(config)
    defaults = convert(config, marked, module, all_hosts)
    bad = check(config, marked, module, defaults, all_hosts)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1
    for name, default in defaults.items():
        print(name, default)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
