#!/usr/bin/env python3
"""Completion of ws from the usage of its commands (ws help terminal).

There is no list of completions to keep: the commands, their arguments and
options come from what each command prints for --help, and from the parser
of a Python command with build_parser() (argparse). Only the values of a
placeholder (APP, BOX, NAME of a checkpoint...) are named here, in VALUES.

    ws_complete.py build CORE          the spec of CORE as JSON (nix/pkgs/ws.nix
                                       writes it to CORE/share/ws/complete.json)
    ws_complete.py complete -- WORD... the candidates for the last WORD (the
                                       one being typed, may be empty), one per
                                       line: VALUE<TAB>DESCRIPTION, or @files

The usage of a command (ws help plan-v2, 11.4):

    Usage:
      ws CMD SUB [-n] [--opt VALUE] [a|b|NAME...]   description

- a line starts with `ws`; its description follows after two spaces;
- lowercase words are literal (a|b: either), a word with an uppercase
  letter is a placeholder (NAME, FILE.exe, KEY[=VALUE]), NAME... repeats;
- [ ] is optional, [A | B] either of the two; --opt VALUE takes a value;
- an option is described on a line of its own anywhere in the help:
  `  -n, --no-apply  description`.

bin/ws dispatches a command to its tool (`CMD) shift; exec
"$WS_CORE/libexec/TOOL"`, and the modules of `ws modules`): the arguments of
such a command are those of the tool's usage, the description of the
command that of bin/ws.
"""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
SPEC = "share/ws/complete.json"

# Placeholders that name files; the shell completes paths for them.
FILES = re.compile(r"\b(FILE|DIR|PATH|ARCHIVE|OUTPUT|PROGRAM)\b|\.[a-z]+\b")
# Placeholders whose value is typed (no candidates); a new placeholder must
# be in VALUES, FILES or here (tests/test_ws_complete.py).
FREE = {
    "ARG", "COMMAND", "N", "SECONDS", "MINUTES", "SIZE", "URL", "TITLE",
    "APPNAME", "ID", "A", "B", "VALUE", "KEY", "KEY[=VALUE]", "NAME URL",
    "WxH", "BUS", "SPEC", "TOPIC_PAGE", "PAGE",
}

# ---------------------------------------------------------------- the grammar


def split_description(line):
    """(syntax, description): the description starts after two spaces outside
    brackets."""
    depth = 0
    for i, c in enumerate(line):
        depth += c == "["
        depth -= c == "]"
        if depth == 0 and line.startswith("  ", i):
            return line[:i].strip(), line[i:].strip()
    return line.strip(), ""


def tokens(syntax):
    """Words and the brackets, `|` between spaces as its own token."""
    out = []
    for raw in syntax.split():
        if raw == "|":
            out.append("|")
            continue
        while raw.startswith("["):
            out.append("[")
            raw = raw[1:]
        tail = 0
        while raw.endswith("]") and raw.count("]") > raw.count("["):
            raw = raw[:-1]
            tail += 1
        if raw:
            out.append(raw)
        out += ["]"] * tail
    return out


def parse_seq(toks, i=0, until=None):
    """A sequence up to `until` (`]`); [A | B] -> ("group", [seq, ...])."""
    seq = []
    while i < len(toks) and toks[i] != until:
        t = toks[i]
        if t == "[":
            alts, cur = [], []
            i += 1
            while True:
                part, i = parse_seq(toks, i, "]|")
                cur = part
                alts.append(cur)
                if i >= len(toks):
                    raise ValueError("unclosed [")
                if toks[i] == "]":
                    i += 1
                    break
                i += 1  # |
            seq.append(("group", alts))
            continue
        if until and t in until:
            break
        if t == "|":
            # A | B at the top of a line: either of the two.
            rest, i = parse_seq(toks, i + 1, until)
            return [("group", [seq, rest], "required")], i
        seq.append(("word", t))
        i += 1
    return seq, i


def parse_seq_top(toks):
    seq, i = parse_seq(toks)
    if i != len(toks):
        raise ValueError(f"unexpected {toks[i]!r}")
    return seq


def is_option(word):
    return word.startswith("-") and len(word) > 1


def is_placeholder(word):
    return any(c.isupper() for c in word) or word.startswith("<")


