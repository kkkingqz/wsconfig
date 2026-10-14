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
import flatpak_catalog  # noqa: E402
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

    def test_flatpak(self):
        old = ws_marks.MarkedList(OLD / "apps.txt", key_fields={2})
        catalog = flatpak_catalog.Catalog(ROOT)
        self.assertEqual(catalog.ids(), [line.key[1] for line in old.entries()])
        self.assertEqual([e["remote"] for e in catalog.apps()], [line.key[0] for line in old.entries()])
        self.assert_same(old, "flatpak", {a: catalog.default(a) for a in catalog.ids()})
        # The overrides of every host: the old lines that apply there.
        overrides = ws_marks.MarkedList(OLD / "overrides.txt", **ws_marks.OVERRIDES)
        for host in HOSTS:
            choice = ws_catalog.Choice("flatpak", host, ROOT)
            flatpak_catalog.check_host(choice, catalog)
            before = sorted(tuple(line.key) for line in overrides.entries()
                            if overrides.line_state(line, host) == "yes")
            after = sorted((app, kind, value) for app in catalog.ids()
                           for kind, value in flatpak_catalog.effective(catalog, choice, app))
            self.assertEqual(after, before, host)


if __name__ == "__main__":
    unittest.main()
