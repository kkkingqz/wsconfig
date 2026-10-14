"""wswin check follows the host choice of the boxes (nix/hosts/HOST/
boxes.toml, else the default of the box): the launchers of windows/apps.nix
exist only where the box is yes, so programs and the .exe default of other
boxes are not checked."""
import json
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
        (root / "distrobox/boxes.json").write_text(
            '[{"name": "here", "profile": "wine"}, {"name": "elsewhere", "profile": "wine"},'
            ' {"name": "everywhere", "profile": "wine", "default": "yes"}]')
        (root / "windows/apps.json").write_text(json.dumps({"default_box": "elsewhere", "apps": {
            "local": {"box": "here", "prefix": "default", "exe": "drive_c/local.exe"},
            "remote": {"box": "elsewhere", "prefix": "default", "exe": "drive_c/remote.exe"},
            "all": {"box": "everywhere", "prefix": "default", "exe": "drive_c/all.exe"}}}))
        for host in ("test", "other"):
            (root / "config/nix/hosts" / host).mkdir(parents=True)
        self.hosts = root / "config/nix/hosts/test/boxes.toml"
        self.hosts.write_text('yes = ["here"]\n')
        (root / "config/nix/hosts/other/boxes.toml").write_text('yes = ["elsewhere"]\n')
        self.env = dict(os.environ, HOME=str(root), WSWIN_DATA=str(root),
                        WSCONFIG=str(root / "config"), WS_HOST="test")

    def check(self):
        return subprocess.run([str(ROOT / "libexec/wswin-check")], env=self.env,
                              text=True, capture_output=True).stdout

    def test_only_boxes_marked_yes_are_checked(self):
        out = self.check()
        self.assertIn("WARN  app local: not installed", out)
        self.assertIn("INFO  app remote: box elsewhere is not on test, no launcher", out)
        self.assertNotIn("app remote: not installed", out)
        self.assertIn("INFO  .exe: default box elsewhere is not on test", out)
        # The default yes of a box counts as yes.
        self.assertIn("WARN  app all: not installed", out)

    def test_unreadable_choice_fails(self):
        self.hosts.write_text('yes = "here"\n')
        self.assertIn("FAIL  host choice of the boxes", self.check())


if __name__ == "__main__":
    unittest.main()
