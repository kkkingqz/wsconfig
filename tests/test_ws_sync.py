"""ws sync: the only commit and push of the data files (ws help plan-v2, 2.7),
in a configuration of its own (8.11)."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = '[remotes]\nflathub = "https://example.org"\n\n[[apps]]\nid = "org.example.A"\nremote = "flathub"\n'
APP_B = '\n[[apps]]\nid = "org.example.B"\nremote = "flathub"\n'
IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t"}


class SyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("WS", "GIT_"))}
        self.env.update(IDENTITY, HOME=str(self.root), GIT_CONFIG_GLOBAL=str(self.root / "gitconfig"),
                        GIT_CONFIG_NOSYSTEM="1")
        (self.root / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n[pull]\n\trebase = true\n")
        # The core apart, the configuration a repository of its own.
        self.core = self.root / "core"
        (self.core / "bin").mkdir(parents=True)
        shutil.copy(ROOT / "bin/ws", self.core / "bin/ws")
        shutil.copytree(ROOT / "lib", self.core / "lib", ignore=shutil.ignore_patterns("__pycache__"))
        self.repo = self.root / "repo"
        (self.repo / "flatpak").mkdir(parents=True)
        self.env["WSCONFIG"] = str(self.repo)
        (self.repo / "flatpak/catalog.toml").write_text(CATALOG)
        (self.repo / "wsconfig.toml").write_text("schema = 1\n")
        (self.repo / "flake.lock").write_text('{"nodes": {"nixpkgs": {"locked": {"rev": "a"}}, "root": {}}}\n')
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "init")

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.repo), *args], env=self.env, check=True,
                              text=True, capture_output=True).stdout.strip()

    def ws(self, *args):
        return subprocess.run([str(self.core / "bin/ws"), "sync", *args], env=self.env, text=True,
                              capture_output=True, stdin=subprocess.DEVNULL)

    def with_upstream(self):
        origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], env=self.env, check=True)
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "-u", "origin", "main")
        return origin

    def edit_apps(self):
        (self.repo / "flatpak/catalog.toml").write_text(CATALOG + APP_B)

    def test_no_remote_commits_locally(self):
        self.edit_apps()
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("no remote: the commit stays local", p.stdout)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "ws sync: flatpak/catalog.toml")
        self.assertIn("flatpak/catalog.toml: +org.example.B", self.git("log", "-1", "--format=%b"))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_upstream_pull_rebase_and_push(self):
        origin = self.with_upstream()
        # Someone else published meanwhile.
        other = self.root / "other"
        subprocess.run(["git", "clone", "-q", str(origin), str(other)], env=self.env, check=True)
        (other / "README").write_text("x\n")
        self.git("add", "README", cwd=other)
        self.git("commit", "-qm", "other", cwd=other)
        self.git("push", "-q", cwd=other)
        self.edit_apps()
        (self.repo / "flake.lock").write_text('{"nodes": {"nixpkgs": {"locked": {"rev": "b"}}, "root": {}}}\n')
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("pushed to origin/main", p.stdout)
        log = self.git("log", "--format=%s", "origin/main")
        self.assertEqual(log.splitlines()[:2], ["ws sync: flake.lock flatpak/catalog.toml", "other"])
        self.assertIn("flake.lock: nixpkgs", self.git("log", "-1", "--format=%b"))

    def test_remote_without_upstream_commits_locally(self):
        origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], env=self.env, check=True)
        self.git("remote", "add", "origin", str(origin))
        self.edit_apps()
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("no upstream for main", p.stdout)
        self.assertIn("push -u origin main", p.stdout)

    def test_dry_run_changes_nothing(self):
        self.with_upstream()
        self.edit_apps()
        head = self.git("rev-parse", "HEAD")
        p = self.ws("--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("would commit: ws sync: flatpak/catalog.toml", p.stdout)
        self.assertIn("would run: git pull --rebase, git push", p.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_host_choices_new_and_changed(self):
        host = self.repo / "hosts/mbp16"
        host.mkdir(parents=True)
        (host / "widgets.toml").write_text('yes = ["a"]\n')
        # A new choice file is added by lib/ws_catalog.py that writes it.
        self.git("add", "hosts/mbp16/widgets.toml")
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "ws sync: hosts/mbp16/widgets.toml")
        self.assertIn("hosts/mbp16/widgets.toml: a=yes", self.git("log", "-1", "--format=%b"))
        (host / "widgets.toml").write_text('yes = []\nno = ["a"]\n')
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("widgets.toml: a=no", self.git("log", "-1", "--format=%b"))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_new_scripts_are_added_and_committed(self):
        # scripts/: added without git add (ws help plan-v2, 10.1); other
        # untracked files and ignored ones stay out.
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts/hello").write_text("#!/bin/sh\n")
        (self.repo / "scripts/old.bak").write_text("")
        (self.repo / ".gitignore").write_text("*.bak\n")
        self.git("add", ".gitignore")
        (self.repo / "notes.txt").write_text("")
        p = self.ws("--dry-run")
        self.assertIn("would add to Git and commit: scripts/hello", p.stdout)
        self.assertEqual(self.git("ls-files", "scripts"), "")
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("not tracked, not published: notes.txt", p.stdout)
        self.assertIn("not tracked, not published: notes.txt (", p.stdout)
        self.assertEqual(self.git("ls-files", "scripts"), "scripts/hello")
        self.assertIn("scripts/hello: +hello", self.git("log", "-1", "--format=%b"))
        (self.repo / "scripts/hello").write_text("#!/bin/sh\necho\n")
        self.assertEqual(self.ws().returncode, 0)
        self.assertIn("scripts/hello: edited", self.git("log", "-1", "--format=%b"))
        # Deleted by hand: the deletion is the next commit.
        (self.repo / "scripts/hello").unlink()
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scripts/hello: -hello", self.git("log", "-1", "--format=%b"))
        self.assertEqual(self.git("ls-files", "scripts"), "")
        # Deleted with git rm (ws script delete): out of the index already.
        (self.repo / "scripts/b").write_text("#!/bin/sh\n")
        self.assertEqual(self.ws().returncode, 0)
        self.git("rm", "-q", "scripts/b")
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("scripts/b: -b", self.git("log", "-1", "--format=%b"))
        self.assertEqual(self.git("status", "--porcelain"), "?? notes.txt")

    def test_every_tracked_change_is_data(self):
        # No code in a configuration: an unpushed commit of any file is
        # published too.
        origin = self.with_upstream()
        (self.repo / "README").write_text("notes\n")
        self.git("add", "README")
        self.git("commit", "-qm", "notes")
        self.edit_apps()
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.git("rev-parse", "main", cwd=origin))

    def test_refuses_detached_head_and_git_operations(self):
        self.git("checkout", "-q", "--detach")
        p = self.ws()
        self.assertEqual(p.returncode, 1)
        self.assertIn("HEAD is detached", p.stderr)
        self.git("checkout", "-q", "main")
        (self.repo / ".git/MERGE_HEAD").write_text(self.git("rev-parse", "HEAD") + "\n")
        p = self.ws()
        self.assertEqual(p.returncode, 1)
        self.assertIn("a Git operation is in progress (merge_head)", p.stderr)

    def test_conflict_stops_with_the_manual_steps(self):
        origin = self.with_upstream()
        other = self.root / "other"
        subprocess.run(["git", "clone", "-q", str(origin), str(other)], env=self.env, check=True)
        (other / "flatpak/catalog.toml").write_text(CATALOG + APP_B.replace(".B", ".C"))
        self.git("commit", "-qam", "other", cwd=other)
        self.git("push", "-q", cwd=other)
        self.edit_apps()
        p = self.ws()
        self.assertEqual(p.returncode, 1)
        self.assertIn("stopped on a conflict", p.stderr)
        self.assertIn("rebase --abort", p.stderr)
        # Nothing is resolved or reset: the rebase is left to the user.
        self.assertTrue((self.repo / ".git/rebase-merge").exists() or (self.repo / ".git/rebase-apply").exists())

    def test_nothing_to_commit_still_pushes_earlier_data_commits(self):
        origin = self.with_upstream()
        self.edit_apps()
        self.git("commit", "-qam", "data by hand")
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("no changed data files", p.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.git("rev-parse", "main", cwd=origin))


if __name__ == "__main__":
    unittest.main()
