"""wsbox apply, create, remove and check against the workstation marks of
distrobox/hosts.txt, with podman and distrobox replaced by shell stubs: a
container is a file in the state directory. The checklist runs on a real
pseudo terminal (pty.fork gives wsbox a controlling terminal)."""
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
WSBOX = ROOT / "bin/wsbox"

STUB = r'''#!/usr/bin/env bash
# podman and distrobox for wsbox: containers are files in $WSBOX_TEST_STATE.
state="$WSBOX_TEST_STATE"
echo "${0##*/} $*" >> "$state/.calls"
case "${0##*/}" in
    podman)
        case "$1 ${2:-}" in
            "container exists") [[ -e "$state/$3" ]] ;;
            "info "*) echo true ;;
            *) exit 1 ;;
        esac ;;
    distrobox)
        case "$1" in
            assemble)
                while (($#)); do [[ "$1" == --name ]] && touch "$state/$2"; shift; done ;;
            rm) rm -f "$state/${!#}" ;;
            *) exit 1 ;;
        esac ;;
esac
'''

CONTAINERS = "[a]\nimage=img-a\n\n[b]\nimage=img-b\n\n[c]\nimage=img-c\n"


class WsboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.state = root / "state"
        cfg = root / "cfg"
        stubs = root / "bin"
        for d in (self.state, cfg, stubs, root / "run"):
            d.mkdir()
        for name in ("podman", "distrobox", "distrobox-assemble"):
            (stubs / name).write_text(STUB)
            (stubs / name).chmod(0o755)
        (cfg / "containers.ini").write_text(CONTAINERS)
        (cfg / "exports.ini").write_text("")
        (cfg / "boxes.ini").write_text("")
        self.hosts = root / "hosts.txt"
        self.env = dict(os.environ, PATH=f"{stubs}:{os.environ['PATH']}",
                        WSBOX_CONFIG=str(cfg), WSBOX_HOSTS=str(self.hosts),
                        WSBOX_TEST_STATE=str(self.state), XDG_RUNTIME_DIR=str(root / "run"),
                        WS_HOST="test")

    def marks(self, text):
        self.hosts.write_text(text)

    def exists(self, *names):
        for name in names:
            (self.state / name).touch()

    def containers(self):
        return {p.name for p in self.state.iterdir() if not p.name.startswith(".")}

    def wsbox(self, *args):
        """wsbox ARGS without a terminal."""
        return subprocess.run([str(WSBOX), *args], env=self.env, text=True,
                              capture_output=True, stdin=subprocess.DEVNULL)

    def wsbox_tty(self, keys, *args):
        """wsbox ARGS on a pseudo terminal; KEYS are typed one chunk at a
        time once the question is on the screen. Returns (exit code, screen)."""
        pid, master = pty.fork()
        if pid == 0:
            try:
                os.execve(str(WSBOX), [str(WSBOX), *args], self.env)
            finally:
                os._exit(127)
        screen, keys = b"", list(keys)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if keys and b"[Y/n]" in screen:
                time.sleep(0.02)
                os.write(master, keys.pop(0).encode())
            if not select.select([master], [], [], 0.05)[0]:
                continue
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if not data:
                break
            screen += data
        os.close(master)
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status), screen.decode(errors="replace")

    def test_apply_creates_yes_marks_existing_and_waits_for_a_terminal(self):
        self.marks("a test=yes all=ask\nc other=yes all=ask\n")
        self.exists("b")
        p = self.wsbox("apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.containers(), {"a", "b"})
        self.assertIn("no terminal", p.stderr)
        # b existed without a line: marked yes; c not offered: untouched.
        self.assertEqual(self.hosts.read_text(),
                         "a test=yes all=ask\nc other=yes all=ask\nb test=yes all=ask\n")

    def test_apply_asks_and_writes_the_answer(self):
        self.marks("a test=no all=ask\nc other=yes all=ask\n")
        # Offered: b (no line), c (all=ask); uncheck b, keep c.
        code, screen = self.wsbox_tty(["n\n", " ", "\r"], "apply")
        self.assertEqual(code, 0, screen)
        self.assertIn("Поставить все? [Y/n]", screen)
        self.assertEqual(self.containers(), {"c"})
        self.assertEqual(self.hosts.read_text(),
                         "a test=no all=ask\nc other=yes test=yes all=ask\nb test=no all=ask\n")

    def test_select_offers_declined_unchecked(self):
        self.marks("a test=no all=ask\nb test=yes all=ask\nc test=yes all=ask\n")
        self.exists("b", "c")
        code, screen = self.wsbox_tty(["\n"], "apply", "--select")
        self.assertEqual(code, 0, screen)
        self.assertIn("(отказались)", screen)
        self.assertEqual(self.containers(), {"a", "b", "c"})
        self.assertIn("a test=yes all=ask\n", self.hosts.read_text())

    def test_cancel_answers_only_the_question(self):
        self.marks("a test=yes all=ask\nc other=yes all=ask\n")
        self.exists("b")
        code, screen = self.wsbox_tty(["n\n", "\x1b"], "apply")
        self.assertEqual(code, 0, screen)
        self.assertIn("выбор отменён", screen)
        self.assertEqual(self.containers(), {"a", "b"})
        self.assertEqual(self.hosts.read_text(),
                         "a test=yes all=ask\nc other=yes all=ask\nb test=yes all=ask\n")

    def test_unreadable_marks_stop_apply(self):
        self.marks("a test=maybe\n")
        p = self.wsbox("apply")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("test=maybe", p.stderr)
        self.assertEqual(self.containers(), set())
        calls = self.state / ".calls"
        self.assertNotIn("distrobox assemble", calls.read_text() if calls.exists() else "")

    def test_apply_name_and_create_mark_this_workstation(self):
        self.marks("a other=yes all=no\n")
        self.assertEqual(self.wsbox("apply", "a").returncode, 0)
        self.assertEqual(self.wsbox("create", "b").returncode, 0)
        self.assertEqual(self.containers(), {"a", "b"})
        self.assertEqual(self.hosts.read_text(),
                         "a other=yes test=yes all=no\nb test=yes all=ask\n")

    def test_remove_drops_the_line_or_marks_no(self):
        self.marks("a test=yes all=ask\nb other=yes test=yes all=ask\n")
        self.exists("a", "b")
        for name in ("a", "b"):
            p = self.wsbox("remove", name)
            self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.containers(), set())
        self.assertEqual(self.hosts.read_text(), "b other=yes test=no all=ask\n")

    def test_remove_checks_workstation_and_marks_before_removing(self):
        self.exists("a")
        for host, marks, message in (("legion.go", "a test=yes\n", "invalid workstation name"),
                                     ("test", "a test=maybe\n", "cannot read")):
            with self.subTest(host=host):
                self.marks(marks)
                self.env["WS_HOST"] = host
                p = self.wsbox("remove", "a")
                self.assertNotEqual(p.returncode, 0)
                self.assertIn(message, p.stderr)
                self.assertEqual(self.containers(), {"a"})
                self.assertEqual(self.hosts.read_text(), marks)

    def test_update_without_containers_has_nothing_to_do(self):
        # Every container declined here: not an error for ws update.
        self.marks("a test=no\nb test=no\nc test=no\n")
        result = self.wsbox("update")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing to update", result.stdout)

    def test_check_reports_by_mark(self):
        self.marks("a test=yes all=ask\nb test=no all=ask\nghost test=yes\n")
        self.exists("b")
        out = self.wsbox("check").stdout
        self.assertIn("FAIL  managed container missing: a (test=yes; wsbox apply)", out)
        self.assertIn("WARN  managed container exists but marked test=no: b", out)
        self.assertIn("INFO  managed container not offered on test yet: c", out)
        self.assertIn("WARN  distrobox/hosts.txt marks an undeclared container: ghost", out)


if __name__ == "__main__":
    unittest.main()
