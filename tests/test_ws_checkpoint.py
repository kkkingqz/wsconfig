"""ws checkpoint show: the way back by what meta.txt recorded (ws help
plan-v2, 8.7): a configuration of its own with the pinned core or --core,
and checkpoints from before the split."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
BASE = "name: {name}\ndate: 2026-10-15T10:00:00+03:00\ncommit: {commit}\nkernel: k\n"


class CheckpointShowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = self.root / "config"
        self.config.mkdir()
        (self.config / "wsconfig.toml").write_text("schema = 1\n")
        self.state = self.root / "state"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("WS", "GIT_"))}
        self.env.update(WSCONFIG=str(self.config), WS_STATE=str(self.state), HOME=str(self.root))

    def checkpoint(self, name, extra=""):
        d = self.state / "checkpoints" / name
        d.mkdir(parents=True)
        (d / "meta.txt").write_text(BASE.format(name=name, commit="1" * 40) + extra)

    def show(self, name):
        p = subprocess.run([str(ROOT / "libexec/ws-checkpoint"), "show", name], env=self.env,
                           text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_pinned_core(self):
        self.checkpoint("a", f"config: {self.config}\ncore: {'2' * 40}\n")
        out = self.show("a")
        self.assertIn(f"git -C {self.config} switch --detach checkpoint/a", out)
        self.assertIn("its flake.lock pins the core", out)

    def test_core_path(self):
        self.checkpoint("b", f"config: {self.config}\ncore: {'2' * 40}\ncore-path: /src/core\n")
        out = self.show("b")
        self.assertIn(f"git -C /src/core switch --detach {'2' * 12}", out)
        self.assertIn("ws apply --core /src/core", out)

    def test_from_before_the_split(self):
        # The configuration is one of its own now (no bin/ws at its root).
        self.checkpoint("c")
        out = self.show("c")
        self.assertIn("Recorded before code and data were separate repositories", out)
        self.assertIn("CHECKOUT/bin/ws apply", out)


if __name__ == "__main__":
    unittest.main()
