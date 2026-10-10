#!/usr/bin/env python3
"""The choices of setup.sh on a workstation (helpws setup): every line of
flatpak/apps.txt, distrobox/hosts.txt and flatpak/overrides.txt without a
mark of this workstation, as checklists (lib/ws_select.py). all=yes and ask
start checked, all=no unchecked; overrides are offered only for the apps
this workstation has. Every line shown gets HOST=yes or HOST=no, so ws apply
asks nothing afterwards; overrides of apps it does not have stay unmarked.
Nothing is written until all three lists are answered.

    setup_marks.py REPO HOST    prints the lists it changed; exit 2 when
                                cancelled (nothing written), 3 without a
                                terminal
"""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ws_marks import OVERRIDES, MarkedList, check_host  # noqa: E402
import ws_select  # noqa: E402

CANCELLED, NO_TERMINAL = 2, 3


def name_of(marked, line):
    """What a line is called in the checklist and found by: APP or box, the
    whole key of an override."""
    return " ".join(line.key) if marked.fixed else line.key[-1]


def offer(marked, host, keep=lambda line: True):
    """[(name, label, checked)] of the lines without a mark of HOST."""
    items = []
    for line in marked.entries():
        if host in line.marks or not keep(line):
            continue
        label = line.key[0] if len(line.key) > 1 and not marked.fixed else ""
        items.append((name_of(marked, line), label, marked.line_state(line, host) != "no"))
    return items


def mark(marked, host, items, chosen):
    for name, _, _ in items:
        key = name.split() if marked.fixed else name
        marked.set(key, host, "yes" if name in chosen else "no")


def ask(term, title, items):
    if not items:
        return []
    term.write(f"\n{title}: {len(items)}\n")
    return ws_select.checklist(term, title, [(n, l) for n, l, _ in items],
                               [c for _, _, c in items])


def run(repo, host, term):
    repo = Path(repo)
    apps = MarkedList(repo / "flatpak/apps.txt", key_fields={1, 2})
    boxes = MarkedList(repo / "distrobox/hosts.txt")
    overrides = MarkedList(repo / "flatpak/overrides.txt", **OVERRIDES)

    for marked, title in ((apps, f"Flatpak-приложения на {host}"),
                          (boxes, f"Контейнеры Distrobox на {host}")):
        items = offer(marked, host)
        chosen = ask(term, title, items)
        if chosen is None:
            return None
        mark(marked, host, items, chosen)

    has = {line.key[-1] for line in apps.entries() if apps.line_state(line, host) == "yes"}
    items = offer(overrides, host, lambda line: line.key[0] in has)
    chosen = ask(term, f"Overrides Flatpak на {host}", items)
    if chosen is None:
        return None
    mark(overrides, host, items, chosen)

    changed = []
    for marked in (apps, boxes, overrides):
        if any(line.changed for line in marked.lines):
            marked.save()
            changed.append(str(marked.path.relative_to(repo)))
    return changed


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: setup_marks.py REPO HOST\n")
        return 64
    host = check_host(argv[2])
    fd = ws_select.open_tty()
    if fd is None:
        sys.stderr.write("setup_marks: no terminal to ask on\n")
        return NO_TERMINAL
    try:
        changed = run(argv[1], host, ws_select.Terminal(fd))
    finally:
        os.close(fd)
    if changed is None:
        sys.stderr.write("setup_marks: cancelled, nothing written\n")
        return CANCELLED
    for path in changed:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
