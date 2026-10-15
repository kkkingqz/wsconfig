#!/usr/bin/env python3
"""The dialogs of ws: the only place that runs gum (ws help plan-v2, 11).

Items are (id, label); an answer is ids, never labels. The answers:

- accepted: the chosen ids, an empty list included (nothing checked);
- cancelled (Esc): None; the caller writes nothing;
- no terminal: NoTerminal, raised before gum runs (gum's exit 1 without
  /dev/tty is the one of Esc);
- Ctrl+C: KeyboardInterrupt;
- gum missing or failing: UIError (a SystemExit with the message), never
  an answer.

gum draws into its stderr: here that is the terminal, its stdout is a pipe
for the answer. Where gum comes from: WS_GUM (tests), libexec/gum of the
core in the store (nix/pkgs/ws.nix), else gum in PATH (the core run from a
checkout; home-manager installs it). WS_UI_TTY replaces /dev/tty and the
check of stdin (ws setup: WS_SETUP_TTY, tests).
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CANCELLED = 2
NO_TERMINAL = 3
INTERRUPTED = 130

CORE = Path(__file__).resolve().parent.parent
# What may not reach gum: its protocol is lines, label<TAB>id.
UNSAFE = re.compile(r"[\x00-\x1f\x7f]")


class NoTerminal(Exception):
    """No controlling terminal to ask on."""


class UIError(SystemExit):
    """gum is missing or failed: no answer of the user."""

    def __init__(self, message):
        super().__init__(f"ws: {message}")


def gum():
    path = os.environ.get("WS_GUM")
    if path:
        return path
    own = CORE / "libexec" / "gum"
    if os.access(own, os.X_OK):
        return str(own)
    found = shutil.which("gum")
    if found:
        return found
    raise UIError("gum not found (ws apply home)")


def open_tty():
    """A descriptor of the terminal to ask on, None without one: as before
    gum, stdin must be a terminal too (ws apply < /dev/null, a pipe or a
    service does not ask)."""
    path = os.environ.get("WS_UI_TTY")
    if not path and not sys.stdin.isatty():
        return None
    try:
        return os.open(path or "/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return None


def run(args, tty=None):
    """gum ARGS on the terminal; (exit code, stdout lines)."""
    fd = open_tty() if tty is None else tty
    if fd is None:
        raise NoTerminal()
    try:
        p = subprocess.run([gum()] + args, stdin=fd, stderr=fd, stdout=subprocess.PIPE, text=True)
    except OSError as e:
        raise UIError(f"gum: {e.strerror}") from None
    finally:
        if tty is None:
            os.close(fd)
    if p.returncode == 130:
        raise KeyboardInterrupt()
    if p.returncode not in (0, 1):
        raise UIError(f"gum {args[0]} failed (exit {p.returncode})")
    return p.returncode, p.stdout.splitlines()


def clean(text):
    """A label for gum: control characters become spaces."""
    return UNSAFE.sub(" ", text)


def check_id(item_id):
    if not item_id or UNSAFE.search(item_id):
        raise ValueError(f"ws_ui: invalid id {item_id!r}")
    return item_id


def escape(label):
    """A label in --selected: a list with commas, \\, is a comma; any other
    backslash is itself (gum 0.17)."""
    return label.replace(",", "\\,")


def labels(items):
    """{id: label}: the id first, so the labels are unique (gum matches
    --selected and answers by label)."""
    width = max(len(i) for i, _ in items)
    out = {}
    for item_id, label in items:
        check_id(item_id)
        # A backslash before a comma would not survive --selected.
        label = clean(label).strip().replace("\\,", "\\ ,")
        out[item_id] = f"{item_id:<{width}}  {label}".rstrip() if label else item_id
    if len(out) != len(items) or len(set(out.values())) != len(out):
        raise ValueError("ws_ui: duplicate ids")
    return out


def choose(title, items, selected=(), many=True, tty=None):
    """items: [(id, label)]. With MANY the checked ids (SELECTED start
    checked), else the one id (SELECTED: the first of it starts under the
    cursor); None when cancelled."""
    if not items:
        return [] if many else None
    shown = labels(items)
    args = ["choose", "--label-delimiter=\t", f"--header={clean(title)}"]
    if many:
        args.append("--no-limit")
    args += [f"--selected={escape(shown[i])}" for i in selected if i in shown]
    args += [f"{shown[i]}\t{i}" for i, _ in items]
    rc, lines = run(args, tty)
    if rc == 1:
        return None
    chosen = [line for line in lines if line]
    unknown = [c for c in chosen if c not in shown]
    if unknown:
        raise UIError(f"gum choose answered unknown items: {', '.join(unknown)}")
    if many:
        return chosen
    if len(chosen) != 1:
        raise UIError("gum choose answered no item")
    return chosen[0]


def confirm(question, default=True, tty=None):
    """Yes or no; Esc is no."""
    rc, _ = run(["confirm", f"--default={'true' if default else 'false'}", clean(question)], tty)
    return rc == 0


def input_text(prompt, value="", placeholder="", tty=None):
    """A line of text, VALUE in the field; None when cancelled."""
    args = ["input", f"--header={clean(prompt)}", f"--value={clean(value)}"]
    if placeholder:
        args.append(f"--placeholder={clean(placeholder)}")
    rc, lines = run(args, tty)
    if rc == 1:
        return None
    return lines[0] if lines else ""


def pause(text, tty=None):
    """Wait for Enter (one button)."""
    run(["confirm", "--affirmative=OK", "--negative=", clean(text)], tty)


def offer(items, what, unchecked=(), tty=None):
    """The checklist of the catalogs (ws apply, ws setup, ws flatpak apply,
    ws script apply; ws help plan-v2, 11.0, 2): items [(name, label)], all
    checked but UNCHECKED (declined earlier, marked). The chosen names, None
    when cancelled; raises NoTerminal."""
    if not items:
        return []
    shown = [(n, f"{label} (declined)".strip() if n in unchecked else label) for n, label in items]
    return choose(f"Install on this host: {what}",
                  shown, [n for n, _ in items if n not in unchecked], tty=tty)