def expand(seq, options):
    """The variants of a sequence: lists of positional words; options go to
    OPTIONS {name: value placeholder or None}."""
    variants = [[]]
    k = 0
    while k < len(seq):
        node = seq[k]
        if node[0] == "word":
            w = node[1]
            if is_option(w):
                name, _, value = w.partition("[=")
                name, _, inline = name.partition("=")
                nxt = seq[k + 1] if k + 1 < len(seq) else None
                if nxt and nxt[0] == "word" and is_placeholder(nxt[1]) and not value and not inline:
                    options[name] = nxt[1]
                    k += 2
                    continue
                options.setdefault(name, (inline or value.rstrip("]")) or None)
                k += 1
                continue
            variants = [v + [w] for v in variants]
        else:
            alts = []
            for alt in node[1]:
                alts += expand(alt, options)
            if len(node) == 2:
                alts.append([])
            unique = []
            for a in alts:
                if a not in unique:
                    unique.append(a)
            variants = [v + a for v in variants for a in unique]
        k += 1
    if len(variants) > 256:
        raise ValueError("too many variants")
    return variants


def element(word):
    repeat = word.endswith("...")
    word = word.removesuffix("...")
    literals, holder = [], None
    if is_placeholder(word) and not ("|" in word and not FILES.search(word) and
                                     all(is_placeholder(p) for p in word.split("|"))):
        parts = word.split("|")
        if FILES.search(word):
            return {"lit": [], "ph": word, "rep": repeat}
        for p in parts:
            if is_placeholder(p):
                holder = p.strip("<>").upper() if p.startswith("<") else p
            else:
                literals.append(p)
    else:
        for p in word.split("|"):
            if is_placeholder(p):
                holder = p
            else:
                literals.append(p)
    return {"lit": literals, "ph": holder, "rep": repeat}


def parse_line(line):
    """A usage line `ws ...` -> [{"el": [...], "opt": {...}, "desc": ...}]."""
    syntax, desc = split_description(line.strip())
    # `ws CMD ...`: the arguments are the tool's.
    toks = [t for t in tokens(syntax) if t != "..."]
    if not toks or toks[0] != "ws":
        raise ValueError(f"not a usage line: {line!r}")
    options = {}
    out = []
    for variant in expand(parse_seq_top(toks[1:]), options):
        out.append({"el": [element(w) for w in variant], "opt": options, "desc": desc})
    return out


OPTION_LINE = re.compile(
    r"^\s*((?:-\w|--[\w-]+)(?:,\s*(?:-\w|--[\w-]+))*)(?:[ =]\[?[A-Z][\w=\[\]|]*)?\s{2,}(\S.*)$")
USAGE_HEAD = re.compile(r"^\s*usage:\s*(.*)$", re.I)


def parse_help(text):
    """The usage lines and the option descriptions of a help text."""
    lines, about = [], {}
    rows = text.splitlines()
    i = 0
    while i < len(rows):
        m = USAGE_HEAD.match(rows[i])
        if not m:
            i += 1
            continue
        head = m.group(1).strip()
        if head.startswith("ws "):
            lines += parse_line(head)
        i += 1
        while i < len(rows) and rows[i].strip():
            row = rows[i].strip()
            if row.startswith("ws "):
                lines += parse_line(row)
            i += 1
    groups = []
    for row in rows:
        m = OPTION_LINE.match(row)
        if m:
            group = re.split(r",\s*", m.group(1))
            groups.append(group)
            for name in group:
                about.setdefault(name, m.group(2).strip())
    # -n in the usage, `-n, --no-apply` described: both complete.
    for line in lines:
        for group in groups:
            present = [n for n in group if n in line["opt"]]
            if present:
                line["opt"] = {**line["opt"], **{n: line["opt"][present[0]] for n in group}}
    return lines, about


# ---------------------------------------------------------- argparse commands


