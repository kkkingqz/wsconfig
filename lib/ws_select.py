#!/usr/bin/env python3
"""Choice of the declared items that are not installed yet, for the apply of
wsflatpak (apps) and wsbox (containers).

Asks "install all?"; on "n" shows a checklist (Space toggles). Items left
out are remembered in a state file of this machine
(~/.local/state/workstation/<layer>/skipped, one name per line): the next
apply does not ask about them again and check reports them as info, not as
a failure. `--select` asks about every missing item again, the skipped ones
start unchecked. Without a terminal nothing is asked: every item not
skipped is chosen, as before.

Used by wsbox as a command:

    ws_select.py --state FILE --hint CMD [--select] -- NAME<TAB>LABEL...

prints the chosen names, one per line; exit 2 when the choice was cancelled.
"""
import argparse
import os
from pathlib import Path
import select as _select
import sys
import termios

CANCELLED = 2


def read_skipped(path):
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return []
    return [x.strip() for x in text.splitlines() if x.strip()]


def write_skipped(path, names):
    path = Path(path)
    if not names:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(f"{n}\n" for n in names))
    tmp.replace(path)


def unskip(path, names):
    """Drop NAMES from the state file (installed on explicit request)."""
    left = [n for n in read_skipped(path) if n not in set(names)]
    write_skipped(path, left)


def open_tty():
    if not sys.stdin.isatty():
        return None
    try:
        return os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return None


class Terminal:
    def __init__(self, fd):
        self.fd = fd

    def write(self, text):
        os.write(self.fd, text.encode())

    def readline(self):
        data = b""
        while not data.endswith(b"\n"):
            b = os.read(self.fd, 1)
            if not b:
                return None
            data += b
        return data.decode(errors="replace").strip()

    def key(self):
        b = os.read(self.fd, 1)
        if not b:
            return "eof"
        if b != b"\x1b":
            return b.decode(errors="replace")
        # A bare Esc or the start of an arrow key sequence.
        seq = b""
        while _select.select([self.fd], [], [], 0.05)[0]:
            seq += os.read(self.fd, 1)
            if seq[-1:].isalpha() or seq[-1:] == b"~":
                break
        return {b"[A": "up", b"OA": "up", b"[B": "down", b"OB": "down",
                b"[5~": "pgup", b"[6~": "pgdn", b"[H": "home",
                b"[F": "end"}.get(seq, "esc" if not seq else "")

    def size(self):
        try:
            size = os.get_terminal_size(self.fd)
            return size.columns, size.lines
        except OSError:
            return 80, 24


def checklist(term, title, items, checked):
    """items: [(name, label)]; checked: [bool]. Returns the list of checked
    names, or None when cancelled (Esc, q, Ctrl-D)."""
    checked = list(checked)
    pos = top = 0
    width = max(len(n) for n, _ in items)
    help_line = ("↑/↓ — выбор, Space — галочка, a — все/ничего, "
                 "Enter — установить отмеченные, Esc/q — отмена")
    drawn = 0

    old = termios.tcgetattr(term.fd)
    new = termios.tcgetattr(term.fd)
    new[3] &= ~(termios.ICANON | termios.ECHO)
    new[6][termios.VMIN] = 1
    new[6][termios.VTIME] = 0
    termios.tcsetattr(term.fd, termios.TCSADRAIN, new)
    term.write("\x1b[?25l")
    try:
        while True:
            cols, rows = term.size()
            # A wrapped line would break the redraw: cut to the width.
            cut = lambda text: text[:max(cols - 1, 10)]
            height = max(3, min(len(items), rows - 4))
            top = min(max(top, pos - height + 1), pos)
            lines = [cut(title)]
            for i in range(top, min(top + height, len(items))):
                name, label = items[i]
                mark = "[x]" if checked[i] else "[ ]"
                line = cut(f" {mark} {name:<{width}}  {label}".rstrip())
                if i == pos:
                    line = f"\x1b[7m{line}\x1b[0m"
                lines.append(line)
            more = len(items) - height
            count = sum(checked)
            lines.append(f"\x1b[2m{cut(help_line)}\x1b[0m")
            lines.append(cut(f"отмечено {count} из {len(items)}"
                             + (f", строки {top + 1}–{top + height}" if more > 0 else "")))
            out = (f"\x1b[{drawn - 1}A" if drawn > 1 else "") + "\r"
            out += "\n".join(f"\x1b[2K{x}" for x in lines)
            out += "\x1b[J"
            term.write(out)
            drawn = len(lines)

            k = term.key()
            if k in ("up", "k"):
                pos = (pos - 1) % len(items)
            elif k in ("down", "j"):
                pos = (pos + 1) % len(items)
            elif k == "pgup":
                pos = max(0, pos - height)
            elif k == "pgdn":
                pos = min(len(items) - 1, pos + height)
            elif k == "home":
                pos = 0
            elif k == "end":
                pos = len(items) - 1
            elif k == " ":
                checked[pos] = not checked[pos]
            elif k == "a":
                checked = [not all(checked)] * len(items)
            elif k in ("\n", "\r"):
                term.write("\n")
                return [n for (n, _), c in zip(items, checked) if c]
            elif k in ("esc", "q", "eof", "\x04"):
                term.write("\n")
                return None
    finally:
        term.write("\x1b[?25h")
        termios.tcsetattr(term.fd, termios.TCSADRAIN, old)


