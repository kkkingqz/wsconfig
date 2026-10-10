from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ws_marks  # noqa: E402


class MarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "list.txt"

    def write(self, text):
        self.path.write_text(text)
        return ws_marks.MarkedList(self.path)

    def test_own_mark_wins_over_all(self):
        m = self.write("box a=no all=yes\nother a=yes all=no\nplain\n")
        self.assertEqual(m.state("box", "a"), "no")
        self.assertEqual(m.state("box", "b"), "yes")
        self.assertEqual(m.state("other", "b"), "no")
        self.assertEqual(m.state("plain", "a"), "ask")
        self.assertEqual(m.state("missing", "a"), "ask")

    def test_set_adds_line_with_all_ask_and_keeps_the_rest(self):
        m = self.write("# header\nbox a=yes all=ask  # note\n\n")
        m.set("box", "b", "no")
        m.set("new", "b", "yes", key=["flathub", "new"])
        m.save()
        self.assertEqual(self.path.read_text(),
                         "# header\nbox a=yes b=no all=ask  # note\n\nflathub new b=yes all=ask\n")

    def test_unchanged_lines_are_written_back_verbatim(self):
        text = "flathub  app   a=yes  all=ask\n"
        m = self.write(text)
        m.set("app", "a", "yes")
        m.save()
        self.assertEqual(self.path.read_text(), text)

    def test_remove_drops_line_unless_other_hosts_are_marked(self):
        m = self.write("solo a=yes all=ask\nshared a=yes b=no all=ask\n")
        self.assertEqual(m.remove("solo", "a"), "removed")
        self.assertEqual(m.remove("shared", "a"), "no")
        self.assertIsNone(m.remove("missing", "a"))
        m.save()
        self.assertEqual(self.path.read_text(), "shared a=no b=no all=ask\n")

    def test_invalid_marks_are_refused(self):
        for text in ("box a=maybe\n", "box a=yes extra\n", "box a=yes a=no\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.write(text)

    def test_workstation_name_must_fit_a_mark(self):
        m = self.write("box a=yes all=ask\n")
        for host in ("legion.go", "all", "-x", ""):
            with self.subTest(host=host), self.assertRaises(ValueError):
                m.set("box", host, "yes")
            with self.subTest(host=host), self.assertRaises(ValueError):
                m.remove("box", host)
        self.assertEqual(m.set("box", "legion-go_2", "no").render(),
                         "box a=yes legion-go_2=no all=ask")

    def test_summary_for_the_commit_message(self):
        old = self.write("a h=yes all=ask\nb h=yes all=ask\n")
        new_path = Path(self.temp.name) / "new.txt"
        new_path.write_text("a h=yes w=no all=ask\nc w=yes all=ask\n")
        new = ws_marks.MarkedList(new_path)
        self.assertEqual(ws_marks.summary(old, new), "a w=no, +c, -b")

    def test_command_line(self):
        self.write("box a=yes all=ask\n")
        run = lambda *args: subprocess.run([sys.executable, str(ROOT / "lib/ws_marks.py"), str(self.path), *args],
                                           text=True, capture_output=True)
        self.assertEqual(run("states", "b", "box", "other").stdout, "box ask\nother ask\n")
        run("set", "box", "b", "yes")
        self.assertEqual(run("state", "box", "b").stdout, "yes\n")
        self.assertEqual(run("remove", "box", "b").stdout, "no\n")
        self.assertEqual(self.path.read_text(), "box a=yes b=no all=ask\n")
        # Nothing to remove: the file is not written, a missing one not made.
        missing = Path(self.temp.name) / "missing.txt"
        p = subprocess.run([sys.executable, str(ROOT / "lib/ws_marks.py"), str(missing), "remove", "box", "b"],
                           text=True, capture_output=True)
        self.assertEqual(p.stdout, "absent\n")
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
