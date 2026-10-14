#!/usr/bin/env python3
"""Catalogs and the choice of each host (helpws plan-v2, stage 3).

A module's catalog is all it can install: the Flatpak apps, the containers
of distrobox/catalog.toml, the widgets of the pinned wswidgets. Each position has a
default, what a host without its own choice gets:

    ask  offered (apply asks: "Поставить все? [Y/n]", then a checklist)
    no   not offered (apply --select still asks)
    yes  on every host without its own choice, without a question

The choice of a host is nix/hosts/HOST/MODULE.toml, written only on that
host:

    yes = ["a", "b"]   installed here (widgets: the panel order)
    no = ["c"]         declined here

A name in neither has the catalog default. lib/catalog.nix reads the same
files for Nix. Reading takes tomllib; edits take tomlkit, which keeps the
comments and the order of a file a person edited.

For the bash tools (HOST: ws host --for-marks unless --host):

    ws_catalog.py [--host H] MODULE state NAME [DEFAULT]
    ws_catalog.py [--host H] MODULE states NAME[=DEFAULT]...  NAME STATE per line
    ws_catalog.py [--host H] MODULE set STATE NAME...         ask drops the choice
    ws_catalog.py [--host H] MODULE yes                       in file order
    ws_catalog.py [--host H] MODULE chosen                    names in yes or no
    ws_catalog.py MODULE used                                 names in yes on any host
    ws_catalog.py [--host H] MODULE offer [--select] --what TEXT -- NAME<TAB>DEFAULT<TAB>LABEL...
    ws_catalog.py summary OLD NEW                             changes of a host file (ws sync)
    ws_catalog.py [--host H] offer --all [--select] [MODULE...]  ws apply: every module
    ws_catalog.py [--host H] offer --all --setup              setup.sh: checklists

offer asks about the positions in state ask (with --select also no, those
unchecked), writes the answer (chosen yes, the rest no) and prints the
names it set yes; exit 2 when cancelled (nothing written: the positions
stay ask), 3 without a terminal (it prints the names it would ask about),
130 on Ctrl+C.

offer --all asks about flatpak, boxes and widgets (or the MODULEs) in turn
and prints the files it wrote; a cancel or no terminal leaves a module ask
and goes on (setup, apply_offer). With --setup it asks as setup.sh does,
about everything without a choice of the host: exit 2 when cancelled
(nothing written), 3 without a terminal.
"""
import os
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ws_common  # noqa: E402
import ws_facts  # noqa: E402
import ws_select  # noqa: E402

PROG = "ws_catalog"
STATES = ("yes", "no", "ask")
DEFAULTS = STATES
# MODULE -> the header of a new host file.
MODULES = {
    "flatpak": "Flatpak (ws flatpak)",
    "boxes": "контейнеры Distrobox (ws box)",
    "widgets": "виджеты (ws widgets); порядок yes — порядок кнопок на панели",
}


def hosts_dir(config=None):
    return Path(config or ws_common.CONFIG) / "nix/hosts"


def current_host(config=None):
    host = ws_facts.find_host(config)
    if host is None:
        raise ValueError("unknown workstation (ws host)")
    return ws_facts.check_host(host)


def tomlkit():
    try:
        import tomlkit as module
    except ImportError:
        raise ValueError("python3-tomlkit is missing: sudo apt install python3-tomlkit "
                         "(nix/hosts/apt.txt)") from None
    return module


def names_of(data, key, path):
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{path}: {key} must be a list of names")
    if len(set(value)) != len(value):
        raise ValueError(f"{path}: a name twice in {key}")
    return list(value)


