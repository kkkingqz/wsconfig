"""lib/ws_catalog.py: the host choices of the catalogs (ws help plan-v2, 3.1).
lib/catalog.nix reads the same fixture (lib/test-catalog.nix)."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ws_catalog  # noqa: E402
import ws_select  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/catalog"


class CatalogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name)
        shutil.copytree(FIXTURE, self.config / "hosts")

    def choice(self, module="boxes", host="a"):
        return ws_catalog.Choice(module, host, self.config)

    def path(self, module="boxes", host="a"):
        return self.config / "hosts" / host / f"{module}.toml"

    def cli(self, *args, host="a"):
        env = {k: v for k, v in os.environ.items() if not k.startswith("WS")}
        env["WSCONFIG"] = str(self.config)
        return subprocess.run([sys.executable, str(ROOT / "lib/ws_catalog.py"), "--host", host, *args],
                              env=env, text=True, capture_output=True, stdin=subprocess.DEVNULL)

    def test_state_is_the_choice_else_the_default(self):
        c = self.choice()
        self.assertEqual(c.state("arch"), "yes")
        self.assertEqual(c.state("proton", "yes"), "no")
        self.assertEqual(c.state("t2bce-build", "no"), "no")
        self.assertEqual(c.state("other"), "ask")
        self.assertEqual(c.state("other", "yes"), "yes")
        # No file: the defaults.
        self.assertEqual(self.choice(host="b").state("arch", "no"), "no")
        with self.assertRaises(ValueError):
            c.state("x", "maybe")

    def test_edit_keeps_comments_and_order(self):
        c = self.choice()
        self.assertTrue(c.set("proton", "yes"))
        self.assertFalse(c.set("arch", "yes"))
        c.set("wine", "ask")
        c.save()
        text = self.path().read_text()
        self.assertIn("# a: Distrobox containers", text)
        self.assertIn('"arch",  # comment inside', text)
        self.assertEqual(self.choice().yes(), ["arch", "proton"])
        self.assertEqual(self.choice().no(), [])
        self.assertEqual(self.choice().state("wine"), "ask")

    def test_yes_appends_in_order(self):
        c = self.choice("widgets", "b")
        c.set("third", "yes")
        c.save()
        self.assertEqual(self.choice("widgets", "b").yes(), ["compact", "example", "third"])

    def test_new_file_gets_a_header(self):
        c = self.choice(host="new")
        c.set("arch", "no")
        c.save()
        text = self.path(host="new").read_text()
        self.assertTrue(text.startswith("# new: контейнеры Distrobox"), text)
        self.assertEqual(self.choice(host="new").no(), ["arch"])

    def test_unchanged_file_is_not_written(self):
        before = self.path().stat().st_mtime_ns
        c = self.choice()
        c.set("arch", "yes")
        c.save()
        self.assertEqual(self.path().stat().st_mtime_ns, before)
        self.choice(host="none").save()
        self.assertFalse(self.path(host="none").exists())

    def test_invalid_files_are_refused(self):
        for text in ('yes = ["a"]\nno = ["a"]\n', 'yes = ["a", "a"]\n', 'yes = "a"\n', "yes = [\n"):
            self.path(host="bad").parent.mkdir(exist_ok=True)
            self.path(host="bad").write_text(text)
            with self.assertRaises(ValueError, msg=text):
                self.choice(host="bad")
        with self.assertRaises(ValueError):
            self.choice(module="nothing")
        with self.assertRaises(ValueError):
            self.choice(host="bad name")

    def test_offer_asks_about_ask_and_writes_the_answer(self):
        items = [("arch", "ask", "Arch"), ("wine", "ask", ""), ("proton", "ask", ""),
                 ("t2bce-build", "no", ""), ("new", "ask", "New"), ("other", "ask", "")]
        asked = []

        def choose(offered, what, unchecked, tty):
            asked.append((offered, list(unchecked)))
            return ["new"]

        with mock.patch.object(ws_select, "choose", choose):
            self.assertEqual(ws_catalog.offer(self.choice(), items), ["new"])
            self.assertEqual(asked[-1], ([("new", "New"), ("other", "")], []))
            c = self.choice()
            self.assertEqual((c.state("new"), c.state("other")), ("yes", "no"))
            # --select: also the declined ones, unchecked.
            ws_catalog.offer(self.choice(), items, select=True)
            self.assertEqual([n for n, _ in asked[-1][0]], ["proton", "t2bce-build", "other"])
            self.assertEqual(asked[-1][1], ["proton", "t2bce-build", "other"])

    def test_cancelled_offer_writes_nothing(self):
        before = self.path().read_text()
        with mock.patch.object(ws_select, "choose", lambda *a: None):
            self.assertIsNone(ws_catalog.offer(self.choice(), [("new", "ask", "")]))
        self.assertEqual(self.path().read_text(), before)

    def test_cli(self):
        p = self.cli("boxes", "states", "arch", "proton=yes", "t2bce-build=no", "other")
        self.assertEqual(p.stdout.split("\n")[:4], ["arch yes", "proton no", "t2bce-build no", "other ask"])
        self.assertEqual(self.cli("boxes", "set", "yes", "x", "y").returncode, 0)
        self.assertEqual(self.cli("boxes", "yes").stdout.split(), ["arch", "wine", "x", "y"])
        self.assertEqual(self.cli("boxes", "chosen").stdout.split(), ["arch", "wine", "x", "y", "proton"])
        self.assertEqual(self.cli("boxes", "state", "zzz", "no").stdout, "no\n")
        p = self.cli("boxes", "set", "maybe", "x")
        self.assertEqual(p.returncode, 1)
        self.assertIn("ws_catalog: invalid state", p.stderr)

    def test_cli_offer_without_a_terminal_names_the_offered(self):
        p = self.cli("boxes", "offer", "--what", "контейнеры", "--",
                     "arch\task\t", "new\task\tNew", "t2\tno\t")
        self.assertEqual(p.returncode, ws_select.NO_TERMINAL, p.stderr)
        self.assertEqual(p.stdout.split(), ["new"])
        self.assertEqual(self.choice().state("new"), "ask")

    def test_summary(self):
        old = 'yes = ["a", "b"]\nno = ["c"]\n'
        new = 'yes = ["a", "c"]\nno = ["d"]\n'
        self.assertEqual(ws_catalog.summary(old, new), "c=yes, d=no, -b")
        self.assertEqual(ws_catalog.summary("", 'yes = ["a"]\n'), "a=yes")
        self.assertEqual(ws_catalog.summary(old, "# note\n" + old), "edited")


if __name__ == "__main__":
    unittest.main()
