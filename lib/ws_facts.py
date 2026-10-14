#!/usr/bin/env python3
"""Host and string facts of nix/hosts/HOST/facts.nix, read without Nix
(helpws plan-v2, 2.2): the only reader. bootstrap.sh and setup.sh need the
facts before Nix exists, the checks read them often.

A string fact is a line `NAME = "VALUE";` (the first one). Facts that are
not strings (lists, container) are read by Nix (`nix eval`).

    ws_facts.py host [--for-marks]     WS_HOST, else the host whose facts.nix
                                       has this hostname; --for-marks: also a
                                       name a host file can hold (lib/ws_catalog.py)
    ws_facts.py fact [--host HOST] NAME
                                       the fact of HOST (default: this host)
    ws_facts.py fact --file FACTS NAME a facts.nix outside nix/hosts (setup.sh)

The data root is WS_CONFIG (lib/ws_common.py).
"""
import os
from pathlib import Path
import re
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ws_common  # noqa: E402

PROG = "ws"
# A name that can stand in HOST=STATE; "all" stands for every host.
HOST_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
ALL = "all"


def facts_file(host, config=None):
    return Path(config or ws_common.CONFIG) / "nix/hosts" / host / "facts.nix"


def fact_in(path, name):
    """The string fact NAME of a facts.nix, or None."""
    try:
        text = Path(path).read_text()
    except OSError:
        return None
    m = re.search(rf'^\s*{re.escape(name)} = "([^"]*)";', text, re.M)
    return m[1] if m else None


def fact(host, name, config=None):
    return fact_in(facts_file(host, config), name)


def find_host(config=None):
    """WS_HOST, else the host whose facts.nix has this hostname, else None."""
    if os.environ.get("WS_HOST"):
        return os.environ["WS_HOST"]
    me = socket.gethostname()
    for path in sorted((Path(config or ws_common.CONFIG) / "nix/hosts").glob("*/facts.nix")):
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
        ws_common.die(PROG, f'no nix/hosts/*/facts.nix with hostname = "{socket.gethostname()}"; '
                      "add the host or set WS_HOST")
    if for_marks:
        try:
            check_host(host)
        except ValueError as e:
            ws_common.die(PROG, str(e))
    return host


def main(argv):
    if argv[:1] == ["host"] and argv[1:] in ([], ["--for-marks"]):
        print(host_or_die(argv[1:] == ["--for-marks"]))
        return 0
    if argv[:1] == ["fact"]:
        args = argv[1:]
        if len(args) == 3 and args[0] == "--file":
            path, name = Path(args[1]), args[2]
            where = str(path)
        elif len(args) == 3 and args[0] == "--host":
            path, name = facts_file(args[1]), args[2]
            where = f"nix/hosts/{args[1]}/facts.nix"
        elif len(args) == 1:
            host = host_or_die()
            path, name = facts_file(host), args[0]
            where = f"nix/hosts/{host}/facts.nix"
        else:
            ws_common.die(PROG, "usage: ws fact [--host HOST] NAME")
        if not path.is_file():
            ws_common.die(PROG, f"no {where}")
        value = fact_in(path, name)
        if not value:
            ws_common.die(PROG, f"no string fact {name} in {where}")
        print(value)
        return 0
    ws_common.die(PROG, "usage: ws_facts.py host [--for-marks] | fact [--host HOST|--file FACTS] NAME")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
