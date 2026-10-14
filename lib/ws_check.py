#!/usr/bin/env python3
"""Result contract of the owner checks, the Python side of lib/check.bash
(helpws plan-v2, 2.4). ws check runs every owner with --json and reads only
the object printed by finish():

    {"status": "pass|warn|fail", "passes": N, "warnings": N, "failures": N,
     "messages": [{"level": "pass|warn|fail|info", "text": "..."}]}

With --json stdout carries only that object: everything else the check
prints, its child processes included, goes to stderr. Without --json the
same messages are printed for people; that text may change freely.

    ws_check.py result FILE VERBOSE   for ws check: "WARNINGS FAILURES", then
                                      the WARN/FAIL messages (all with
                                      VERBOSE=true); exit 1 on a bad object
"""
import json
import os
import sys

RULE = "-" * 72


class Check:
    def __init__(self, json_mode=False):
        self.json_mode = json_mode
        self.counts = {"pass": 0, "warn": 0, "fail": 0}
        self.messages = []
        self._out = None
        if json_mode:
            # As `exec 3>&1 1>&2` in check.bash: fd 1 of this process and
            # of its children is stderr until finish().
            sys.stdout.flush()
            self._out = os.dup(1)
            os.dup2(2, 1)

    def msg(self, level, text):
        self.messages.append({"level": level, "text": text})
        if level in self.counts:
            self.counts[level] += 1
        if not self.json_mode:
            print(f"  {level.upper():<5} {text}")

    def passed(self, text):
        self.msg("pass", text)

    def warn(self, text):
        self.msg("warn", text)

    def fail(self, text):
        self.msg("fail", text)

    def info(self, text):
        self.msg("info", text)

    def section(self, title):
        if not self.json_mode:
            print(f"\n{title}\n{RULE}")

    def status(self):
        return "fail" if self.counts["fail"] else "warn" if self.counts["warn"] else "pass"

    def finish(self):
        """Prints the summary (text or the object); returns the exit code,
        1 when a check failed."""
        if self.json_mode:
            sys.stdout.flush()
            os.dup2(self._out, 1)
            os.close(self._out)
            print(json.dumps({"status": self.status(), "passes": self.counts["pass"],
                              "warnings": self.counts["warn"], "failures": self.counts["fail"],
                              "messages": self.messages}), flush=True)
        else:
            print(f"\n  PASS={self.counts['pass']} WARN={self.counts['warn']} FAIL={self.counts['fail']}")
        return 1 if self.counts["fail"] else 0


def result(path, verbose):
    """Counts and messages of one result object, for ws check."""
    try:
        with open(path) as f:
            d = json.load(f)
        lines = [f"{int(d['warnings'])} {int(d['failures'])}"]
    except Exception:
        return 1
    for m in d.get("messages", []):
        if verbose or m["level"] in ("warn", "fail"):
            lines.append("  %-5s %s" % (m["level"].upper(), m["text"]))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "result":
        sys.exit(result(sys.argv[2], sys.argv[3] == "true"))
    print("usage: ws_check.py result FILE VERBOSE", file=sys.stderr)
    sys.exit(64)