class Choice:
    """The choice of HOST for MODULE: nix/hosts/HOST/MODULE.toml."""

    def __init__(self, module, host=None, config=None):
        if module not in MODULES:
            raise ValueError(f"unknown module {module!r} ({', '.join(MODULES)})")
        self.module = module
        self.host = ws_facts.check_host(host) if host else current_host(config)
        self.path = hosts_dir(config) / self.host / f"{module}.toml"
        self.text = self.path.read_text() if self.path.exists() else None
        self.data = self.parse(self.text or "", self.path)
        self.doc = None

    @staticmethod
    def parse(text, path):
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{path}: {e}") from None
        both = set(names_of(data, "yes", path)) & set(names_of(data, "no", path))
        if both:
            raise ValueError(f"{path}: in both yes and no: {', '.join(sorted(both))}")
        return data

    def yes(self):
        return list(self.data.get("yes", []))

    def no(self):
        return list(self.data.get("no", []))

    def state(self, name, default="ask"):
        if default not in DEFAULTS:
            raise ValueError(f"invalid default {default!r} of {name} (ask|no|yes)")
        if name in self.data.get("yes", []):
            return "yes"
        if name in self.data.get("no", []):
            return "no"
        return default

    def edit(self):
        """The tomlkit document, read on the first edit."""
        if self.doc is None:
            kit = tomlkit()
            if self.text is None:
                self.doc = kit.document()
                self.doc.add(kit.comment(f"{self.host}: {MODULES[self.module]}."))
                self.doc.add(kit.comment("yes — есть здесь, no — отказались; чего нет ни там, ни там, — default каталога."))
            else:
                self.doc = kit.parse(self.text)
        return self.doc

    def set(self, name, state):
        """STATE yes or no puts NAME in that list (yes at the end), ask
        drops it from both. True when the file changes."""
        if state not in STATES:
            raise ValueError(f"invalid state {state!r} (yes|no|ask)")
        if self.state(name, "ask") == state:
            return False
        doc = self.edit()
        for key in ("yes", "no"):
            if key not in doc:
                doc[key] = tomlkit().array()
            if name in doc[key]:
                doc[key].remove(name)
        if state != "ask":
            doc[state].append(name)
            if len(doc[state]) > 3:
                doc[state].multiline(True)
        self.data = self.parse(tomlkit().dumps(doc), self.path)
        return True

    def save(self):
        """Writes the edits; True when the file changed."""
        if self.doc is None:
            return False
        text = tomlkit().dumps(self.doc)
        if text == self.text:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(text)
        tmp.replace(self.path)
        self.text = text
        return True


def used(module, config=None):
    """The names in yes on any host, each once, by host name."""
    names = []
    for path in sorted(hosts_dir(config).glob(f"*/{module}.toml")):
        for name in Choice(module, path.parent.name, config).yes():
            if name not in names:
                names.append(name)
    return names


def offer(choice, items, select=False, what="", tty=None):
    """items: [(name, default, label)] of the catalog. Asks about those in
    state ask (with SELECT also no, unchecked), writes the answer and
    returns the names it set yes; [] with nothing to ask. None when
    cancelled (nothing written); raises ws_select.NoTerminal."""
    offered, unchecked = [], []
    for name, default, label in items:
        state = choice.state(name, default)
        if state == "ask" or (state == "no" and select):
            offered.append((name, label))
            if state == "no":
                unchecked.append(name)
    if not offered:
        return []
    chosen = ws_select.choose(offered, what, unchecked, tty)
    if chosen is None:
        return None
    for name, _ in offered:
        choice.set(name, "yes" if name in chosen else "no")
    choice.save()
    return [name for name, _ in offered if name in chosen]


def summary(old_text, new_text):
    """What changed between two versions of a host file, for the commit
    message of ws sync: NAME=yes, NAME=no, -NAME (back to the default)."""
    old = Choice.parse(old_text, "old")
    new = Choice.parse(new_text, "new")
    def states(data):
        return {**{n: "yes" for n in data.get("yes", [])}, **{n: "no" for n in data.get("no", [])}}
    before, after = states(old), states(new)
    out = [f"{n}={s}" for n, s in after.items() if before.get(n) != s]
    out += [f"-{n}" for n in before if n not in after]
    # Flatpak: [overrides."APP"] of the host.
    old_over, new_over = old.get("overrides", {}), new.get("overrides", {})
    out += [f"overrides {a}" for a in sorted(set(old_over) | set(new_over))
            if old_over.get(a) != new_over.get(a)]
    if not out and old_text != new_text:
        out.append("edited")
    return ", ".join(out)


# All the modules at once: setup.sh before the long part (--setup) and the
# start of ws apply.
STEAM_FLATPAK = "com.valvesoftware.Steam"
CANCELLED, NO_TERMINAL = ws_select.CANCELLED, ws_select.NO_TERMINAL


def box_catalog(config=None):
    """[(name, default)] of the containers: boxes.json of the build
    (distrobox/catalog.toml through ws apply), else distrobox/catalog.toml
    itself (setup runs before bootstrap installs Nix)."""
    built = ws_common.load(Path(os.environ.get("WSBOX_CONFIG") or
                                Path.home() / ".local/share/wsconfig/distrobox") / "boxes.json")
    if isinstance(built, list) and config is None:
        return [(b["name"], b.get("default", "ask")) for b in built]
    path = Path(config or ws_common.CONFIG) / "distrobox/catalog.toml"
    try:
        boxes = tomllib.loads(path.read_text()).get("boxes", [])
    except OSError:
        return []
    return [(b["name"], b.get("default", "ask")) for b in boxes if isinstance(b, dict) and "name" in b]


