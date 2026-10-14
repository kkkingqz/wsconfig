"""lib/check.bash and lib/ws_check.py: one result contract (helpws plan-v2, 2.4)."""
import contextlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ws_check  # noqa: E402

MESSAGES = [("pass", "one"), ("warn", "two words"), ("info", 'quote " and tab\there'),
            ("fail", "кириллица"), ("pass", "last")]


def bash_check(json_mode):
    calls = "\n".join(f"{level} {shlex.quote(text)}" for level, text in MESSAGES)
    script = f"""set -u
. {ROOT}/lib/check.bash
{'check_json_mode' if json_mode else ''}
echo noise
{calls}
check_finish
"""
    return subprocess.run(["bash", "-c", script], text=True, capture_output=True)


def python_check(json_mode):
    script = f"""import json, subprocess, sys
sys.path.insert(0, {str(ROOT / 'lib')!r})
import ws_check
c = ws_check.Check({json_mode})
print("noise")
for level, text in {MESSAGES!r}:
    c.msg(level, text)
subprocess.run(["echo", "child noise"])
sys.exit(c.finish())
"""
    return subprocess.run([sys.executable, "-c", script], text=True, capture_output=True)


class CheckContractTests(unittest.TestCase):
    def test_same_object_from_bash_and_python(self):
        b, p = bash_check(True), python_check(True)
        self.assertEqual((b.returncode, p.returncode), (1, 1))
        self.assertEqual(json.loads(b.stdout), json.loads(p.stdout))
        self.assertEqual(json.loads(p.stdout), {
            "status": "fail", "passes": 2, "warnings": 1, "failures": 1,
            "messages": [{"level": l, "text": t} for l, t in MESSAGES]})

    def test_json_mode_keeps_stdout_for_the_object(self):
        p = python_check(True)
        self.assertEqual(len(p.stdout.splitlines()), 1)
        self.assertIn("noise", p.stderr)
        self.assertIn("child noise", p.stderr)

    def test_same_text_from_bash_and_python(self):
        b, p = bash_check(False), python_check(False)
        self.assertEqual(b.stdout, p.stdout.replace("child noise\n", ""))

    def test_status_without_failures(self):
        c = ws_check.Check(False)
        with contextlib.redirect_stdout(io.StringIO()):
            c.warn("x")
        self.assertEqual(c.status(), "warn")

    def test_result_for_ws_check(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"status": "warn", "passes": 1, "warnings": 1, "failures": 0,
                       "messages": [{"level": "pass", "text": "a"}, {"level": "warn", "text": "b"}]}, f)
        self.addCleanup(os.unlink, f.name)
        run = lambda v: subprocess.run([sys.executable, str(ROOT / "lib/ws_check.py"), "result", f.name, v],
                                       text=True, capture_output=True)
        self.assertEqual(run("false").stdout, "1 0\n  WARN  b\n")
        self.assertEqual(run("true").stdout, "1 0\n  PASS  a\n  WARN  b\n")
        Path(f.name).write_text("not json")
        self.assertEqual(run("false").returncode, 1)


if __name__ == "__main__":
    unittest.main()
