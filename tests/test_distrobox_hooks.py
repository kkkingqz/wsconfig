"""distrobox/arch/wsbox-host-ntsync/install-hook: run by sh from a copy
(ws help plan-v2, stage 5); the build user is its argument, not the owner of
its files."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "distrobox/arch/wsbox-host-ntsync"


class NtsyncHookTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        # A copy without the executable bit, as in ~/.local/share/wsconfig/hooks.
        self.copy = self.root / "hooks/wsbox-host-ntsync"
        shutil.copytree(HOOK, self.copy)
        (self.copy / "install-hook").chmod(0o644)
        self.calls = self.root / "calls"
        stubs = self.root / "bin"
        stubs.mkdir()
        for name, body in {
            "pacman": 'echo "pacman $*" >> "$CALLS"; [ "$1" != -Q ] || [ -n "$INSTALLED" ]\n',
            "runuser": 'echo "runuser $1 $2" >> "$CALLS"\n',
            "chown": 'echo "chown $2" >> "$CALLS"\n',
            "stat": 'echo "stat" >> "$CALLS"; exit 1\n',
        }.items():
            (stubs / name).write_text("#!/bin/sh\n" + body)
            (stubs / name).chmod(0o755)
        self.env = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}", "CALLS": str(self.calls)}

    def hook(self, *args, **env):
        return subprocess.run(["sh", str(self.copy / "install-hook"), *args], text=True,
                              capture_output=True, env={**self.env, **env})

    def calls_made(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_builds_as_the_given_user(self):
        p = self.hook("king", INSTALLED="")
        self.assertEqual(p.returncode, 0, p.stderr)
        calls = self.calls_made()
        self.assertIn("runuser -u king", calls)
        self.assertIn("chown king", calls)
        self.assertNotIn("stat", calls)
        self.assertTrue(calls[-1].startswith("pacman -U --noconfirm "), calls)

    def test_nothing_once_installed(self):
        p = self.hook("king", INSTALLED="1")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.calls_made(), ["pacman -Q wsbox-host-ntsync"])

    def test_pkgbuild_checksum_matches_the_readme(self):
        # makepkg refuses a source with another sum (ws box check reports it).
        import hashlib
        readme = hashlib.sha256((HOOK / "README.md").read_bytes()).hexdigest()
        self.assertIn(f'sha256sums=("{readme}")', (HOOK / "PKGBUILD").read_text())

    def test_user_is_required(self):
        p = self.hook(INSTALLED="")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("usage: install-hook USER", p.stderr)


if __name__ == "__main__":
    unittest.main()