def widget_catalog(config=None):
    """[(id, label)] of the pinned wswidgets as ws apply built it, else
    the widgets some host has in yes (the full catalog needs Nix)."""
    built = ws_common.load(Path.home() / ".local/share/workstation/widgets/catalog.json")
    if isinstance(built, list) and config is None:
        return [(w["id"], w.get("label", "")) for w in built]
    return [(name, "") for name in used("widgets", config)]


def checklist(term, title, items):
    """items: [(name, label, checked)]; the checked names, None when
    cancelled."""
    if not items:
        return []
    term.write(f"\n{title}: {len(items)}\n")
    return ws_select.checklist(term, title, [(n, l) for n, l, _ in items],
                               [c for _, _, c in items])


def setup(config, host, term):
    """The choices of setup.sh (helpws setup), as checklists, so ws apply
    asks nothing afterwards: the apps of flatpak/catalog.toml and the
    containers of distrobox/catalog.toml without a choice of this host, with
    widgets = true the widgets some host has in yes (ws widgets apply
    offers the rest later), and the catalog overrides of the apps the host
    gets. Default ask and yes start checked, no unchecked; an unchecked
    override becomes a skip of the host. Nothing is written until all the
    lists are answered (None: cancelled). With nativeSteam = true the
    Steam flatpak is no without a question: Steam is the apt one there.
    Returns the files written."""
    import flatpak_catalog
    config = Path(config)
    catalog = flatpak_catalog.Catalog(config)
    apps = Choice("flatpak", host, config)
    boxes = Choice("boxes", host, config)
    widgets = Choice("widgets", host, config)

    if (ws_facts.fact(host, "nativeSteam", config) == "yes" and catalog.app(STEAM_FLATPAK) is not None
            and STEAM_FLATPAK not in apps.yes() + apps.no()):
        apps.set(STEAM_FLATPAK, "no")
        term.write(f"\n{STEAM_FLATPAK}: no на {host} (nativeSteam = true: Steam из apt)\n")

    remote = lambda app: catalog.app(app)["remote"]
    lists = [(apps, f"Flatpak-приложения на {host}",
              [(a, catalog.default(a)) for a in catalog.ids()], remote),
             (boxes, f"Контейнеры Distrobox на {host}", box_catalog(config), lambda n: "")]
    # The widget layer only where host.toml has it (helpws widgets).
    if ws_facts.fact(host, "widgets", config) == "yes":
        lists.append((widgets, f"Виджеты (ws widgets) на {host}",
                      [(n, "ask") for n, _ in widget_catalog(config)], lambda n: ""))
    for choice, title, positions, label in lists:
        items = [(name, label(name), default != "no") for name, default in positions
                 if name not in choice.yes() + choice.no()]
        chosen = checklist(term, title, items)
        if chosen is None:
            return None
        for name, _, _ in items:
            choice.set(name, "yes" if name in chosen else "no")

    # The catalog overrides of the apps this host gets; unchecked: a skip.
    items, keys = [], {}
    for app in catalog.ids():
        if apps.state(app, catalog.default(app)) != "yes":
            continue
        for kind, value in flatpak_catalog.effective(catalog, apps, app):
            if (kind, value) in catalog.values(app):
                name = f"{app} {kind} {value}"
                items.append((name, "", True))
                keys[name] = (app, kind, flatpak_catalog.key_of(kind, value))
    chosen = checklist(term, f"Overrides Flatpak на {host}", items)
    if chosen is None:
        return None
    for name, _, _ in items:
        if name not in chosen:
            flatpak_catalog.set_skip(apps, *keys[name], True)

    return [str(c.path.relative_to(config)) for c in (apps, boxes, widgets) if c.save()]


