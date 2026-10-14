#!/usr/bin/env python3
"""Host and facts of nix/hosts/HOST/host.toml, read without Nix (ws help
plan-v2, 2.2 and 4): the only reader. bootstrap.sh and setup.sh need the
facts before Nix exists, the checks read them often. Only Nix checks the
values (lib/host.nix); this reads what is there.

A fact is a key of [host], [platform] or [layers]. A string or number is
printed as written, true and false as yes and no (the bash checks compare
with yes). Lists are not facts here, Nix reads them; [container] is
printed as JSON by `section`.

    ws_facts.py host [--for-marks]     WS_HOST, else the host whose host.toml
                                       has this hostname; --for-marks: also a
                                       name a host file can hold (lib/ws_catalog.py)
    ws_facts.py fact [--host HOST] NAME
                                       the fact of HOST (default: this host)
    ws_facts.py fact --file HOST_TOML NAME
                                       a host.toml outside nix/hosts (setup.sh)
    ws_facts.py section [--host HOST] NAME
                                       a section of host.toml as JSON (ws-container)
    ws_facts.py record                 write host.json in the state: this host
                                       and the data root (ws apply, setup.sh)

The data root is WS_CONFIG (lib/ws_common.py). host.json names the host
only for the data root it records.
"""
import json
import os
from pathlib import Path
import re
import socket
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ws_common  # noqa: E402

PROG = "ws"
# A name that can stand in HOST=STATE; "all" stands for every host.
HOST_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
ALL = "all"
# The sections whose keys are facts.
FACT_SECTIONS = ("host", "platform", "layers")


def facts_file(host, config=None):
    return Path(config or ws_common.CONFIG) / "nix/hosts" / host / "host.toml"


def load(path):
    """The parsed host.toml at PATH; None when it cannot be read. A file
    that is no TOML is an error: nothing about the host can be known."""
    try:
        text = Path(path).read_text()
    except OSError:
        return None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        ws_common.die(PROG, f"{path}: {e}")


def value_text(value):
    """VALUE as a fact prints, None for a list or a table."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def fact_in(path, name):
    """The fact NAME of a host.toml as text, or None."""
    data = load(path) or {}
    for section in FACT_SECTIONS:
        table = data.get(section)
        if isinstance(table, dict) and name in table:
            return value_text(table[name])
    return None


def fact(host, name, config=None):
    return fact_in(facts_file(host, config), name)


def find_host(config=None, record=True):
    """WS_HOST, else the host of host.json when it records this data root,
    else the host whose host.toml has this hostname, else None."""
    if os.environ.get("WS_HOST"):
        return os.environ["WS_HOST"]
    root = Path(config or ws_common.CONFIG)
    if record:
        rec = ws_common.host_record()
        host = rec.get("host")
        if (rec.get("config") == str(root) and isinstance(host, str) and HOST_NAME.match(host)
                and facts_file(host, root).is_file()):
            return host
    me = socket.gethostname()
    for path in sorted((root / "nix/hosts").glob("*/host.toml")):
        if fact_in(path, "hostname") == me:
            return path.parent.name
    return None


def check_host(host):
    """HOST as it can stand in a mark; ValueError otherwise."""
    if host == ALL or not HOST_NAME.match(host):
        raise ValueError(f"invalid workstation name {host!r} for a mark "
                         "(letters, digits, - and _; not all)")
    return host


def host_or_die(for_marks=False):
    host = find_host()
    if host is None:
        ws_common.die(PROG, f'no nix/hosts/*/host.toml with hostname = "{socket.gethostname()}"; '
                      "add the host or set WS_HOST")
    if for_marks:
        try:
            check_host(host)
        except ValueError as e:
            ws_common.die(PROG, str(e))
    return host


def record():
    """host.json: this host and the data root; written only when it
    changes. The host is found as without the record (hostname, WS_HOST):
    an old record does not keep itself."""
    host = find_host(record=False) or host_or_die()
    data = {"host": host, "config": str(ws_common.CONFIG)}
    if ws_common.host_record() == data:
        return
    path = ws_common.state_dir() / ws_common.HOST_RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)
    print(f"{PROG}: {path}: host {host}, configuration {data['config']}", file=sys.stderr)


def main(argv):
    if argv == ["record"]:
        record()
        return 0
    if argv[:1] == ["host"] and argv[1:] in ([], ["--for-marks"]):
        print(host_or_die(argv[1:] == ["--for-marks"]))
        return 0
    if argv[:1] in (["fact"], ["section"]):
        command, args = argv[0], argv[1:]
        if command == "fact" and len(args) == 3 and args[0] == "--file":
            path, name = Path(args[1]), args[2]
            where = str(path)
        elif len(args) == 3 and args[0] == "--host":
            path, name = facts_file(args[1]), args[2]
            where = f"nix/hosts/{args[1]}/host.toml"
        elif len(args) == 1:
            host = host_or_die()
            path, name = facts_file(host), args[0]
            where = f"nix/hosts/{host}/host.toml"
        else:
            ws_common.die(PROG, f"usage: ws {command} [--host HOST] NAME")
        if not path.is_file():
            ws_common.die(PROG, f"no {where}")
        if command == "section":
            table = (load(path) or {}).get(name)
            if not isinstance(table, dict):
                ws_common.die(PROG, f"no section [{name}] in {where}")
            print(json.dumps(table))
            return 0
        value = fact_in(path, name)
        if not value:
            ws_common.die(PROG, f"no fact {name} in {where} (lists are read by Nix)")
        print(value)
        return 0
    ws_common.die(PROG, "usage: ws_facts.py host [--for-marks] | fact [--host HOST|--file HOST_TOML] NAME"
                  " | section [--host HOST] NAME | record")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
