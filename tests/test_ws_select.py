import os
from pathlib import Path
import pty
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import ws_select  # noqa: E402

ITEMS = [("a.App", "flathub"), ("b.App", "flathub"), ("c.App", "other")]
DOWN = "\x1b[B"


class ChooseTests(unittest.TestCase):
    def choose(self, keys, items=ITEMS, unchecked=()):
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
            result = ws_select.choose(items, "тест", unchecked, tty=slave)
            typist.join()
        finally:
            # Closing the slave ends the reader (EIO) once it has read
            # everything; the master goes last.
            os.close(slave)
            reader.join(timeout=5)
            os.close(master)
        self.screen = b"".join(output).decode(errors="replace")
        return result

    def test_enter_installs_all(self):
        self.assertEqual(self.choose(["\n"]), ["a.App", "b.App", "c.App"])
        self.assertIn("Поставить все? [Y/n]", self.screen)

    def test_space_unchecks(self):
        self.assertEqual(self.choose(["n\n", DOWN, " ", "\n"]), ["a.App", "c.App"])
        self.assertIn("[x] a.App", self.screen)

    def test_arrows_in_application_cursor_mode(self):
        # ESC O B (SS3), as a terminal in application cursor mode sends it.
        self.assertEqual(self.choose(["n\n", "\x1bOB", " ", "\x1bOA", " ", "\n"]), ["c.App"])

    def test_toggle_all_off_then_one_on(self):
        self.assertEqual(self.choose(["n\n", "a", DOWN, DOWN, " ", "\n"]), ["c.App"])

    def test_russian_layout_letters(self):
        # ф and й are the a and q keys in the ЙЦУКЕН layout.
        self.assertEqual(self.choose(["n\n", "ф", DOWN, DOWN, " ", "\n"]), ["c.App"])
        self.assertIsNone(self.choose(["n\n", "й"]))

    def test_escape_cancels(self):
        self.assertIsNone(self.choose(["n\n", " ", "\x1b"]))

    def test_declined_start_unchecked(self):
        self.assertEqual(self.choose(["n\n", "\n"], unchecked={"b.App"}), ["a.App", "c.App"])
        self.assertIn("[ ] b.App", self.screen)
        self.assertIn("(отказались)", self.screen)

    def test_nothing_to_ask_needs_no_terminal(self):
        self.assertEqual(ws_select.choose([], "тест", tty=-1), [])

    def test_without_terminal(self):
        with mock.patch.object(ws_select, "open_tty", return_value=None):
            with self.assertRaises(ws_select.NoTerminal):
                ws_select.choose(ITEMS, "тест")


if __name__ == "__main__":
    unittest.main()
