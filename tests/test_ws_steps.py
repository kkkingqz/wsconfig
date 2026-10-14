"""ws apply, update and check walk their step tables the same way
(helpws plan-v2, 2.5): names, selection, header, summary."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

APPLY = {"ws-gnome": 0, "ws-tiling-apply": 69, "ws-keyboard-apply": 3,
         "wsflatpak": 0, "wsbox": 0, "wswidgets": 0}
CHECK = ["ws-check-repo", "ws-check-home", "ws-keyboard", "ws-gnome", "wsflatpak", "wsbox", "wswin",
         "ws-suspend", "wsgame", "ws-workstation-verify"]


class StepsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        (self.repo / "bin").mkdir(parents=True)
        shutil.copytree(ROOT / "lib", self.repo / "lib", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / "bin/ws", self.repo / "bin/ws")
        shutil.copyfile(ROOT / ".gitignore", self.repo / ".gitignore")
        # The catalogs ws apply asks about first: nothing to ask.
        (self.repo / "flatpak").mkdir()
        (self.repo / "flatpak/catalog.toml").write_text("[remotes]\n")
        for name, rc in APPLY.items():
            self.stub(name, f'echo "{name} $*"\n[ "$1" = check ] && exit 0\nexit {rc}\n')
        result = json.dumps({"status": "warn", "passes": 1, "warnings": 1, "failures": 0,
                             "messages": [{"level": "warn", "text": "w"}]})
        for name in CHECK:
            if name not in APPLY:
                self.stub(name, f"echo '{result}'\n")
        for name in ("wsflatpak", "wsbox"):
            self.stub(name, f'case "$1" in check) echo \'{result}\' ;; *) echo "{name} $*" ;; esac\n')
        git = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", "init"], check=True)

    def stub(self, name, body):
        p = self.repo / "bin" / name
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(0o755)

    def ws(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("WS")}
        env.update(WS_HOST="test", HOME=str(self.repo.parent))
        p = subprocess.run([str(self.repo / "bin/ws"), *args], text=True, capture_output=True, env=env,
                           stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout, p.stderr

    def test_apply_all(self):
        rc, out, _ = self.ws("apply")
        self.assertEqual(rc, 1)
        self.assertEqual(out, """
=== choices: ws_catalog offer --all flatpak boxes widgets

=== extensions: ws-gnome extensions
ws-gnome extensions

=== tiling: ws-tiling-apply
ws-tiling-apply 

=== keyboard: ws-keyboard-apply
ws-keyboard-apply 

=== flatpak: wsflatpak apply
wsflatpak apply

=== distrobox: wsbox apply
wsbox apply

=== widgets: wswidgets apply
wswidgets apply

=== ws apply
  OK        choices
  OK        extensions
  PREFLIGHT tiling (log out and in, then: ws apply tiling)
  FAIL      keyboard (exit 3)
  OK        flatpak
  OK        distrobox
  OK        widgets
""")

    def test_apply_selected_in_table_order(self):
        rc, out, _ = self.ws("apply", "widgets", "extensions")
        self.assertEqual(rc, 0)
        self.assertEqual([l for l in out.splitlines() if l.startswith("===")],
                         ["=== choices: ws_catalog offer --all widgets",
                          "=== extensions: ws-gnome extensions", "=== widgets: wswidgets apply",
                          "=== ws apply"])

    def test_steps_ask_nothing_after_the_choices(self):
        self.stub("wsflatpak", 'echo "offered=${WS_OFFERED:-}"\n')
        rc, out, _ = self.ws("apply", "flatpak")
        self.assertIn("offered=1", out)
        rc, out, _ = self.ws("apply", "keyboard")
        self.assertNotIn("choices", out)

    def test_unknown_step(self):
        for kind in ("apply", "update"):
            rc, out, err = self.ws(kind, "nosuch")
            self.assertEqual((rc, out, err), (1, "", f"ws: unknown {kind} step: nosuch\n"))

    def test_check_summary(self):
        rc, out, _ = self.ws("check")
        lines = out.splitlines()
        self.assertIn("=== repo: ws-check-repo (exit 0)", lines)
        self.assertIn("  WARN  w", lines)
        tail = lines[lines.index("=== ws check"):]
        self.assertEqual(tail[1], "  WARN  repo (1)")
        self.assertRegex(tail[-1], r"^  FAIL=\d+ WARN=\d+$")

    def test_steps_lists(self):
        self.assertEqual(self.ws("steps", "apply")[1].split(),
                         ["extensions", "tiling", "keyboard", "flatpak", "distrobox", "widgets"])


if __name__ == "__main__":
    unittest.main()
