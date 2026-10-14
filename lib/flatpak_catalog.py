#!/usr/bin/env python3
"""The Flatpak catalog and the overrides of a host (helpws flatpak; helpws
plan-v2, 3.4).

flatpak/catalog.toml is every app a host may have, in order:

    [remotes]
    flathub = "https://dl.flathub.org/repo/flathub.flatpakrepo"

    [[apps]]
    # comments of an app go inside its table (they go with it)
    id = "com.anydesk.Anydesk"
    remote = "flathub"
    default = "ask"                        # ask (the default), no or yes
    filesystems = ["home:ro"]              # Context.filesystems
    env = { GDK_SCALE = "2" }              # Environment
    talk = ["org.kde.StatusNotifierWatcher"]   # Session Bus Policy, talk

The overrides of an app in the catalog apply on every host that has it.
nix/hosts/HOST/flatpak.toml holds the choice of the host (yes, no;
lib/ws_catalog.py) and its own overrides on top:

    [overrides."com.anydesk.Anydesk"]
    env = { GDK_SCALE = "1" }              # replaces the catalog value
    skip = ["talk org.kde.StatusNotifierWatcher"]   # not on this host

One value per key on a host: the env name, the filesystem path whatever
its mode (:ro, :rw, :create), the bus name. A value of the host replaces a
catalog value of the same key; skip names catalog values as KIND KEY.
flatpak/flatpak.nix builds the same set (lib/catalog.nix overridesOf).

For the fish completions and ws sync:

    flatpak_catalog.py apps                 ids of the catalog
    flatpak_catalog.py override-apps        apps with overrides (catalog, any host)
    flatpak_catalog.py values APP KIND      APP's values of KIND (env: the names)
    flatpak_catalog.py summary OLD NEW      changes of catalog.toml
"""
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ws_catalog  # noqa: E402
import ws_common  # noqa: E402

KINDS = ("filesystem", "env", "talk")
FIELD = {"filesystem": "filesystems", "env": "env", "talk": "talk"}
APP_KEYS = {"id", "remote", "default", "filesystems", "env", "talk"}
HOST_KEYS = {"filesystems", "env", "talk", "skip"}
MODES = (":ro", ":rw", ":create")


def key_of(kind, value):
    """The key of a value: env NAME of NAME=VALUE, the path of a filesystem
    without its mode, the bus name."""
    if kind == "env":
        return value.split("=", 1)[0]
    if kind == "filesystem":
        for mode in MODES:
            if value.endswith(mode):
                return value[:-len(mode)]
    return value


def values_of(entry):
    """[(KIND, VALUE)] of a catalog entry or a host section; env values as
    NAME=VALUE."""
    out = [("filesystem", v) for v in entry.get("filesystems", [])]
    out += [("env", f"{k}={v}") for k, v in entry.get("env", {}).items()]
    out += [("talk", v) for v in entry.get("talk", [])]
    return out


