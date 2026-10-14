"""The conversion of the workstation marks into the host choices (helpws
plan-v2, stage 3): every host of nix/hosts has the same state of every
position as in the old list (tests/fixtures/marks, the files as they were
before; tests/convert_marks.py converted them). Goes with ws_marks in 3.5."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

import convert_marks  # noqa: E402
import setup_marks  # noqa: E402
import ws_catalog  # noqa: E402
import ws_marks  # noqa: E402

OLD = ROOT / "tests/fixtures/marks"
HOSTS = ["legiongo", "mbp16", "wsgnomebox", "wsvm"]


class ConversionTests(unittest.TestCase):
    def assert_same(self, old, module, defaults):
        self.assertEqual(convert_marks.hosts(ROOT), HOSTS)
        bad = convert_marks.check(ROOT, old, module, defaults, HOSTS)
        self.assertEqual(bad, [])

    def test_widgets(self):
        old = ws_marks.MarkedList(OLD / "widgets.txt")
        # The widget catalog is the pinned wswidgets: every default is ask.
        self.assert_same(old, "widgets", {line.key[-1]: "ask" for line in old.entries()})
        # The panel order is the order of the old lines.
        self.assertEqual(ws_catalog.Choice("widgets", "mbp16", ROOT).yes(), ["example", "compact"])

    def test_boxes(self):
        old = ws_marks.MarkedList(OLD / "hosts.txt")
        # The defaults are in distrobox.nix now (setup_marks reads them).
        defaults = dict(setup_marks.box_catalog(ROOT))
        self.assertEqual(sorted(defaults), sorted(line.key[-1] for line in old.entries()))
        self.assert_same(old, "boxes", defaults)


if __name__ == "__main__":
    unittest.main()
