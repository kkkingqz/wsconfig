#!/usr/bin/env python3
"""Per-workstation marks of the managed lists: flatpak/apps.txt (REMOTE APP)
and distrobox/hosts.txt (NAME). After the key fields a line carries
HOST=STATE tokens, STATE one of

    yes  installed on that workstation (apply installs it without asking)
    no   declined there (apply leaves it alone)
    ask  not offered yet (apply asks: "Поставить все? [Y/n]", then a checklist)

`all=STATE` stands for every workstation without its own mark; a line with
neither means ask. Installing through wsflatpak or wsbox marks the
workstation yes and, on a new line, all=ask; removing drops the line when no
other workstation is marked, else marks this one no. The workstation name is
`ws host`.

Used by wsbox as a command:

    ws_marks.py FILE state NAME HOST     print yes, no or ask
    ws_marks.py FILE states HOST NAME... print NAME STATE per line
    ws_marks.py FILE set NAME HOST STATE add the line (all=ask) if needed
    ws_marks.py FILE remove NAME HOST    drop the line or mark HOST no
    ws_marks.py FILE marked NAME         exit 0 when the line exists
    ws_marks.py FILE summary OLDFILE     +NAME, -NAME, NAME HOST=STATE (ws switch)
"""
from pathlib import Path
import re
import subprocess
import sys

STATES = ("yes", "no", "ask")
MARK = re.compile(r"([A-Za-z0-9][A-Za-z0-9_-]*)=(yes|no|ask)\Z")
ALL = "all"


def current_host(repo):
    """The flake host of this machine (WS_HOST or facts.nix hostname)."""
    p = subprocess.run([str(Path(repo) / "bin/ws"), "host"], text=True, capture_output=True)
    if p.returncode or not p.stdout.strip():
        raise SystemExit(p.stderr.strip() or "ws host: unknown workstation")
    return p.stdout.strip()


class Line:
    def __init__(self, raw):
        self.raw = raw
        body, sep, comment = raw.partition("#")
        self.comment = sep + comment if sep else ""
        self.key, self.marks = [], {}
        for token in body.split():
            m = MARK.match(token)
            if m:
                if m[1] in self.marks:
                    raise ValueError(f"duplicate mark {m[1]}: {raw}")
                self.marks[m[1]] = m[2]
            elif self.marks:
                raise ValueError(f"field after the marks: {raw}")
            elif "=" in token:
                raise ValueError(f"invalid mark {token!r} (HOST=yes|no|ask): {raw}")
            else:
                self.key.append(token)
        self.changed = False

    def render(self):
        if not self.changed:
            return self.raw
        marks = [f"{h}={s}" for h, s in self.marks.items() if h != ALL]
        if ALL in self.marks:
            marks.append(f"{ALL}={self.marks[ALL]}")
        text = " ".join(self.key + marks)
        return f"{text}  {self.comment}" if self.comment else text


class MarkedList:
    """FILE of KEY... [HOST=STATE...] [# comment] lines; comments, blank
    lines and untouched lines are written back as they were."""

    def __init__(self, path, key_fields=None):
        self.path = Path(path)
        self.key_fields = key_fields
        text = self.path.read_text() if self.path.exists() else ""
        self.lines = [Line(raw) for raw in text.splitlines()]
        for line in self.lines:
            if line.key and key_fields and len(line.key) not in key_fields:
                raise ValueError(f"{self.path}: invalid line: {line.raw}")

    def entries(self):
        return [line for line in self.lines if line.key]

    def find(self, name):
        """The line whose last key field is NAME (APP, container)."""
        for line in self.entries():
            if line.key[-1] == name:
                return line
        return None

    def state(self, name, host):
        line = self.find(name)
        if line is None:
            return "ask"
        return line.marks.get(host, line.marks.get(ALL, "ask"))

    def set(self, name, host, state, key=None):
        """Mark HOST; a missing line is appended as KEY host=STATE all=ask."""
        assert state in STATES and host != ALL
        line = self.find(name)
        if line is None:
            line = Line(" ".join(key or [name]))
            line.marks = {host: state, ALL: "ask"}
            line.changed = True
            self.lines.append(line)
            return line
        if line.marks.get(host) != state:
            marks = {h: s for h, s in line.marks.items() if h != ALL}
            marks[host] = state
            if ALL in line.marks:
                marks[ALL] = line.marks[ALL]
            line.marks = marks
            line.changed = True
        return line

    def remove(self, name, host):
        """Drop the line when no other workstation is marked, else mark HOST
        no. Returns 'removed', 'no' or None (no such line)."""
        line = self.find(name)
        if line is None:
            return None
        if any(h not in (host, ALL) for h in line.marks):
            self.set(name, host, "no")
            return "no"
        self.lines.remove(line)
        return "removed"

    def delete(self, name):
        line = self.find(name)
        if line is not None:
            self.lines.remove(line)
        return line is not None

    def save(self):
        text = "".join(line.render() + "\n" for line in self.lines)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(text)
        tmp.replace(self.path)


def summary(old, new):
    """What changed from OLD to NEW (MarkedList): the commit message of ws
    switch."""
    before = {line.key[-1]: line.marks for line in old.entries()}
    after = {line.key[-1]: line.marks for line in new.entries()}
    out = []
    for name, marks in after.items():
        if name not in before:
            out.append("+" + name)
        elif marks != before[name]:
            changed = [f"{h}={s}" for h, s in marks.items() if before[name].get(h) != s]
            changed += [f"-{h}" for h in before[name] if h not in marks]
            out.append(f"{name} {' '.join(changed)}")
    out += ["-" + name for name in before if name not in after]
    return ", ".join(out)


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    path, action, args = argv[0], argv[1], argv[2:]
    try:
        marks = MarkedList(path)
        if action == "state" and len(args) == 2:
            print(marks.state(*args))
        elif action == "states" and args:
            for name in args[1:]:
                print(name, marks.state(name, args[0]))
        elif action == "summary" and len(args) == 1:
            print(summary(MarkedList(args[0], key_fields=None), MarkedList(path, key_fields=None)))
        elif action == "marked" and len(args) == 1:
            return 0 if marks.find(args[0]) else 1
        elif action == "set" and len(args) == 3 and args[2] in STATES:
            marks.set(*args)
            marks.save()
        elif action == "remove" and len(args) == 2:
            print(marks.remove(*args) or "absent")
            marks.save()
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except ValueError as e:
        print(f"ws_marks: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
