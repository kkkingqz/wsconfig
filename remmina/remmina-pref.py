#!/usr/bin/env python3
"""Set keys of Remmina's remmina.pref (a GKeyFile) for ws switch:

    remmina-pref.py FILE GROUP.KEY=VALUE...

Only the named keys change; every other line, Remmina's own, stays as it
was. A missing key goes to the end of its group, a missing group to the end
of the file, a missing file is created. The file is written only on a
change, and each change is printed."""
from pathlib import Path
import re
import sys

GROUP = re.compile(r"\[([^\]]+)\]\s*\Z")
KEY = re.compile(r"\s*([^=#;\s\[][^=]*?)\s*=(.*)\Z")


def parse_args(args):
    wanted = []
    for arg in args:
        m = re.fullmatch(r"([^.=\[\]]+)\.([^=\s]+)=(.*)", arg)
        if not m:
            raise SystemExit(f"remmina-pref: not GROUP.KEY=VALUE: {arg!r}")
        wanted.append(m.groups())
    return wanted


def apply(lines, group, key, value):
    """LINES with KEY of GROUP set to VALUE; the change or None."""
    current, end = None, None
    for i, line in enumerate(lines):
        g = GROUP.match(line)
        if g:
            current = g[1]
            continue
        if current != group:
            continue
        if line.strip():
            end = i
        k = KEY.match(line)
        if k and k[1] == key:
            if k[2] == value:
                return None
            lines[i] = f"{key}={value}"
            return f"[{group}] {key}={value} (was {k[2]})"
    if end is None:
        # No such group, or an empty one: the group header is the anchor.
        end = next((i for i, line in enumerate(lines)
                    if (g := GROUP.match(line)) and g[1] == group), None)
    if end is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [f"[{group}]", f"{key}={value}"]
    else:
        lines.insert(end + 1, f"{key}={value}")
    return f"[{group}] {key}={value}"


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    path, wanted = Path(argv[0]), parse_args(argv[1:])
    text = path.read_text() if path.exists() else ""
    lines = text.splitlines()
    changes = [c for c in (apply(lines, *w) for w in wanted) if c]
    if not changes:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(path)
    for change in changes:
        print(f"{path.name}: {change}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
