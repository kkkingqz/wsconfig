import contextlib
import io
import os
from pathlib import Path
import pty
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import ws_select  # noqa: E402

ITEMS = [("a.App", "flathub"), ("b.App", "flathub"), ("c.App", "other")]
DOWN = "\x1b[B"


class ChooseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "layer/skipped"

    def choose(self, keys, items=ITEMS, reselect=False):
        """Run choose() on a pseudo terminal; KEYS are typed one chunk at
        a time (an arrow key must arrive as one chunk)."""
        master, slave = pty.openpty()
        output = []

        def drain():
            while True:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    return
                if not data:
                    return
                output.append(data)

        def type_keys():
            for chunk in keys:
                time.sleep(0.02)
                os.write(master, chunk.encode())

        reader = threading.Thread(target=drain, daemon=True)
        typist = threading.Thread(target=type_keys, daemon=True)
        reader.start()
        typist.start()
        try:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                result = ws_select.choose(items, self.state, "x apply --select",
                                          "тест", reselect, tty=slave)
            typist.join()
        finally:
            os.close(slave)
            os.close(master)
        self.err = err.getvalue()
        self.screen = b"".join(output).decode(errors="replace")
        return result

    def skipped(self):
        return ws_select.read_skipped(self.state)

    def test_enter_installs_all(self):
        self.assertEqual(self.choose(["\n"]), ["a.App", "b.App", "c.App"])
        self.assertIn("Поставить все? [Y/n]", self.screen)
        self.assertFalse(self.state.exists())

    def test_space_unchecks_and_remembers(self):
        result = self.choose(["n\n", DOWN, " ", "\n"])
        self.assertEqual(result, ["a.App", "c.App"])
        self.assertEqual(self.skipped(), ["b.App"])
        self.assertIn("[x] a.App", self.screen)

    def test_toggle_all_off_then_one_on(self):
        result = self.choose(["n\n", "a", DOWN, DOWN, " ", "\n"])
        self.assertEqual(result, ["c.App"])
        self.assertEqual(self.skipped(), ["a.App", "b.App"])

    def test_escape_cancels_without_state(self):
        self.assertIsNone(self.choose(["n\n", " ", "\x1b"]))
        self.assertFalse(self.state.exists())

    def test_skipped_are_not_asked_again(self):
        ws_select.write_skipped(self.state, ["b.App"])
        self.assertEqual(self.choose(["\n"]), ["a.App", "c.App"])
        self.assertNotIn("b.App", self.screen)
        self.assertIn("b.App", self.err)
        self.assertEqual(self.skipped(), ["b.App"])

    def test_nothing_to_ask_needs_no_terminal(self):
        ws_select.write_skipped(self.state, ["a.App", "b.App", "c.App"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ws_select.choose(ITEMS, self.state, "x", "тест",
                                              tty=-1), [])

    def test_reselect_starts_skipped_unchecked(self):
        ws_select.write_skipped(self.state, ["b.App"])
        result = self.choose(["n\n", "\n"], reselect=True)
        self.assertEqual(result, ["a.App", "c.App"])
        self.assertIn("[ ] b.App", self.screen)
        result = self.choose(["y\n"], reselect=True)
        self.assertEqual(result, ["a.App", "b.App", "c.App"])
        self.assertFalse(self.state.exists())

    def test_skip_of_item_no_longer_missing_is_dropped(self):
        ws_select.write_skipped(self.state, ["gone.App", "b.App"])
        self.choose(["\n"])
        self.assertEqual(self.skipped(), ["b.App"])

    def test_without_terminal_all_but_skipped(self):
        ws_select.write_skipped(self.state, ["c.App"])
        with mock.patch.object(ws_select, "open_tty", return_value=None), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ws_select.choose(ITEMS, self.state, "x", "тест"),
                             ["a.App", "b.App"])

    def test_unskip(self):
        ws_select.write_skipped(self.state, ["a.App", "b.App"])
        ws_select.unskip(self.state, ["a.App"])
        self.assertEqual(self.skipped(), ["b.App"])


if __name__ == "__main__":
    unittest.main()