def from_parser(parser, prefix):
    """Usage lines of an argparse parser, PREFIX the words before it."""
    out = []
    opts, positionals, subs = {}, [], None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subs = action
        elif action.option_strings:
            if action.help == argparse.SUPPRESS or isinstance(action, argparse._HelpAction):
                continue
            value = None
            if action.nargs != 0:
                value = action.metavar or action.dest.upper()
            for name in action.option_strings:
                opts[name] = value
        else:
            positionals.append(action)
    about = {}
    for action in parser._actions:
        if action.option_strings and action.help and action.help != argparse.SUPPRESS:
            for name in action.option_strings:
                about[name] = action.help % vars(action) if "%(" in action.help else action.help
    if subs is not None:
        helps = {a.dest: a.help or "" for a in subs._choices_actions}
        for name, sub in subs.choices.items():
            desc = helps.get(name) or next((helps[k] for k, v in subs.choices.items()
                                            if v is sub and k in helps), "")
            for line, sub_about in from_parser(sub, prefix + [name]):
                if len(line["el"]) == len(prefix) + 1 or not line["desc"]:
                    line["desc"] = line["desc"] or desc
                line["opt"] = {**opts, **line["opt"]}
                out.append((line, {**about, **sub_about}))
        return out
    els = [{"lit": [w], "ph": None, "rep": False} for w in prefix]
    for action in positionals:
        repeat = action.nargs in ("*", "+", argparse.REMAINDER)
        name = action.metavar or action.dest.upper()
        lits = [str(c) for c in action.choices] if action.choices else []
        els.append({"lit": lits, "ph": None if lits else name, "rep": repeat})
    out.append(({"el": els, "opt": opts, "desc": ""}, about))
    return out


def load_parser(path):
    """build_parser() of a Python command, None when it has none."""
    text = path.read_text(errors="replace")
    if "def build_parser(" not in text:
        return None
    loader = importlib.machinery.SourceFileLoader(f"ws_cmd_{path.name.replace('-', '_')}", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module.build_parser()


# -------------------------------------------------------------- the spec


def dispatch(ws_text):
    """{command: tool} of bin/ws: its last case, the commands."""
    ws_text = ws_text[ws_text.rindex('\ncase "${1:-}" in'):]
    return dict(re.findall(r'^\s+(\S+)\) shift; exec "\$WS_CORE/libexec/([\w-]+)" "\$@" ;;$',
                           ws_text, re.M))


def modules(ws_text):
    block = re.search(r"^modules=\(\n(.*?)^\)", ws_text, re.M | re.S).group(1)
    return dict(re.findall(r'^\s+"(\S+) (\S+)"$', block, re.M))


def tool_source(core, tool):
    """The Python file whose build_parser() describes TOOL: the tool itself,
    or the one a bash wrapper names with `# completion: lib/FILE.py`."""
    path = core / "libexec" / tool
    text = path.read_text(errors="replace")
    m = re.search(r"^# completion: (\S+)$", text, re.M)
    if m:
        return core / m.group(1)
    return path if text.startswith("#!/usr/bin/env python3") else None


def command(path, *args):
    """PATH ARGS through the interpreter of its #! line: a Nix build has no
    /usr/bin/env."""
    head = path.read_text(errors="replace").split("\n", 1)[0]
    if head.startswith("#!"):
        argv = head[2:].split()
        if argv and argv[0].endswith("/env"):
            argv = argv[1:]
        if argv:
            return [*argv, str(path), *args]
    return [str(path), *args]


def run_help(core, tool):
    with tempfile.TemporaryDirectory() as home:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home,
               "LC_ALL": "C.UTF-8", "WS_CORE": str(core), "WS_CONFIG": str(Path(home) / "none")}
        p = subprocess.run(command(core / "libexec" / tool, "--help"), env=env, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    return p.stdout


def tool_lines(core, cmd, tool):
    source = tool_source(core, tool)
    parser = load_parser(source) if source else None
    if parser is not None:
        pairs = from_parser(parser, [cmd])
        lines = [line for line, _ in pairs]
        about = {}
        for _, a in pairs:
            about.update(a)
        return lines, about
    text = run_help(core, tool)
    lines, about = parse_help(text)
    if not lines:
        raise ValueError(f"libexec/{tool} --help: no usage lines of ws {cmd}:\n{text}")
    for line in lines:
        first = line["el"][0] if line["el"] else None
        if not first or first["lit"] != [cmd]:
            raise ValueError(f"libexec/{tool}: usage line not of ws {cmd}: {line}")
    return lines, about


def build(core=CORE):
    ws_text = (core / "bin/ws").read_text()
    top, about = parse_help(subprocess.run(command(core / "bin/ws", "--help"), text=True,
                                           capture_output=True, check=True).stdout)
    owners = {**dispatch(ws_text), **modules(ws_text)}
    lines = []
    for line in top:
        cmd = line["el"][0]["lit"][0] if line["el"] and line["el"][0]["lit"] else None
        if cmd in owners:
            # The tool describes the arguments: only the name from here.
            line = {"el": line["el"][:1], "opt": {}, "desc": line["desc"]}
        line["top"] = True
        lines.append(line)
    tools = {}
    for cmd, tool in sorted(owners.items()):
        sub, sub_about = tool_lines(core, cmd, tool)
        tools[cmd] = tool
        for line in sub:
            line["top"] = False
            line["about"] = {o: sub_about[o] for o in line["opt"] if o in sub_about}
            lines.append(line)
    for line in lines:
        if line["top"]:
            line["about"] = {o: about[o] for o in line["opt"] if o in about}
    steps = {}
    for name in ("apply", "update", "check"):
        p = subprocess.run(command(core / "bin/ws", "steps", name), text=True, capture_output=True,
                           check=True)
        steps[name] = p.stdout.split()
    # Topics: the case of helpws (each page by its first name), described
    # by the list of ws help.
    about = {}
    p = subprocess.run(command(core / "libexec/helpws", "--help"), text=True, capture_output=True,
                       check=True)
    for row in p.stdout.splitlines():
        m = re.match(r"^  ([a-z][\w-]*) {2,}(\S.*)$", row)
        if m and "  " not in m.group(2):  # not a row of several topics
            about[m.group(1)] = m.group(2)
    text = (core / "libexec/helpws").read_text()
    body = text[text.index('case "$topic" in'):]
    topics = []
    for m in re.finditer(r"^    ([a-z0-9|-]+)\)", body[:body.index("\nesac")], re.M):
        name = m.group(1).split("|")[0]
        if name not in ("help", "man") and not name.startswith("-"):
            topics.append([name, about.get(name, "")])
    return {"lines": lines, "tools": tools, "steps": steps, "topics": topics}


def placeholders(spec):
    """(command words, placeholder) of every placeholder of the spec."""
    out = set()
    for line in spec["lines"]:
        words = [e["lit"][0] for e in line["el"] if e["lit"] and len(e["lit"]) == 1 and not e["ph"]]
        for e in line["el"]:
            if e["ph"]:
                out.add((words[0] if words else "", e["ph"]))
        for value in line["opt"].values():
            if value:
                out.add((words[0] if words else "", value))
    return out


# -------------------------------------------------------------- the values


def config():
    return Path(os.environ.get("WSCONFIG") or os.environ.get("WS_CONFIG") or Path.home() / "wsconfig")


def state(*parts):
    return Path(os.environ.get("WS_STATE") or Path.home() / ".local/state/wsconfig", *parts)


def share(*parts):
    # As the tools: not XDG_DATA_HOME (a Flatpak sets its own).
    return Path.home().joinpath(".local/share/wsconfig", *parts)


def manifest(*parts):
    try:
        return json.loads(share(*parts).read_text())
    except (OSError, ValueError):
        return None


def lines_of(cmd, timeout=5):
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line for line in p.stdout.splitlines() if line.strip()] if p.returncode == 0 else []


