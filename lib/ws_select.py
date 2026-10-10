#!/usr/bin/env python3
"""Interactive choice of the items apply would install, for wsflatpak
(apps) and wsbox (containers): the items not offered to this workstation yet
(ws_marks: state ask).

Asks "Поставить все? [Y/n]"; on "n" a checklist (Space toggles, a toggles
all, Enter confirms, Esc/q cancels). The caller writes the answer into its
list (ws_marks): chosen items yes, the rest no; a cancel answers only the
question (the items stay ask, the rest of apply goes on).

Used by wsbox as a command:

    ws_select.py --what TEXT [--unchecked NAME]... -- NAME<TAB>LABEL...

prints the chosen names, one per line; exit 2 when cancelled, 3 without a
terminal.
"""
import argparse
import os
import select as _select
import sys
import termios

CANCELLED = 2
NO_TERMINAL = 3


class NoTerminal(Exception):
    """No controlling terminal to ask on."""


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
        # A bare Esc or a key sequence: CSI (ESC [ ... A) or, in application
        # cursor mode, SS3 (ESC O A); both end with a letter or ~ after
        # their introducer.
        seq = b""
        while _select.select([self.fd], [], [], 0.05)[0]:
            seq += os.read(self.fd, 1)
            if seq[:1] not in (b"[", b"O"):
                break
            if len(seq) > 1 and (seq[-1:].isalpha() or seq[-1:] == b"~"):
                break
        return {b"[A": "up", b"OA": "up", b"[B": "down", b"OB": "down",
                b"[5~": "pgup", b"[6~": "pgdn", b"[H": "home", b"OH": "home",
                b"[1~": "home", b"[F": "end", b"OF": "end",
                b"[4~": "end"}.get(seq, "esc" if not seq else "")

    def size(self):
        try:
            size = os.get_terminal_size(self.fd)
            # A terminal that reports no size (0x0) gets the classic one.
            return size.columns or 80, size.lines or 24
        except OSError:
            return 80, 24


def checklist(term, title, items, checked):
    """items: [(name, label)]; checked: [bool]. Returns the list of checked
    names, or None when cancelled (Esc, q, Ctrl-D)."""
    checked = list(checked)
    pos = top = 0
    width = max(len(n) for n, _ in items)
    help_line = ("↑/↓ — выбор, Space — галочка, a — все/ничего, "
                 "Enter — установить отмеченные, Esc/q — не сейчас")
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


def choose(items, what, unchecked=(), tty=None):
    """items: [(name, label)]. Returns the chosen names, None when cancelled;
    raises NoTerminal without a terminal. UNCHECKED start unchecked in the
    checklist and are marked in the list (declined earlier)."""
    if not items:
        return []
    fd = open_tty() if tty is None else tty
    if fd is None:
        raise NoTerminal()
    term = Terminal(fd)
    try:
        width = max(len(n) for n, _ in items)
        term.write(f"\nНе установлены {what} ({len(items)}):\n")
        for n, label in items:
            mark = " (отказались)" if n in unchecked else ""
            term.write(f"  {n:<{width}}  {label}{mark}\n")
        while True:
            term.write("Поставить все? [Y/n] ")
            answer = term.readline()
            if answer is None:
                term.write("\n")
                return None
            answer = answer.lower()
            if answer in ("", "y", "yes", "д", "да"):
                return [n for n, _ in items]
            if answer in ("n", "no", "н", "нет"):
                return checklist(term, f"Что поставить ({what}):", items,
                                 [n not in unchecked for n, _ in items])
    finally:
        if tty is None:
            os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--what", default="")
    p.add_argument("--unchecked", action="append", default=[])
    p.add_argument("items", nargs="*", metavar="NAME<TAB>LABEL")
    ns = p.parse_args()
    items = [tuple((x.split("\t", 1) + [""])[:2]) for x in ns.items]
    try:
        chosen = choose(items, ns.what, ns.unchecked)
    except NoTerminal:
        return NO_TERMINAL
    if chosen is None:
        return CANCELLED
    for n in chosen:
        print(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
