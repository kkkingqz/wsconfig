"""libexec/ws-clean (ws help clean, ws help plan-v2, 11.5) with nix-env,
nix-store, nix, podman and flatpak replaced by tests/fixtures/bin/clean-stub
and gum by tests/fixtures/bin/gum."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "libexec/ws-clean"
STUB = ROOT / "tests/fixtures/bin/clean-stub"
NOW = time.mktime(time.strptime("2026-10-15 12:00:00", "%Y-%m-%d %H:%M:%S"))
PROFILE_LINK = "/state/nix/profiles/home-manager-{}-link"
FLATPAK = """These runtimes in installation 'user' are not used by installed apps:

        ID                                   Branch    Op
 1.     org.gnome.Platform                   45        r
 2.     org.freedesktop.Platform.GL.default  23.08     r

Proceed with these changes to the user installation? [Y/n]: n
"""


class CleanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = root = Path(tmp.name)
        self.bin = root / "bin"
        self.bin.mkdir()
        (self.bin / "python3").symlink_to(sys.executable)
        for name in ("nix-env", "nix-store", "nix", "podman", "flatpak"):
            (self.bin / name).symlink_to(STUB)
        state = root / "state"
        (state / "nix/profiles").mkdir(parents=True)
        (state / "nix/profiles/home-manager").symlink_to("home-manager-3-link")
        self.links = {n: str(state / f"nix/profiles/home-manager-{n}-link") for n in (1, 2, 3)}
        self.fixture = {
            "generations": ("   1   2026-09-01 10:00:00   \n   2   2026-10-10 10:00:00   \n"
                            "   3   2026-10-15 10:00:00   (current)\n"),
            "dead": ["/nix/store/dead-a", "/nix/store/x.lock"],
            "roots": {self.links[1]: "/nix/store/gen-1", self.links[2]: "/nix/store/gen-2",
                      self.links[3]: "/nix/store/gen-3", "/cp/home": "/nix/store/gen-cp"},
            "closure": {"/nix/store/gen-1": ["/nix/store/gen-1", "/nix/store/old-lib", "/nix/store/lib"],
                        "/nix/store/gen-3": ["/nix/store/gen-3", "/nix/store/lib"]},
            "sizes": {"/nix/store/dead-a": 1000, "/nix/store/gen-1": 2000, "/nix/store/old-lib": 4000},
            "images": [{"Id": "a" * 64, "Names": ["docker.io/library/archlinux:latest"], "Size": 300, "Containers": 2},
                       {"Id": "b" * 64, "Names": None, "Size": 100, "Containers": 0},
                       {"Id": "c" * 64, "Names": ["localhost/sp-test:latest"], "Size": 200, "Containers": 0}],
            "containers": [{"Names": ["arch"], "ImageID": "a" * 12}],
            "flatpak": FLATPAK,
        }
        self.log = root / "log"
        self.env = {"PATH": str(self.bin), "HOME": str(root), "XDG_STATE_HOME": str(state),
                    "CLEAN_FIXTURE": str(root / "fixture.json"), "CLEAN_LOG": str(self.log),
                    "WS_CLEAN_NOW": str(NOW), "WS_GUM": str(ROOT / "tests/fixtures/bin/gum"),
                    "WS_GUM_ANSWERS": str(root / "answers"), "WS_GUM_LOG": str(root / "gum-log")}

    def clean(self, *args, tty=False, answers=()):
        (self.root / "fixture.json").write_text(json.dumps(self.fixture))
        (self.root / "answers").write_text("".join(json.dumps(a) + "\n" for a in answers))
        env = self.env | ({"WS_UI_TTY": "/dev/null"} if tty else {})
        return subprocess.run([sys.executable, str(CLEAN), *args], env=env, text=True,
                              capture_output=True, stdin=subprocess.DEVNULL)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def removals(self):
        return [c for c in self.calls() if "--delete-generations" in c or c[:2] == ["podman", "rmi"]
                or c == ["nix-store", "--gc"] or (c[0] == "flatpak" and "-y" in c)]

    def test_dry_run_plans_and_removes_nothing(self):
        p = self.clean("--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("== nix: 1, 6.8 KiB", p.stdout)
        self.assertIn("home-manager generation 1 (2026-09-01)", p.stdout)
        self.assertNotIn("generation 2 ", p.stdout)
        self.assertIn("== podman: 2, 300 B", p.stdout)
        self.assertIn("bbbbbbbbbbbb  <none>  100 B", p.stdout)
        self.assertIn("cccccccccccc  localhost/sp-test:latest", p.stdout)
        self.assertNotIn("archlinux", p.stdout)
        self.assertIn("org.gnome.Platform//45", p.stdout)
        self.assertEqual(self.removals(), [])
        # flatpak was answered no.
        self.assertIn(["flatpak", "uninstall", "--user", "--unused"], self.calls())

    def test_keep_days(self):
        p = self.clean("--dry-run", "--keep-days", "0", "nix")
        self.assertIn("generation 2 (2026-10-10)", p.stdout)
        self.assertNotIn("generation 3", p.stdout)
        p = self.clean("--dry-run", "--keep-days", "60", "nix")
        self.assertIn("== nix: 1, 1000 B", p.stdout)
        self.assertIn("store paths no root keeps", p.stdout)
        self.assertEqual(self.clean("--keep-days", "x").returncode, 64)

    def test_yes_needs_scopes_and_no_terminal_needs_yes(self):
        self.assertEqual(self.clean("--yes").returncode, 64)
        p = self.clean("nix")
        self.assertEqual(p.returncode, 1)
        self.assertIn("no terminal to ask: ws clean --yes SCOPE", p.stderr)
        self.assertEqual(self.removals(), [])

    def test_yes_removes_exactly_the_plan(self):
        p = self.clean("--yes", "nix", "podman", "flatpak")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.removals(), [
            ["nix-env", "--profile", str(Path(self.env["XDG_STATE_HOME"]) / "nix/profiles/home-manager"),
             "--delete-generations", "1"],
            ["nix-store", "--gc"],
            ["podman", "rmi", "b" * 64], ["podman", "rmi", "c" * 64],
            ["flatpak", "uninstall", "--user", "--unused", "--noninteractive", "-y"]])
        self.assertIn("OK    nix: 1 generations removed; 3 store paths deleted, 1.00 MiB freed", p.stdout)
        self.assertIn("OK    podman: 2 images removed", p.stdout)

    def test_changed_plan_is_skipped_with_yes(self):
        self.fixture["containers@2"] = self.fixture["containers"] + [{"Names": ["new"], "ImageID": "c" * 12}]
        p = self.clean("--yes", "podman")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("podman: the plan changed", p.stdout)
        self.assertIn("SKIP  podman: the plan changed; ws clean again", p.stdout)
        self.assertEqual(self.removals(), [])

    def test_choice_and_confirmation(self):
        # The default of the confirmation is no.
        p = self.clean("podman", tty=True)
        self.assertIn("nothing removed", p.stdout)
        self.assertEqual(self.removals(), [])
        # Yes: only the chosen scope.
        p = self.clean(tty=True, answers=[["podman"], []])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual([c[:2] for c in self.removals()], [["podman", "rmi"], ["podman", "rmi"]])
        # Esc on the choice: nothing.
        self.log.unlink()
        p = self.clean(tty=True, answers=["esc"])
        self.assertIn("nothing removed", p.stdout)
        self.assertEqual(self.removals(), [])

    def test_missing_tools_are_named(self):
        for name in ("podman", "flatpak"):
            (self.bin / name).unlink()
        p = self.clean("--dry-run")
        self.assertIn("== podman: not here (no podman)", p.stdout)
        self.assertIn("== flatpak: not here (no flatpak)", p.stdout)


if __name__ == "__main__":
    unittest.main()
