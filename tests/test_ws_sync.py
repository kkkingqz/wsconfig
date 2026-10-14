"""ws sync: the only commit and push of the data files (helpws plan-v2, 2.7)."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
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
        self.repo = self.root / "repo"
        (self.repo / "bin").mkdir(parents=True)
        (self.repo / "flatpak").mkdir()
        shutil.copy(ROOT / "bin/ws", self.repo / "bin/ws")
        shutil.copytree(ROOT / "lib", self.repo / "lib", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(ROOT / ".gitignore", self.repo / ".gitignore")
        (self.repo / "flatpak/apps.txt").write_text("flathub org.example.A test=yes all=ask\n")
        (self.repo / "flake.lock").write_text('{"nodes": {"nixpkgs": {"locked": {"rev": "a"}}, "root": {}}}\n')
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "init")

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.repo), *args], env=self.env, check=True,
                              text=True, capture_output=True).stdout.strip()

    def ws(self, *args):
        return subprocess.run([str(self.repo / "bin/ws"), "sync", *args], env=self.env, text=True,
                              capture_output=True, stdin=subprocess.DEVNULL)

    def with_upstream(self):
        origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], env=self.env, check=True)
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "-u", "origin", "main")
        return origin

    def edit_apps(self):
        (self.repo / "flatpak/apps.txt").write_text(
            "flathub org.example.A test=yes all=ask\nflathub org.example.B test=yes all=ask\n")

    def test_no_remote_commits_locally(self):
        self.edit_apps()
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("no remote: the commit stays local", p.stdout)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "ws sync: flatpak/apps.txt")
        self.assertIn("flatpak/apps.txt: +org.example.B", self.git("log", "-1", "--format=%b"))
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
        self.assertEqual(log.splitlines()[:2], ["ws sync: flatpak/apps.txt flake.lock", "other"])
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
        self.assertIn("would commit: ws sync: flatpak/apps.txt", p.stdout)
        self.assertIn("would run: git pull --rebase, git push", p.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_host_choices_new_and_changed(self):
        host = self.repo / "nix/hosts/mbp16"
        host.mkdir(parents=True)
        (host / "widgets.toml").write_text('yes = ["a"]\n')
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "ws sync: nix/hosts/mbp16/widgets.toml")
        self.assertIn("nix/hosts/mbp16/widgets.toml: a=yes", self.git("log", "-1", "--format=%b"))
        (host / "widgets.toml").write_text('yes = []\nno = ["a"]\n')
        p = self.ws()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("widgets.toml: a=no", self.git("log", "-1", "--format=%b"))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_refuses_code_changes(self):
        (self.repo / "bin/ws").write_text((self.repo / "bin/ws").read_text() + "\n")
        self.edit_apps()
        p = self.ws()
        self.assertEqual(p.returncode, 1)
        self.assertIn("changes outside the data files: bin/ws", p.stderr)

    def test_refuses_unpushed_code_commits(self):
        self.with_upstream()
        (self.repo / "README").write_text("code\n")
        self.git("add", "README")
        self.git("commit", "-qm", "code")
        p = self.ws()
        self.assertEqual(p.returncode, 1)
        self.assertIn("local commits not on origin/main change code: README", p.stderr)

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
        (other / "flatpak/apps.txt").write_text("flathub org.example.C other=yes all=ask\n")
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
