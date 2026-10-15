"""lib/ws_template.py and template/ (ws help plan-v2, 9.7): a new
configuration from the template, its flake.lock from the lock of the core;
tests/config builds the same files (links into template/)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ws_template  # noqa: E402

LOCKED = {"lastModified": 1, "narHash": "sha256-x", "owner": "kkkingqz", "repo": "wsconfig",
          "rev": "c" * 40, "type": "github"}


class TemplateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.meta = self.tmp / "meta.json"
        # As nix flake metadata --json prints it.
        self.meta.write_text(json.dumps({"locked": LOCKED | {"__final": True}, "url": "github:x"}))

    def test_lock_pins_the_core_and_its_inputs(self):
        core = json.loads((ROOT / "flake.lock").read_text())
        lock = ws_template.lock(core, LOCKED)
        inputs = sorted(core["nodes"][core["root"]]["inputs"])
        self.assertEqual(lock["nodes"]["root"]["inputs"],
                         {name: name for name in inputs + ["wsconfig"]})
        self.assertEqual(lock["nodes"]["wsconfig"], {
            "inputs": {name: [name] for name in inputs}, "locked": LOCKED,
            "original": {"owner": "kkkingqz", "repo": "wsconfig", "type": "github"}})
        for name in inputs:
            self.assertEqual(lock["nodes"][name], core["nodes"][name])

    def test_the_follows_of_template_flake_nix(self):
        # Every input of the core follows the input of the same name.
        text = (ROOT / "template/flake.nix").read_text()
        core = json.loads((ROOT / "flake.lock").read_text())
        for name in core["nodes"][core["root"]]["inputs"]:
            self.assertIn(f'inputs.{name}.follows = "{name}";', text)

    def test_new(self):
        target = ws_template.new(ROOT, self.meta, self.tmp / "cfg")
        self.assertTrue((target / "hosts").is_dir())
        self.assertEqual((target / "flatpak/catalog.toml").read_text(),
                         (ROOT / "template/flatpak/catalog.toml").read_text())
        self.assertEqual(json.loads((target / "flake.lock").read_text())["nodes"]["wsconfig"]["locked"], LOCKED)
        self.assertFalse(any(p.is_symlink() for p in target.rglob("*")))
        with self.assertRaises(SystemExit):
            ws_template.new(ROOT, self.meta, target)

    def test_cli(self):
        p = subprocess.run([sys.executable, str(ROOT / "lib/ws_template.py"), "new", "--core", str(ROOT),
                            "--metadata", str(self.meta), str(self.tmp / "c2")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.tmp / "c2/flake.nix").exists())

    def test_tests_config_is_the_template(self):
        # The shared files of tests/config are links into template/: the
        # checks build what --new gives.
        for name in ("apt.txt", "wsconfig.toml", "distrobox", "flatpak", "gnome", "keyboard",
                     "terminal", "windows"):
            link = ROOT / "tests/config" / name
            self.assertTrue(link.is_symlink(), name)
            self.assertEqual(os.readlink(link), f"../../template/{name}")


if __name__ == "__main__":
    unittest.main()