def choose(items, state, hint, what, reselect=False, tty=None):
    """items: [(name, label)] of the declared items that are missing.
    Returns the names to install, or None when cancelled. Updates STATE."""
    names = [n for n, _ in items]
    skipped = [n for n in read_skipped(state) if n in names]
    if reselect:
        ask = items
    else:
        ask = [(n, label) for n, label in items if n not in skipped]
        if skipped:
            print(f"Пропущены на этой машине: {', '.join(skipped)} "
                  f"(вернуть: {hint})", file=sys.stderr)
    if not ask:
        write_skipped(state, skipped)
        return []

    fd = open_tty() if tty is None else tty
    if fd is None:
        if reselect:
            raise SystemExit(f"{hint}: нужен терминал")
        write_skipped(state, skipped)
        return [n for n, _ in ask]

    term = Terminal(fd)
    try:
        width = max(len(n) for n, _ in ask)
        term.write(f"\nНе установлены {what} ({len(ask)}):\n")
        for n, label in ask:
            mark = " (пропущено)" if n in skipped else ""
            term.write(f"  {n:<{width}}  {label}{mark}\n")
        while True:
            term.write("Поставить все? [Y/n] ")
            answer = term.readline()
            if answer is None:
                term.write("\n")
                return None
            answer = answer.lower()
            if answer in ("", "y", "yes", "д", "да"):
                chosen = [n for n, _ in ask]
                break
            if answer in ("n", "no", "н", "нет"):
                chosen = checklist(
                    term, f"Что поставить ({what}):", ask,
                    [n not in skipped for n, _ in ask])
                if chosen is None:
                    return None
                break
    finally:
        if tty is None:
            os.close(fd)

    left = [n for n, _ in ask if n not in chosen]
    write_skipped(state, sorted(set(skipped) - set(chosen) | set(left)))
    if left:
        print(f"Пропущены (запомнено для этой машины): {', '.join(left)}; "
              f"вернуть: {hint}", file=sys.stderr)
    return chosen


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--state", required=True)
    p.add_argument("--hint", required=True)
    p.add_argument("--what", default="")
    p.add_argument("--select", action="store_true")
    p.add_argument("--unskip", action="store_true",
                   help="drop the names from the state file")
    p.add_argument("items", nargs="*", metavar="NAME<TAB>LABEL")
    ns = p.parse_args()

    items = [tuple((x.split("\t", 1) + [""])[:2]) for x in ns.items]
    if ns.unskip:
        unskip(ns.state, [n for n, _ in items])
        return 0
    chosen = choose(items, ns.state, ns.hint, ns.what, ns.select)
    if chosen is None:
        return CANCELLED
    for n in chosen:
        print(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