def check_values(entry, where):
    for field, kind in (("filesystems", "filesystem"), ("talk", "talk")):
        value = entry.get(field, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            raise ValueError(f"{where}: {field} must be a list of strings")
    env = entry.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
        raise ValueError(f"{where}: env must be a table of strings")
    for kind, value in values_of(entry):
        if not value or any(c.isspace() or c == "#" for c in value):
            raise ValueError(f"{where}: {kind} value must be one word without #: {value!r}")
    keys = [(kind, key_of(kind, value)) for kind, value in values_of(entry)]
    for k in keys:
        if keys.count(k) > 1:
            raise ValueError(f"{where}: two values of {k[0]} {k[1]}")


class Catalog:
    """flatpak/catalog.toml of CONFIG."""

    def __init__(self, config=None):
        self.path = Path(config or ws_common.CONFIG) / "flatpak/catalog.toml"
        try:
            self.text = self.path.read_text()
        except FileNotFoundError:
            raise ValueError(f"{self.path} is missing") from None
        self.data = self.parse(self.text, self.path)
        self.doc = None

    @staticmethod
    def parse(text, path):
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{path}: {e}") from None
        remotes = data.get("remotes", {})
        if not isinstance(remotes, dict) or not all(isinstance(v, str) for v in remotes.values()):
            raise ValueError(f"{path}: remotes must be a table of URLs")
        apps = data.get("apps", [])
        if not isinstance(apps, list):
            raise ValueError(f"{path}: apps must be [[apps]] tables")
        seen = set()
        for entry in apps:
            app = entry.get("id")
            if not isinstance(app, str) or not app:
                raise ValueError(f"{path}: an app without id")
            where = f"{path}: {app}"
            if app in seen:
                raise ValueError(f"{where}: twice in the catalog")
            seen.add(app)
            unknown = set(entry) - APP_KEYS
            if unknown:
                raise ValueError(f"{where}: unknown keys {', '.join(sorted(unknown))}")
            if entry.get("remote") not in remotes:
                raise ValueError(f"{where}: remote {entry.get('remote')!r} is not in [remotes]")
            if entry.get("default", "ask") not in ws_catalog.DEFAULTS:
                raise ValueError(f"{where}: default is ask, no or yes")
            check_values(entry, where)
        return data

    def remotes(self):
        return dict(self.data.get("remotes", {}))

    def apps(self):
        return list(self.data.get("apps", []))

    def ids(self):
        return [e["id"] for e in self.apps()]

    def app(self, app):
        return next((e for e in self.apps() if e["id"] == app), None)

    def default(self, app):
        entry = self.app(app)
        return entry.get("default", "ask") if entry else "ask"

    def values(self, app):
        entry = self.app(app)
        return values_of(entry) if entry else []

    # Edits: tomlkit, comments and order kept.
    def edit(self):
        if self.doc is None:
            self.doc = ws_catalog.tomlkit().parse(self.text)
        return self.doc

    def table(self, app):
        for entry in self.edit().get("apps", []):
            if entry["id"] == app:
                return entry
        raise ValueError(f"{app} is not in {self.path}")

    def reparse(self):
        self.data = self.parse(ws_catalog.tomlkit().dumps(self.doc), self.path)

    def add_app(self, app, remote):
        """A new [[apps]] entry at the end; False when APP is there."""
        if self.app(app) is not None:
            return False
        kit = ws_catalog.tomlkit()
        doc = self.edit()
        entry = kit.table()
        entry["id"] = app
        entry["remote"] = remote
        entry.trivia.indent = "\n"
        if "apps" not in doc:
            doc["apps"] = kit.aot()
        doc["apps"].append(entry)
        self.reparse()
        return True

    def remove_app(self, app):
        doc = self.edit()
        for i, entry in enumerate(doc.get("apps", [])):
            if entry["id"] == app:
                del doc["apps"][i]
                self.reparse()
                return True
        return False

    def set_value(self, app, kind, value):
        """VALUE for APP; one of the same key is replaced. Returns
        'same', 'replaced' or 'added'."""
        result = set_in(self.table(app), kind, value)
        self.reparse()
        return result

    def remove_key(self, app, kind, key):
        result = remove_in(self.table(app), kind, key)
        self.reparse()
        return result

    def save(self):
        if self.doc is None:
            return False
        text = ws_catalog.tomlkit().dumps(self.doc)
        if text == self.text:
            return False
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(text)
        tmp.replace(self.path)
        self.text = text
        return True


def set_in(table, kind, value):
    """VALUE of KIND in a tomlkit TABLE (catalog entry, host section), in
    place of a value of the same key."""
    kit = ws_catalog.tomlkit()
    key = key_of(kind, value)
    if kind == "env":
        name, _, val = value.partition("=")
        if "env" not in table:
            table["env"] = kit.inline_table()
        old = table["env"].get(name)
        if old == val:
            return "same"
        table["env"][name] = val
        return "added" if old is None else "replaced"
    field = FIELD[kind]
    if field not in table:
        table[field] = kit.array()
    items = table[field]
    for i, old in enumerate(list(items)):
        if key_of(kind, old) == key:
            if old == value:
                return "same"
            items[i] = value
            return "replaced"
    items.append(value)
    return "added"


def remove_in(table, kind, key):
    """Drop the value of KEY from a tomlkit TABLE; False when it has none.
    An empty field goes too."""
    field = FIELD[kind]
    if field not in table:
        return False
    if kind == "env":
        if key not in table["env"]:
            return False
        del table["env"][key]
    else:
        items = table[field]
        match = [v for v in items if key_of(kind, v) == key]
        if not match:
            return False
        for v in match:
            items.remove(v)
    if not len(table[field]):
        del table[field]
    return True


# The overrides of a host: [overrides."APP"] of nix/hosts/HOST/flatpak.toml.
def host_section(choice, app):
    return choice.data.get("overrides", {}).get(app, {})


def check_host(choice, catalog):
    """The overrides of CHOICE: tables of known keys, for catalog apps;
    skip names a catalog value."""
    overrides = choice.data.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError(f"{choice.path}: overrides must be [overrides.\"APP\"] tables")
    for app, section in overrides.items():
        where = f"{choice.path}: overrides of {app}"
        if catalog.app(app) is None:
            raise ValueError(f"{where}: not in {catalog.path}")
        unknown = set(section) - HOST_KEYS
        if unknown:
            raise ValueError(f"{where}: unknown keys {', '.join(sorted(unknown))}")
        check_values(section, where)
        skip = section.get("skip", [])
        if not isinstance(skip, list) or not all(isinstance(s, str) for s in skip):
            raise ValueError(f"{where}: skip must be a list of \"KIND KEY\"")
        common = {f"{k} {key_of(k, v)}" for k, v in catalog.values(app)}
        for s in skip:
            if s not in common:
                raise ValueError(f"{where}: skip {s!r} is no catalog value (KIND KEY: {', '.join(sorted(common)) or 'none'})")


def effective(catalog, choice, app):
    """[(KIND, VALUE)] of APP on the host of CHOICE: the catalog values
    without the skipped and those the host replaces, then the host's."""
    section = host_section(choice, app)
    own = values_of(section)
    drop = set(section.get("skip", [])) | {f"{k} {key_of(k, v)}" for k, v in own}
    common = [(k, v) for k, v in catalog.values(app) if f"{k} {key_of(k, v)}" not in drop]
    return common + own


def manifest_overrides(catalog, choice):
    """The overrides of flatpak.json on that host (flatpak/flatpak.nix): APP
    -> filesystems, environment, session_bus, for the apps with any."""
    out = {}
    for app in catalog.ids():
        values = effective(catalog, choice, app)
        if not values:
            continue
        out[app] = {
            "filesystems": [v for k, v in values if k == "filesystem"],
            "environment": dict(v.split("=", 1) for k, v in values if k == "env"),
            "session_bus": {v: "talk" for k, v in values if k == "talk"},
        }
    return out


def edit_host(choice, app):
    """The tomlkit table [overrides."APP"] of CHOICE, made when missing."""
    kit = ws_catalog.tomlkit()
    doc = choice.edit()
    if "overrides" not in doc:
        doc["overrides"] = kit.table(is_super_table=True)
    if app not in doc["overrides"]:
        table = kit.table()
        table.trivia.indent = "\n"
        doc["overrides"][app] = table
    return doc["overrides"][app]


def tidy_host(choice, app):
    """Drop an empty [overrides."APP"] (and an empty [overrides])."""
    doc = choice.edit()
    overrides = doc.get("overrides")
    if overrides is not None and app in overrides and not len(overrides[app]):
        del overrides[app]
    if overrides is not None and not len(overrides):
        del doc["overrides"]
    choice.data = choice.parse(ws_catalog.tomlkit().dumps(doc), choice.path)


def set_skip(choice, app, kind, key, skipped):
    table = edit_host(choice, app)
    item = f"{kind} {key}"
    kit = ws_catalog.tomlkit()
    if skipped:
        if "skip" not in table:
            table["skip"] = kit.array()
        if item not in table["skip"]:
            table["skip"].append(item)
    elif "skip" in table and item in table["skip"]:
        table["skip"].remove(item)
        if not len(table["skip"]):
            del table["skip"]
    tidy_host(choice, app)


def set_host_value(choice, app, kind, value):
    result = set_in(edit_host(choice, app), kind, value)
    tidy_host(choice, app)
    return result


def remove_host_key(choice, app, kind, key):
    result = remove_in(edit_host(choice, app), kind, key)
    tidy_host(choice, app)
    return result


def summary(old_text, new_text):
    """What changed in catalog.toml, for the commit message of ws sync:
    +APP, -APP, APP (the fields that changed), remotes."""
    old = Catalog.parse(old_text, "old") if old_text else {}
    new = Catalog.parse(new_text, "new")
    before = {e["id"]: e for e in old.get("apps", [])}
    after = {e["id"]: e for e in new.get("apps", [])}
    out = [f"+{a}" for a in after if a not in before]
    for a, e in after.items():
        if a in before and e != before[a]:
            fields = sorted(k for k in set(e) | set(before[a]) if e.get(k) != before[a].get(k))
            out.append(f"{a} ({', '.join(fields)})")
    out += [f"-{a}" for a in before if a not in after]
    if old.get("remotes") != new.get("remotes"):
        out.append("remotes")
    if not out and old_text != new_text:
        out.append("edited")
    return ", ".join(out)


def main(argv):
    try:
        if argv == ["apps"]:
            print("\n".join(Catalog().ids()))
        elif argv == ["override-apps"]:
            catalog = Catalog()
            apps = [a for a in catalog.ids() if catalog.values(a)]
            for path in sorted(ws_catalog.hosts_dir().glob("*/flatpak.toml")):
                data = tomllib.loads(path.read_text())
                apps += [a for a in data.get("overrides", {}) if a not in apps]
            print("\n".join(apps))
        elif len(argv) == 3 and argv[0] == "values" and argv[2] in KINDS:
            catalog = Catalog()
            shown = lambda k, v: key_of(k, v) if k == "env" else v
            keys = [shown(k, v) for k, v in catalog.values(argv[1]) if k == argv[2]]
            for path in sorted(ws_catalog.hosts_dir().glob("*/flatpak.toml")):
                section = tomllib.loads(path.read_text()).get("overrides", {}).get(argv[1], {})
                keys += [shown(k, v) for k, v in values_of(section) if k == argv[2]]
            print("\n".join(dict.fromkeys(keys)))
        elif len(argv) == 3 and argv[0] == "summary":
            read = lambda p: Path(p).read_text() if Path(p).exists() else ""
            print(summary(read(argv[1]), read(argv[2])))
        else:
            print(__doc__, file=sys.stderr)
            return 64
    except (ValueError, tomllib.TOMLDecodeError) as e:
        print(f"flatpak_catalog: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
