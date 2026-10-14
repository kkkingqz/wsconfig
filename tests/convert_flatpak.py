#!/usr/bin/env python3
"""One-off converter of flatpak/apps.txt, flatpak/overrides.txt and the
remotes of flatpak/flatpak.nix into flatpak/catalog.toml and the host
choices nix/hosts/HOST/flatpak.toml (helpws plan-v2, 3.4). Goes with
ws_marks.py in 3.5.

    convert_flatpak.py CONFIG

The comments before a line move into the table of its app. An override
must apply on every host (all of them are mbp16=yes all=yes, 2026-10-14):
then it is a catalog value; anything else stops the conversion.
"""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

import convert_marks  # noqa: E402
import flatpak_catalog  # noqa: E402
import ws_marks  # noqa: E402

HEADER = """\
# Flatpak: the remotes and every app a host may have (helpws flatpak), in
# order. Which host has which app, and its own overrides:
# nix/hosts/HOST/flatpak.toml. An app without a choice of the host has its
# default: ask (offered by ws flatpak apply; the default), no or yes.
# filesystems, env and talk of an app apply on every host that has it.
# ws flatpak install|manage|unmanage and filesystem|env|talk edit this file
# (lib/flatpak_catalog.py), ws switch builds it, ws sync publishes it.
"""


def remotes(config):
    text = (Path(config) / "flatpak/flatpak.nix").read_text()
    block = re.search(r"remotes = \{(.*?)\};", text, re.S)[1]
    return re.findall(r'(\w+) = "([^"]+)";', block)


def comments(path):
    """KEY -> the comment lines right before the line of KEY (APP of
    apps.txt, the whole key of overrides.txt), without the file header
    (before the first blank line)."""
    out, pending, header = {}, [], True
    for raw in Path(path).read_text().splitlines():
        if not raw.strip():
            pending, header = [], False
            continue
        if raw.lstrip().startswith("#"):
            if not header:
                pending.append(raw.strip())
            continue
        header = False
        out[tuple(ws_marks.Line(raw).key if "overrides" not in str(path) else ws_marks.Line(raw, fixed=3).key)] = pending
        pending = []
    return out


def toml_string(s):
    return json.dumps(s, ensure_ascii=False)


def catalog_text(config, apps, overrides, all_hosts):
    app_comments = comments(Path(config) / "flatpak/apps.txt")
    over_comments = comments(Path(config) / "flatpak/overrides.txt")
    values = {}
    for line in overrides.entries():
        app, kind, value = line.key
        for host in all_hosts:
            if overrides.line_state(line, host) != "yes":
                raise SystemExit(f"overrides.txt: {' '.join(line.key)} not yes on {host}: needs a host section")
        values.setdefault(app, []).append((kind, value, over_comments.get(tuple(line.key), [])))
    out = [HEADER, "[remotes]"]
    out += [f"{name} = {toml_string(url)}" for name, url in remotes(config)]
    for line in apps.entries():
        remote, app = line.key
        out.append("")
        out.append("[[apps]]")
        notes = app_comments.get((remote, app), [])
        for _, _, c in values.get(app, []):
            notes += [x for x in c if x not in notes]
        out += notes
        out.append(f"id = {toml_string(app)}")
        out.append(f"remote = {toml_string(remote)}")
        default = line.marks.get(ws_marks.ALL, "ask")
        if default != "ask":
            out.append(f"default = {toml_string(default)}")
        mine = values.pop(app, [])
        fs = [v for k, v, _ in mine if k == "filesystem"]
        env = [v.split("=", 1) for k, v, _ in mine if k == "env"]
        talk = [v for k, v, _ in mine if k == "talk"]
        if fs:
            out.append("filesystems = [" + ", ".join(map(toml_string, fs)) + "]")
        if env:
            out.append("env = { " + ", ".join(f"{k} = {toml_string(v)}" for k, v in env) + " }")
        if talk:
            out.append("talk = [" + ", ".join(map(toml_string, talk)) + "]")
    if values:
        raise SystemExit(f"overrides of apps not in apps.txt: {', '.join(values)}")
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 64
    config = Path(argv[0])
    apps = ws_marks.MarkedList(config / "flatpak/apps.txt", key_fields={2})
    overrides = ws_marks.MarkedList(config / "flatpak/overrides.txt", **ws_marks.OVERRIDES)
    all_hosts = convert_marks.hosts(config)
    text = catalog_text(config, apps, overrides, all_hosts)
    flatpak_catalog.Catalog.parse(text, "catalog.toml")
    (config / "flatpak/catalog.toml").write_text(text)
    defaults = convert_marks.convert(config, apps, "flatpak", all_hosts)
    bad = convert_marks.check(config, apps, "flatpak", defaults, all_hosts)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
