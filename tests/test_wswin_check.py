"""wswin check follows the box marks of distrobox/hosts.txt: the launchers
of windows/apps.nix exist only where the box is marked yes, so programs and
the .exe default of other boxes are not checked."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]


class WswinCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "distrobox").mkdir()
        (root / "windows").mkdir()
        (root / "distrobox/boxes.ini").write_text(
            "[here]\nprofile=wine\n\n[elsewhere]\nprofile=wine\n")
        (root / "windows/apps.ini").write_text(
            "[wswin]\ndefault_box=elsewhere\n\n"
            "[local]\nbox=here\nprefix=default\nexe=drive_c/local.exe\n\n"
            "[remote]\nbox=elsewhere\nprefix=default\nexe=drive_c/remote.exe\n")
        self.hosts = root / "hosts.txt"
        self.hosts.write_text("here test=yes all=ask\nelsewhere other=yes all=ask\n")
        self.env = dict(os.environ, HOME=str(root), WSWIN_DATA=str(root),
                        WSBOX_HOSTS=str(self.hosts), WS_HOST="test")

    def check(self):
        return subprocess.run([str(ROOT / "bin/wswin-check")], env=self.env,
                              text=True, capture_output=True).stdout

    def test_only_boxes_marked_yes_are_checked(self):
        out = self.check()
        self.assertIn("WARN  app local: not installed", out)
        self.assertIn("INFO  app remote: box elsewhere is not on test, no launcher", out)
        self.assertNotIn("app remote: not installed", out)
        self.assertIn("INFO  .exe: default box elsewhere is not on test", out)

    def test_unreadable_marks_fail(self):
        self.hosts.write_text("here test=maybe\n")
        self.assertIn("FAIL  workstation marks of", self.check())


if __name__ == "__main__":
    unittest.main()
