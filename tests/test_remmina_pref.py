"""remmina/remmina-pref.py: the keys ws switch owns in remmina.pref, every
other line kept."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "remmina/remmina-pref.py"

PREF = """[remmina_pref]
secret=abc=
rdp_quality_0=6F
rdp_quality_9=80
recent_RDP=192.168.113.113

[ssh_colors]
background=rgb(213,204,186)

[remmina]
name=
ignore-tls-errors=1
"""

WANTED = ["remmina.quality=9", "remmina.colordepth=99", "remmina.network=autodetect",
          "remmina_pref.rdp_quality_9=180"]


class RemminaPrefTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "remmina/remmina.pref"

    def run_pref(self, *args):
        p = subprocess.run([sys.executable, str(SCRIPT), str(self.path), *args],
                           text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_sets_the_keys_and_keeps_the_rest(self):
        self.path.parent.mkdir()
        self.path.write_text(PREF)
        out = self.run_pref(*WANTED)
        self.assertEqual(self.path.read_text(), PREF.replace(
            "rdp_quality_9=80", "rdp_quality_9=180").replace(
            "ignore-tls-errors=1\n",
            "ignore-tls-errors=1\nquality=9\ncolordepth=99\nnetwork=autodetect\n"))
        self.assertIn("remmina.pref: [remmina_pref] rdp_quality_9=180 (was 80)", out)
        self.assertIn("remmina.pref: [remmina] quality=9", out)

    def test_second_run_changes_nothing(self):
        self.path.parent.mkdir()
        self.path.write_text(PREF)
        self.run_pref(*WANTED)
        before = self.path.stat().st_mtime_ns, self.path.read_text()
        self.assertEqual(self.run_pref(*WANTED), "")
        self.assertEqual((self.path.stat().st_mtime_ns, self.path.read_text()), before)

    def test_missing_file_and_groups_are_created(self):
        self.run_pref(*WANTED)
        self.assertEqual(self.path.read_text(),
                         "[remmina]\nquality=9\ncolordepth=99\nnetwork=autodetect\n\n"
                         "[remmina_pref]\nrdp_quality_9=180\n")

    def test_key_goes_before_the_blank_line_of_its_group(self):
        self.path.parent.mkdir()
        self.path.write_text("[remmina_pref]\nsecret=x\n\n[remmina]\nname=\n")
        self.run_pref("remmina_pref.rdp_quality_9=180")
        self.assertEqual(self.path.read_text(),
                         "[remmina_pref]\nsecret=x\nrdp_quality_9=180\n\n[remmina]\nname=\n")

    def test_same_key_in_another_group_is_not_touched(self):
        self.path.parent.mkdir()
        self.path.write_text("[other]\nquality=0\n[remmina]\nquality=0\n")
        self.run_pref("remmina.quality=9")
        self.assertEqual(self.path.read_text(), "[other]\nquality=0\n[remmina]\nquality=9\n")

    def test_bad_argument_is_refused(self):
        p = subprocess.run([sys.executable, str(SCRIPT), str(self.path), "quality=9"],
                           text=True, capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("GROUP.KEY=VALUE", p.stderr)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
