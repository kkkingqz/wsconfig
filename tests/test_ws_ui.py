"""lib/ws_ui.py and libexec/ws-ui: the dialogs through gum (ws help plan-v2,
11.2), with the gum of tests/fixtures/bin (WS_GUM); one test on a real gum
in a pty when gum is in PATH."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest import mock

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ws_ui  # noqa: E402

GUM = ROOT / "tests/fixtures/bin/gum"
UI = ROOT / "libexec/ws-ui"


class StubTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.log, self.answers = self.tmp / "log", self.tmp / "answers"
        self.env = {"WS_GUM": str(GUM), "WS_UI_TTY": "/dev/null",
                    "WS_GUM_LOG": str(self.log), "WS_GUM_ANSWERS": str(self.answers)}
        p = mock.patch.dict(os.environ, self.env)
        p.start()
        self.addCleanup(p.stop)

    def answer(self, *answers):
        self.answers.write_text("".join(json.dumps(a) + "\n" for a in answers))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_offer_checks_all_but_the_declined(self):
        items = [("org.a", "App, with comma"), ("org.b", "B"), ("org.c", "")]
        self.assertEqual(ws_ui.offer(items, "Flatpak apps", unchecked=["org.c"]), ["org.a", "org.b"])
        args = self.calls()[0]
        self.assertEqual(args[:3], ["choose", "--label-delimiter=\t", "--header=Install on this host: Flatpak apps"])
        self.assertIn("--no-limit", args)
        self.assertIn("--selected=org.a  App\\, with comma", args)
        self.assertIn("org.c  (declined)\torg.c", args)
        self.assertEqual(ws_ui.offer([], "x"), [])

    def test_empty_choice_cancel_and_interrupt_differ(self):
        items = [("a", ""), ("b", "")]
        self.answer([""], "esc", "ctrl-c", ["zzz"])
        self.assertEqual(ws_ui.choose("T", items, ["a"]), [])
        self.assertIsNone(ws_ui.choose("T", items, ["a"]))
        with self.assertRaises(KeyboardInterrupt):
            ws_ui.choose("T", items)
        with self.assertRaises(ws_ui.UIError):
            ws_ui.choose("T", items)

    def test_labels_are_safe_and_unique(self):
        shown = ws_ui.labels([("a", "x\ty\x1b[31m"), ("bb", "c\\, d")])
        self.assertEqual(shown, {"a": "a   x y [31m", "bb": "bb  c\\ , d"})
        for items in ([("a", ""), ("a", "")], [("a\tb", "")], [("", "")]):
            with self.assertRaises(ValueError, msg=items):
                ws_ui.labels(items)

    def test_one_of_many(self):
        items = [("legiongo", ""), ("mbp16", ""), ("new host…", "")]
        self.assertEqual(ws_ui.choose("Host", items, ["mbp16"], many=False), "mbp16")
        self.assertNotIn("--no-limit", self.calls()[0])
        self.assertEqual(ws_ui.choose("Host", items, many=False), "legiongo")

    def test_confirm_input_pause(self):
        self.assertTrue(ws_ui.confirm("Q?"))
        self.assertFalse(ws_ui.confirm("Q?", default=False))
        self.answer("esc")
        self.assertFalse(ws_ui.confirm("Q?"))
        self.assertEqual(ws_ui.input_text("Name", "king"), "king")
        self.answer("esc")
        self.assertIsNone(ws_ui.input_text("Name", "king"))
        ws_ui.pause("Enter: reboot")
        self.assertEqual(self.calls()[-1], ["confirm", "--affirmative=OK", "--negative=", "Enter: reboot"])

    def test_no_terminal_runs_no_gum(self):
        with mock.patch.dict(os.environ, {"WS_UI_TTY": ""}), \
                mock.patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaises(ws_ui.NoTerminal):
                ws_ui.confirm("Q?")
        self.assertFalse(self.log.exists())

    def test_missing_gum_is_an_error_not_an_answer(self):
        with mock.patch.dict(os.environ, {"WS_GUM": "", "PATH": str(self.tmp)}), \
                mock.patch.object(ws_ui, "CORE", self.tmp):
            with self.assertRaises(ws_ui.UIError) as e:
                ws_ui.confirm("Q?")
        self.assertIn("gum not found", str(e.exception))

    def test_cli_exit_codes(self):
        def ui(*args, **env):
            return subprocess.run([str(UI), *args], env=os.environ | env,
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(ui("confirm", "Q?").returncode, 0)
        self.assertEqual(ui("confirm", "--default", "no", "Q?").returncode, 1)
        p = ui("input", "--value", "v", "Name")
        self.assertEqual((p.returncode, p.stdout), (0, "v\n"))
        self.answer("esc")
        self.assertEqual(ui("input", "Name").returncode, ws_ui.CANCELLED)
        p = ui("choose", "--selected", "b", "Host", "a\t", "b\t")
        self.assertEqual((p.returncode, p.stdout), (0, "b\n"))
        self.answer("ctrl-c")
        self.assertEqual(ui("pause", "x").returncode, ws_ui.INTERRUPTED)
        p = ui("confirm", "Q?", WS_UI_TTY="")
        self.assertEqual(p.returncode, ws_ui.NO_TERMINAL, p.stderr)


@unittest.skipUnless(shutil.which("gum"), "no gum in PATH")
class RealGumTests(unittest.TestCase):
    def test_enter_accepts_the_preselection(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import ws_ui; "
                "print(ws_ui.offer([('a', 'A, b'), ('b', 'B'), ('c', '')], 'x', ['c']))")
        m, s = pty.openpty()
        fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))

        def ctty():
            os.setsid()
            fcntl.ioctl(s, termios.TIOCSCTTY, 0)
        env = {k: v for k, v in os.environ.items() if not k.startswith("WS_")} | {"TERM": "xterm-256color"}
        p = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "lib")], stdin=s, stderr=s,
                             stdout=subprocess.PIPE, preexec_fn=ctty, env=env)
        os.close(s)
        deadline = time.time() + 1
        while time.time() < deadline:
            if select.select([m], [], [], 0.05)[0]:
                os.read(m, 65536)
        os.write(m, b"\r")
        out, _ = p.communicate(timeout=10)
        os.close(m)
        self.assertEqual(out.decode(), "['a', 'b']\n")


if __name__ == "__main__":
    unittest.main()