def dirs(path):
    try:
        return sorted(p.name for p in path.iterdir() if p.is_dir())
    except OSError:
        return []


def flatpak_user_apps():
    return lines_of(["flatpak", "list", "--user", "--app", "--columns=application"])


def flatpak_catalog(*args):
    env = {**os.environ, "WSCONFIG": str(config())}
    try:
        p = subprocess.run([sys.executable, str(CORE / "lib/flatpak_catalog.py"), *args],
                           text=True, capture_output=True, timeout=5, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return p.stdout.split() if p.returncode == 0 else []


def flatpak_app(ctx):
    sub = ctx["words"][1]
    if sub == "install":
        # The apps of the remote of --remote (flathub), as IDs and refs.
        remote, raw = "flathub", ctx["raw"]
        for i, w in enumerate(raw):
            if w == "--remote" and i + 1 < len(raw):
                remote = raw[i + 1]
            elif w.startswith("--remote="):
                remote = w.split("=", 1)[1]
        out = []
        for ref in lines_of(["flatpak", "remote-ls", "--user", "--cached", "--app",
                             "--columns=ref", remote]):
            out += [ref.split("/")[0], f"app/{ref}"]
        return out
    if sub == "unmanage":
        return flatpak_catalog("apps")
    if sub.startswith("un") and sub != "uninstall":
        return flatpak_user_apps() + flatpak_catalog("override-apps")
    return flatpak_user_apps()


def flatpak_value(kind, offered=()):
    def values(ctx):
        if ctx["words"][1].startswith("un"):
            return flatpak_catalog("values", ctx["args"][0], kind) if ctx["args"] else []
        return list(offered)
    return values


def flatpak_remotes(ctx):
    cfg = Path(os.environ.get("WSFLATPAK_CONFIG") or share("flatpak"))
    try:
        return list(json.loads((cfg / "flatpak.json").read_text()).get("remotes", {}))
    except (OSError, ValueError, AttributeError):
        return lines_of(["flatpak", "remotes", "--user", "--columns=name"])


def boxes():
    data = manifest("distrobox", "boxes.json")
    return [b for b in data if isinstance(b, dict) and "name" in b] if isinstance(data, list) else []


def box_apps(ctx):
    args = ctx["args"]
    for b in boxes():
        if args and b["name"] == args[0]:
            return sorted(b.get("exports") or {})
    return []


def windows_apps(ctx):
    data = manifest("windows", "apps.json")
    return sorted((data or {}).get("apps") or {}) if isinstance(data, dict) else []


def widgets_catalog(ctx):
    try:
        return [f"{w['id']}\t{w.get('label', '')}"
                for w in json.loads(share("widgets", "catalog.json").read_text())]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def ws_lines(*args):
    return lines_of([str(CORE / "bin/ws"), *args])


def ws_hosts(ctx):
    return dirs(config() / "hosts")


# (command, placeholder) or placeholder alone -> a function of the context
# {"args": the words typed for the placeholders before, "spec": the spec}.
VALUES = {
    ("apply", "STEP"): lambda ctx: ctx["spec"]["steps"]["apply"],
    ("update", "STEP"): lambda ctx: ctx["spec"]["steps"]["update"],
    ("help", "TOPIC"): lambda ctx: [f"{n}\t{d}" for n, d in ctx["spec"]["topics"]],
    ("help", "PAGE"): lambda ctx: sorted(p.name.removesuffix(".1") for p in (
        Path.home() / ".local/share/man/man1").glob("ws-*.1")),
    ("baseline", "NAME"): lambda ctx: dirs(state("baseline")),
    ("baseline", "A"): lambda ctx: dirs(state("baseline")),
    ("baseline", "B"): lambda ctx: dirs(state("baseline")),
    ("checkpoint", "NAME"): lambda ctx: dirs(state("checkpoints")),
    ("container", "HOST"): ws_hosts,
    ("fact", "HOST"): ws_hosts,
    ("fact", "NAME"): lambda ctx: [],
    ("setup", "NAME"): ws_hosts,
    ("clean", "SCOPE"): lambda ctx: ["nix", "podman", "flatpak"],
    ("flatpak", "APP"): flatpak_app,
    ("flatpak", "REMOTE"): flatpak_remotes,
    ("flatpak", "SPEC"): flatpak_value("filesystem", (
        "host", "host:ro", "home", "home:ro", "xdg-download", "xdg-documents", "xdg-desktop",
        "xdg-pictures", "xdg-videos", "xdg-music", "@files")),
    ("flatpak", "BUS"): flatpak_value("talk", ("org.freedesktop.Flatpak", "org.kde.StatusNotifierWatcher")),
    ("flatpak", "KEY"): flatpak_value("env"),
    ("box", "NAME"): lambda ctx: [b["name"] for b in boxes()],
    ("box", "APP"): box_apps,
    ("windows", "BOX"): lambda ctx: [b["name"] for b in boxes() if b.get("profile")],
    ("windows", "APP"): windows_apps,
    ("gpu", "COMMAND"): lambda ctx: ["@commands"],
    ("windows", "NAME"): lambda ctx: [],
    ("widgets", "ID"): widgets_catalog,
    ("script", "NAME"): lambda ctx: ws_lines("script", "names"),
    ("suspend", "KERNEL"): lambda ctx: dirs(Path("/lib/modules")),
    ("gmux", "KERNEL"): lambda ctx: dirs(Path("/lib/modules")),
    ("psr", "KERNEL"): lambda ctx: dirs(Path("/lib/modules")),
    ("backup", "SCOPE"): lambda ctx: ["home", "vms", "all", "system"],
}


def known(cmd, holder):
    return (cmd, holder) in VALUES or holder in VALUES or FILES.search(holder) or holder in FREE


def values(spec, cmd, holder, args, words=(), raw=()):
    if FILES.search(holder):
        return ["@files"]
    fn = VALUES.get((cmd, holder)) or VALUES.get(holder)
    if not fn:
        return []
    try:
        return list(fn({"args": args, "spec": spec, "words": list(words) + [""], "raw": list(raw)}))
    except Exception:  # a broken source of values must not break the shell
        return []


# -------------------------------------------------------------- matching


def options_of(spec, cmd):
    out = {}
    for line in spec["lines"]:
        if line_cmd(line) == cmd:
            out.update(line["opt"])
    return out


def line_cmd(line):
    first = line["el"][0] if line["el"] else None
    return first["lit"][0] if first and first["lit"] else None


def match(line, words):
    """The index of the element for the next word after WORDS and the words
    typed for placeholders; None when the line does not fit."""
    els, j, args = line["el"], 0, []
    for w in words:
        while True:
            if j >= len(els):
                if els and els[-1]["rep"]:
                    j = len(els) - 1
                else:
                    return None
            e = els[j]
            if w in e["lit"] or e["ph"]:
                if e["ph"] and w not in e["lit"]:
                    args.append(w)
                if not e["rep"]:
                    j += 1
                break
            if e["rep"] and j + 1 < len(els):
                j += 1
                continue
            return None
    return j, args


def complete(spec, words, current):
    """Candidates for CURRENT after WORDS (the words after ws)."""
    cmd = words[0] if words else None
    opts = options_of(spec, cmd) if cmd else {}
    # The value of an option.
    if words and words[-1] in opts and opts[words[-1]]:
        holder = opts[words[-1]]
        return [v for v in values(spec, cmd, holder, [], [cmd], words)]
    positional, skip = [], False
    for w in words:
        if skip:
            skip = False
            continue
        if is_option(w):
            name, eq, _ = w.partition("=")
            skip = not eq and bool(opts.get(name))
            continue
        positional.append(w)
    out, seen = [], set()

    def add(value, desc=""):
        if value not in seen:
            seen.add(value)
            out.append(f"{value}\t{desc}" if desc else value)

    if current.startswith("-") and positional:
        for line in spec["lines"]:
            if line["top"] != (len(positional) == 0) and line_cmd(line) in spec["tools"]:
                continue
            if line_cmd(line) != positional[0]:
                continue
            m = match(line, positional)
            if m is None:
                continue
            for name in line["opt"]:
                add(name, line.get("about", {}).get(name, ""))
        return out
    for line in spec["lines"]:
        if positional:
            if line_cmd(line) != positional[0]:
                continue
            if line["top"] and positional[0] in spec["tools"]:
                continue
        elif not line["top"]:
            continue
        m = match(line, positional)
        if m is None:
            continue
        j, args = m
        els = line["el"]
        if j >= len(els):
            if not (els and els[-1]["rep"]):
                continue
            j = len(els) - 1
        e = els[j]
        literal_run = 0
        while literal_run < len(els) and els[literal_run]["lit"] and not els[literal_run]["ph"] \
                and len(els[literal_run]["lit"]) == 1:
            literal_run += 1
        desc = line["desc"] if j == literal_run - 1 or (j == 0 and line["top"]) else ""
        if j == 0 and not line["top"]:
            desc = ""
        for lit in e["lit"]:
            add(lit, desc)
        if e["ph"]:
            for v in values(spec, positional[0] if positional else "", e["ph"], args,
                            positional, words):
                if "\t" in v:
                    add(*v.split("\t", 1))
                else:
                    add(v)
    return out


# -------------------------------------------------------------- the spec file


def source_key(core):
    """A key of the core files the spec comes from (a checkout: the cache)."""
    h = hashlib.sha256()
    for d in ("bin", "libexec", "lib"):
        for p in sorted((core / d).glob("*")):
            if p.is_file():
                h.update(f"{p}:{p.stat().st_mtime_ns}".encode())
    return h.hexdigest()[:16]


def load_spec(core=CORE):
    built = core / SPEC
    if built.is_file():
        return json.loads(built.read_text())
    # A checkout of the core: built once per change of its files.
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache", "ws",
                 f"complete-{source_key(core)}.json")
    try:
        return json.loads(cache.read_text())
    except (OSError, ValueError):
        pass
    spec = build(core)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        for old in cache.parent.glob("complete-*.json"):
            old.unlink()
        cache.write_text(json.dumps(spec))
    except OSError:
        pass
    return spec


def main(argv):
    if len(argv) == 2 and argv[0] == "build":
        json.dump(build(Path(argv[1]).resolve()), sys.stdout, indent=1, sort_keys=True)
        print()
        return 0
    if argv[:2] == ["complete", "--"]:
        words = argv[2:]
        current = words.pop() if words else ""
        for line in complete(load_spec(), words, current):
            print(line)
        return 0
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