def apply_offer(host, modules, select=False, tty=None, err=sys.stderr):
    """The start of ws apply: for each of MODULES (flatpak, boxes, widgets)
    the positions in state ask (with SELECT also no), as each module's
    apply asks: "Поставить все? [Y/n]", then a checklist. A cancel or a
    missing terminal leaves that module's positions ask and goes on.
    Returns the files written."""
    import flatpak_catalog
    written = []
    for module in modules:
        choice = Choice(module, host)
        if module == "flatpak":
            catalog = flatpak_catalog.Catalog()
            items = [(a, catalog.default(a), catalog.app(a)["remote"]) for a in catalog.ids()]
            what = "приложения Flatpak"
        elif module == "boxes":
            items = [(n, d, "") for n, d in box_catalog()]
            what = "контейнеры Distrobox"
        elif module == "widgets":
            if ws_facts.fact(host, "widgets") != "yes":
                continue
            items = [(n, "ask", label) for n, label in widget_catalog()]
            what = "виджеты wswidgets"
        else:
            raise ValueError(f"unknown module {module!r}")
        before = choice.text
        try:
            chosen = offer(choice, items, select, what, tty)
        except ws_select.NoTerminal:
            names = [n for n, d, _ in items if choice.state(n, d) == "ask"]
            err.write(f"Not offered on {host} yet (no terminal to ask): {' '.join(names)}; "
                      "run ws apply in a terminal\n")
            continue
        if chosen is None:
            err.write(f"ws apply: выбор отменён, {what} не тронуты (спросит в следующий раз)\n")
            continue
        if choice.text != before:
            written.append(str(choice.path))
    return written


def cli_offer_all(host, args):
    setup_mode = "--setup" in args
    select = "--select" in args
    modules = [a for a in args if not a.startswith("--")] or ["flatpak", "boxes", "widgets"]
    host = ws_facts.check_host(host) if host else current_host()
    if not setup_mode:
        for path in apply_offer(host, modules, select):
            print(path)
        return 0
    fd = ws_select.open_tty()
    if fd is None:
        sys.stderr.write(f"{PROG}: no terminal to ask on\n")
        return NO_TERMINAL
    try:
        changed = setup(ws_common.CONFIG, host, ws_select.Terminal(fd))
    except KeyboardInterrupt:
        sys.stderr.write(f"\n{PROG}: interrupted, nothing written\n")
        return ws_select.INTERRUPTED
    finally:
        os.close(fd)
    if changed is None:
        sys.stderr.write(f"{PROG}: cancelled, nothing written\n")
        return CANCELLED
    for path in changed:
        print(path)
    return 0


def main(argv):
    host = None
    if argv[:1] == ["--host"] and len(argv) >= 2:
        host, argv = argv[1], argv[2:]
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 64
    try:
        if argv[:2] == ["offer", "--all"]:
            return cli_offer_all(host, argv[2:])
        if argv[0] == "summary" and len(argv) == 3:
            read = lambda p: Path(p).read_text() if Path(p).exists() else ""
            print(summary(read(argv[1]), read(argv[2])))
            return 0
        module, action, args = argv[0], argv[1], argv[2:]
        if action == "used" and not args:
            for name in used(module):
                print(name)
            return 0
        choice = Choice(module, host)
        if action == "state" and len(args) in (1, 2):
            print(choice.state(*args))
        elif action == "states":
            for arg in args:
                name, _, default = arg.partition("=")
                print(name, choice.state(name, default or "ask"))
        elif action == "set" and len(args) >= 2:
            for name in args[1:]:
                choice.set(name, args[0])
            choice.save()
        elif action in ("yes", "chosen") and not args:
            for name in choice.yes() + (choice.no() if action == "chosen" else []):
                print(name)
        elif action == "offer":
            return cli_offer(choice, args)
        else:
            print(__doc__, file=sys.stderr)
            return 64
    except ValueError as e:
        print(f"{PROG}: {e}", file=sys.stderr)
        return 1
    return 0


def cli_offer(choice, args):
    select, what = False, ""
    while args and args[0] != "--":
        if args[0] == "--select":
            select, args = True, args[1:]
        elif args[0] == "--what" and len(args) >= 2:
            what, args = args[1], args[2:]
        else:
            print(__doc__, file=sys.stderr)
            return 64
    items = []
    for row in args[1:]:
        name, default, label = (row.split("\t", 2) + ["", ""])[:3]
        items.append((name, default or "ask", label))
    try:
        chosen = offer(choice, items, select, what)
    except ws_select.NoTerminal:
        # The names that would be asked about, for the caller's message.
        for name, default, _ in items:
            state = choice.state(name, default)
            if state == "ask" or (state == "no" and select):
                print(name)
        return ws_select.NO_TERMINAL
    except KeyboardInterrupt:
        sys.stderr.write("\n")
        return ws_select.INTERRUPTED
    if chosen is None:
        return ws_select.CANCELLED
    for name in chosen:
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
