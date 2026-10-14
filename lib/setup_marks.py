#!/usr/bin/env python3
"""The choices of setup.sh on a host (helpws setup), as checklists
(lib/ws_select.py) before the long part, so ws apply asks nothing
afterwards. Offered: the apps of flatpak/catalog.toml and the containers of
distrobox.nix without a choice of this host, with widgets = "yes" the
widgets some host has in yes (the full widget catalog needs Nix, which
comes later: ws widgets apply offers the rest), and the catalog overrides
of the apps the host gets. Default ask and yes start checked, no
unchecked; the answers go into nix/hosts/HOST/*.toml (lib/ws_catalog.py):
yes or no, an unchecked override a skip of the host. Nothing is written
until all the lists are answered. On a host with nativeSteam = "yes" the
Steam flatpak is no without a question: Steam is the apt one there
(steam/apt.txt).

    setup_marks.py REPO HOST    prints the files it changed; exit 2 when
                                cancelled (nothing written), 3 without a
                                terminal
"""
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flatpak_catalog  # noqa: E402
from ws_facts import check_host, fact  # noqa: E402
import ws_catalog  # noqa: E402
import ws_select  # noqa: E402

CANCELLED, NO_TERMINAL = 2, 3
STEAM_FLATPAK = "com.valvesoftware.Steam"


def unchosen(choice, catalog, label=lambda name: ""):
    """[(name, label, checked)] of CATALOG [(name, default)] without a
    choice of the host; checked unless the default is no."""
    return [(name, label(name), default != "no") for name, default in catalog
            if name not in choice.yes() + choice.no()]


def answer(choice, items, chosen):
    for name, _, _ in items:
        choice.set(name, "yes" if name in chosen else "no")


def box_catalog(repo):
    """[(name, default)] of distrobox/distrobox.nix, read without Nix (setup
    runs before bootstrap installs it): the name = "..." lines of the
    containers and their default = "..." (helpws plan-v2: TOML at stage 7)."""
    boxes = []
    for line in (Path(repo) / "distrobox/distrobox.nix").read_text().splitlines():
        m = re.fullmatch(r'\s*(name|default) = "([^"]+)";', line)
        if m and m[1] == "name":
            boxes.append([m[2], "ask"])
        elif m and boxes:
            boxes[-1][1] = m[2]
    return [tuple(b) for b in boxes]


def ask(term, title, items):
    if not items:
        return []
    term.write(f"\n{title}: {len(items)}\n")
    return ws_select.checklist(term, title, [(n, l) for n, l, _ in items],
                               [c for _, _, c in items])


def run(repo, host, term):
    repo = Path(repo)
    catalog = flatpak_catalog.Catalog(repo)
    apps = ws_catalog.Choice("flatpak", host, repo)
    boxes = ws_catalog.Choice("boxes", host, repo)
    widgets = ws_catalog.Choice("widgets", host, repo)

    if (fact(host, "nativeSteam", repo) == "yes" and catalog.app(STEAM_FLATPAK) is not None
            and STEAM_FLATPAK not in apps.yes() + apps.no()):
        apps.set(STEAM_FLATPAK, "no")
        term.write(f"\n{STEAM_FLATPAK}: no на {host} (nativeSteam = \"yes\": Steam из apt)\n")

    remote = lambda app: catalog.app(app)["remote"]
    lists = [(apps, f"Flatpak-приложения на {host}",
              [(a, catalog.default(a)) for a in catalog.ids()], remote),
             # Containers of distrobox.nix.
             (boxes, f"Контейнеры Distrobox на {host}", box_catalog(repo), lambda n: "")]
    # The widget layer only where facts.nix has it (helpws widgets).
    if fact(host, "widgets", repo) == "yes":
        lists.append((widgets, f"Виджеты (ws widgets) на {host}",
                      [(n, "ask") for n in ws_catalog.used("widgets", repo)], lambda n: ""))
    for choice, title, items, label in lists:
        items = unchosen(choice, items, label)
        chosen = ask(term, title, items)
        if chosen is None:
            return None
        answer(choice, items, chosen)

    # The catalog overrides of the apps this host gets; unchecked: a skip.
    has = [a for a in catalog.ids() if apps.state(a, catalog.default(a)) == "yes"]
    items, keys = [], {}
    for app in has:
        for kind, value in flatpak_catalog.effective(catalog, apps, app):
            if (kind, value) in catalog.values(app):
                name = f"{app} {kind} {value}"
                items.append((name, "", True))
                keys[name] = (app, kind, flatpak_catalog.key_of(kind, value))
    chosen = ask(term, f"Overrides Flatpak на {host}", items)
    if chosen is None:
        return None
    for name, _, _ in items:
        if name not in chosen:
            flatpak_catalog.set_skip(apps, *keys[name], True)

    return [str(c.path.relative_to(repo)) for c in (apps, boxes, widgets) if c.save()]


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
    except KeyboardInterrupt:
        sys.stderr.write("\nsetup_marks: interrupted, nothing written\n")
        return ws_select.INTERRUPTED
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
