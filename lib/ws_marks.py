#!/usr/bin/env python3
"""Per-workstation marks of the managed lists: flatpak/apps.txt (REMOTE APP)
and distrobox/hosts.txt (NAME); flatpak/overrides.txt (APP KIND VALUE)
with yes and no only (OVERRIDES). After the key fields a line carries
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
    ws_marks.py FILE summary OLDFILE [N] +NAME, -NAME, NAME HOST=STATE (ws switch);
                                         N fixed key fields (overrides.txt: 3),
                                         NAME is then the whole key

An override line applies on a workstation whose state is yes; a line
without its own mark and without all= applies everywhere.
"""
from pathlib import Path
import re
import subprocess
import sys

STATES = ("yes", "no", "ask")
MARK = re.compile(r"([A-Za-z0-9][A-Za-z0-9_-]*)=(yes|no|ask)\Z")
ALL = "all"
# flatpak/overrides.txt: APP KIND VALUE, then marks (a VALUE may be KEY=yes);
# yes or no, applies everywhere unless marked no; a new line gets all=yes.
OVERRIDES = dict(fixed=3, default="yes", new_all="yes", states=("yes", "no"))


def check_host(host):
    """HOST as it can stand in a mark: what the parser reads back."""
    if host == ALL or not MARK.match(f"{host}=yes"):
        raise ValueError(f"invalid workstation name {host!r} for a mark "
                         "(letters, digits, - and _; not all)")
    return host


def current_host(repo):
    """The flake host of this machine (WS_HOST or facts.nix hostname)."""
    p = subprocess.run([str(Path(repo) / "bin/ws"), "host"], text=True, capture_output=True)
    if p.returncode or not p.stdout.strip():
        raise SystemExit(p.stderr.strip() or "ws host: unknown workstation")
    try:
        return check_host(p.stdout.strip())
    except ValueError as e:
        raise SystemExit(str(e))


class Line:
    def __init__(self, raw, fixed=None):
        """FIXED: the first FIXED fields are the key whatever they look like
        (an env VALUE such as KEY=yes), every field after them a mark."""
        self.raw = raw
        body, sep, comment = raw.partition("#")
        self.comment = sep + comment if sep else ""
        self.key, self.marks = [], {}
        tokens = body.split()
        if fixed:
            self.key, tokens = tokens[:fixed], tokens[fixed:]
        for token in tokens:
            m = MARK.match(token)
            if fixed and not m:
                raise ValueError(f"invalid mark {token!r} (HOST=yes|no): {raw}")
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

    def __init__(self, path, key_fields=None, fixed=None, default="ask",
                 new_all="ask", states=STATES):
        """DEFAULT: the state of a line with neither the own mark nor all=;
        NEW_ALL: all= of a new line; STATES: the allowed ones (OVERRIDES)."""
        self.path = Path(path)
        self.key_fields = {fixed} if fixed else key_fields
        self.fixed, self.default, self.new_all, self.states = fixed, default, new_all, states
        text = self.path.read_text() if self.path.exists() else ""
        self.lines = [Line(raw, fixed) for raw in text.splitlines()]
        for line in self.lines:
            if line.key and self.key_fields and len(line.key) not in self.key_fields:
                raise ValueError(f"{self.path}: invalid line: {line.raw}")
            bad = [f"{h}={s}" for h, s in line.marks.items() if s not in states]
            if bad:
                raise ValueError(f"{self.path}: {bad[0]}: only {'|'.join(states)} here: {line.raw}")

    def entries(self):
        return [line for line in self.lines if line.key]

    def find(self, name):
        """The line whose last key field is NAME (APP, container), or whose
        whole key is NAME when it is a tuple or list (overrides)."""
        whole = isinstance(name, (tuple, list))
        for line in self.entries():
            if (line.key == list(name)) if whole else (line.key[-1] == name):
                return line
        return None

    def line_state(self, line, host):
        return line.marks.get(host, line.marks.get(ALL, self.default))

    def state(self, name, host):
        line = self.find(name)
        if line is None:
            return "ask"
        return self.line_state(line, host)

    @staticmethod
    def others(line, host):
        """Workstations other than HOST with their own mark on LINE."""
        return [h for h in line.marks if h not in (host, ALL)]

    def add(self, key, marks, after=None):
        """A new line KEY MARKS, after the line AFTER (else at the end)."""
        line = Line(" ".join(key), self.fixed)
        line.marks = dict(marks)
        line.changed = True
        index = self.lines.index(after) + 1 if after is not None else len(self.lines)
        self.lines.insert(index, line)
        return line

    def set(self, name, host, state, key=None):
        """Mark HOST; a missing line is appended as KEY host=STATE all=NEW_ALL."""
        assert state in self.states
        check_host(host)
        line = self.find(name)
        if line is None:
            return self.add(key or [name], {host: state, ALL: self.new_all})
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
        check_host(host)
        line = self.find(name)
        if line is None:
            return None
        if self.others(line, host):
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
    switch. A line is named by its last key field, by the whole key in a
    list of fixed key fields."""
    name = (lambda line: " ".join(line.key)) if new.fixed else (lambda line: line.key[-1])
    before = {name(line): line.marks for line in old.entries()}
    after = {name(line): line.marks for line in new.entries()}
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
        if action == "summary" and len(args) in (1, 2):
            fixed = int(args[1]) if len(args) == 2 else None
            print(summary(MarkedList(args[0], fixed=fixed), MarkedList(path, fixed=fixed)))
            return 0
        marks = MarkedList(path)
        if action == "state" and len(args) == 2:
            print(marks.state(*args))
        elif action == "states" and args:
            for name in args[1:]:
                print(name, marks.state(name, args[0]))
        elif action == "marked" and len(args) == 1:
            return 0 if marks.find(args[0]) else 1
        elif action == "set" and len(args) == 3 and args[2] in STATES:
            if marks.set(*args).changed:
                marks.save()
        elif action == "remove" and len(args) == 2:
            result = marks.remove(*args)
            print(result or "absent")
            if result:
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
