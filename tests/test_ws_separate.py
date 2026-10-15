"""A configuration of its own (ws help plan-v2, 8.6): no bin/ws at its root,
every tracked file is data, untracked files are named; --core PATH and
ws update core for the core it pins."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)
from ws_fixture import Workspace

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("ws-gnome", "ws-tiling-apply", "ws-keyboard-apply", "wsflatpak", "wsbox", "wswidgets")
# flake.lock of a configuration repository: it pins the core as wsconfig.
LOCK = {"nodes": {"root": {"inputs": {"wsconfig": "wsconfig", "nixpkgs": "nixpkgs"}},
                  "wsconfig": {"locked": {"rev": "a" * 40}}, "nixpkgs": {"locked": {"rev": "b" * 40}}},
        "root": "root", "version": 7}


class SeparateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Workspace(tmp.name, modules={m: "exit 0\n" for m in MODULES})
        self.w.stub("gdbus", "exit 0\n", where="bin")

    def pin_core(self):
        (self.w.repo / "flake.lock").write_text(json.dumps(LOCK))
        self.w.git("commit", "-qam", "pin the core")

    def nix_calls(self):
        return [c for c in self.w.take_calls() if c.startswith("nix ")]

    def test_apply_names_untracked_files_and_builds_nothing(self):
        (self.w.repo / "home").mkdir()
        (self.w.repo / "home/new.conf").write_text("x\n")
        self.w.take_calls()
        rc, _, err = self.w.ws("apply")
        self.assertEqual(rc, 2)
        self.assertIn("not tracked): home/new.conf", err)
        self.assertEqual(self.nix_calls(), [])
        # Not added either.
        self.assertIn("?? home/new.conf", self.w.git("status", "--porcelain", "--untracked-files=all"))

    def test_sync_commits_every_tracked_change_and_names_untracked(self):
        (self.w.repo / "apt.txt").write_text("btop\n")
        (self.w.repo / "notes.txt").write_text("x\n")
        rc, out, err = self.w.ws("sync")
        self.assertEqual(rc, 0, err)
        self.assertIn("not tracked, not published: notes.txt", out)
        self.assertEqual(self.w.git("log", "-1", "--format=%s"), "ws sync: apt.txt")
        self.assertIn("apt.txt: edited", self.w.git("log", "-1", "--format=%b"))
        self.assertEqual(self.w.git("status", "--porcelain"), "?? notes.txt")

    def test_core_needs_the_input_wsconfig(self):
        rc, _, err = self.w.ws("apply", "--core", str(self.w.core))
        self.assertEqual(rc, 1)
        self.assertIn("has no flake input wsconfig", err)

    def test_core_overrides_the_input_of_every_build(self):
        self.pin_core()
        self.w.take_calls()
        rc, out, err = self.w.ws("apply", "home", "--core", str(self.w.core))
        self.assertEqual(rc, 0, out + err)
        override = f"--override-input wsconfig path:{self.w.core}"
        calls = self.nix_calls()
        self.assertTrue(calls)
        self.assertEqual([c for c in calls if override not in c], [])
        # flake.lock stays.
        self.assertEqual(json.loads((self.w.repo / "flake.lock").read_text()), LOCK)

    def test_update_core(self):
        rc, out, _ = self.w.ws("update", "core")
        self.assertEqual(rc, 0, out)
        self.assertIn("pins no core", out)
        self.pin_core()
        self.w.take_calls()
        rc, out, err = self.w.ws("update", "core")
        self.assertEqual(rc, 0, out + err)
        self.assertIn(f"nix flake update wsconfig --flake {self.w.repo}", self.nix_calls())

    def test_update_nix_leaves_the_core(self):
        self.pin_core()
        self.w.take_calls()
        rc, out, err = self.w.ws("update", "nix")
        self.assertEqual(rc, 0, out + err)
        self.assertIn(f"nix flake update nixpkgs home-manager wswidgets --flake {self.w.repo}",
                      self.nix_calls())

    def test_new_choice_file_is_added(self):
        # The first choice of a host creates its file; ws apply adds nothing.
        p = subprocess.run(["python3", str(self.w.core / "lib/ws_catalog.py"), "flatpak", "set", "yes",
                            "org.example.A"], env=self.w.env, text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.w.git("status", "--porcelain"), "A  hosts/test/flatpak.toml")

    def test_check_repo_of_the_configuration(self):
        shutil.copy(ROOT / "libexec/ws-check-repo", self.w.core / "libexec/ws-check-repo")
        (self.w.repo / "stray.txt").write_text("x\n")
        (self.w.repo / "wsconfig.toml").write_text("schema = 7\n")
        rc, out, _ = self.w.ws("check", "repo", "--json")
        texts = [m["text"] for m in json.loads(out)["messages"]]
        self.assertTrue(any("schema 7, this core reads 1" in t for t in texts), texts)
        self.assertTrue(any("not tracked, so not in the build" in t and "stray.txt" in t for t in texts), texts)
        # The checks of code are the core checkout's.
        self.assertFalse(any("bootstrap.sh" in t for t in texts), texts)


if __name__ == "__main__":
    unittest.main()
