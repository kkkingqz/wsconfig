"""install.sh (ws help plan-v2, 9.4): apt, @nix, Nix, the group, then ws
setup of the core at one revision: REV resolved once, built into
WS_STATE/setup/ws, recorded in WS_STATE/setup/core. Stubs for sudo, apt,
findmnt, nix, sg, wget; git ls-remote reads a local core repository."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]

STUBS = {
    # Every privileged command is only recorded.
    "sudo": '#!/bin/sh\necho "sudo $*" >> "$HOME/log"\n'
            'case "$*" in "btrfs subvolume show"*) [ -n "$NIX_MOUNTED" ] || exit 1 ;; esac\n',
    "dpkg-query": '#!/bin/sh\nfor p in $INSTALLED; do [ "$p" = "$3" ] && { printf "install ok installed"; exit 0; }; done\nexit 1\n',
    "findmnt": '#!/bin/sh\ncase "$*" in\n'
               '  "-no FSTYPE /") echo "$ROOT_FS" ;;\n'
               '  "-no OPTIONS /nix") [ -n "$NIX_MOUNTED" ] && echo rw,subvol=/@nix ;;\n'
               '  "-no SOURCE /") echo /dev/vda2 ;;\n'
               '  "-no UUID /") echo 0000-uuid ;;\n'
               '  *) exit 1 ;;\nesac\n',
    "systemctl": '#!/bin/sh\nexit 0\n',
    "getent": '#!/bin/sh\necho "nix-users:x:999:$NIX_MEMBERS"\n',
    "id": '#!/bin/sh\n[ "$1" = -nG ] && { echo "$ID_GROUPS"; exit 0; }\nexec /usr/bin/id "$@"\n',
    "wget": '#!/bin/sh\necho "wget $3" >> "$HOME/log"\ncp "$CORE_TREE/lib/btrfs.bash" "$2"\n',
    # nix build --out-link LINK REF
    "nix": '#!/bin/sh\necho "nix $* NIX_CONFIG=$NIX_CONFIG" >> "$HOME/log"\nln -sfn "$FAKE_CORE" "$3"\n',
    # sg GROUP -c CMD
    "sg": '#!/bin/sh\necho "sg $1" >> "$HOME/log"\nexec sh -c "$3"\n',
}


class InstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        stubs = self.root / "bin"
        stubs.mkdir()
        for name, body in STUBS.items():
            (stubs / name).write_text(body)
            (stubs / name).chmod(0o755)
        os_release = self.root / "os-release"
        os_release.write_text('ID=ubuntu\nVERSION_ID="26.04"\n')
        # The core repository ls-remote reads.
        self.origin = self.root / "core-origin"
        self.origin.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("WS", "GIT_", "XDG_", "NIX_"))}
        self.env.update(HOME=str(self.home), PATH=f"{stubs}:{os.environ['PATH']}",
                        GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
                        WS_INSTALL_GIT=str(self.origin), WS_INSTALL_RAW="https://raw.example/core",
                        WS_INSTALL_FLAKE="github:example/core", WS_INSTALL_OS_RELEASE=str(os_release),
                        WS_SETUP_TTY="/dev/null", ROOT_FS="btrfs", NIX_MOUNTED="", INSTALLED="",
                        NIX_MEMBERS="", ID_GROUPS="t", CORE_TREE=str(ROOT))
        self.git("init", "-q", "-b", "main")
        (self.origin / "f").write_text("1\n")
        self.git("add", "f")
        self.git("commit", "-qm", "one")
        self.main = self.git("rev-parse", "HEAD")
        # The core nix build gives: its ws records how it was started.
        self.fake = self.root / "fake-core"
        (self.fake / "bin").mkdir(parents=True)
        (self.fake / "bin/ws").write_text('#!/bin/sh\necho "$*" > "$HOME/ws-args"\n')
        (self.fake / "bin/ws").chmod(0o755)
        self.env["FAKE_CORE"] = str(self.fake)
        self.state = self.home / ".local/state/wsconfig/setup"

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.origin), *args], env=self.env, check=True,
                              text=True, capture_output=True).stdout.strip()

    def install(self, *args, **env):
        return subprocess.run(["bash", "-s", "--", *args], input=(ROOT / "install.sh").read_text(),
                              env=self.env | env, text=True, capture_output=True)

    def log(self):
        f = self.home / "log"
        return f.read_text().splitlines() if f.exists() else []

    def test_main_is_resolved_built_and_runs_ws_setup(self):
        p = self.install("--repo", "https://github.com/u/cfg.git")
        self.assertEqual(p.returncode, 0, p.stderr)
        log = self.log()
        self.assertIn(f"Ядро: main → {self.main}", p.stdout)
        self.assertEqual((self.state / "core").read_text().strip(), self.main)
        self.assertIn(f"wget https://raw.example/core/{self.main}/lib/btrfs.bash", log)
        self.assertIn("sudo btrfs subvolume create /run/btrfs-top/@nix", log)
        self.assertIn("sudo apt-get install -y git gh python3-tomlkit xdg-terminal-exec util-linux-extra", log)
        self.assertIn("sudo apt-get install -y nix-bin nix-setup-systemd", log)
        self.assertIn("sudo usermod -aG nix-users " + subprocess.check_output(["id", "-un"], text=True).strip(), log)
        # The group only through sg in this session.
        build = [line for line in log if line.startswith("nix build")]
        self.assertEqual(build, [f"nix build --out-link {self.state / 'ws'} github:example/core/{self.main}#ws"
                                 " NIX_CONFIG=experimental-features = nix-command flakes"])
        self.assertEqual(log.count("sg nix-users"), 2)
        self.assertEqual((self.home / "ws-args").read_text().strip(), "setup --repo https://github.com/u/cfg.git")
        self.assertEqual(os.readlink(self.state / "ws"), str(self.fake))

    def test_a_second_run_installs_nothing_again(self):
        user = subprocess.check_output(["id", "-un"], text=True).strip()
        p = self.install("--new", INSTALLED="git gh python3-tomlkit xdg-terminal-exec util-linux-extra "
                         "nix-bin nix-setup-systemd", NIX_MOUNTED="1", NIX_MEMBERS=user, ID_GROUPS="t nix-users")
        self.assertEqual(p.returncode, 0, p.stderr)
        log = self.log()
        self.assertFalse([line for line in log if "apt-get" in line or "subvolume create" in line or "usermod" in line], log)
        self.assertNotIn("sg nix-users", log)
        self.assertIn("/nix is mounted from @nix", p.stdout)
        self.assertEqual((self.home / "ws-args").read_text().strip(), "setup --new")

    def test_core_rev_branch_tag_or_commit(self):
        self.git("tag", "-a", "-m", "t", "v1")
        (self.origin / "f").write_text("2\n")
        self.git("commit", "-qam", "two")
        self.git("branch", "next")
        two = self.git("rev-parse", "HEAD")
        p = self.install("--core", "v1", "--new")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((self.state / "core").read_text().strip(), self.main)
        p = self.install("--core", "next")
        self.assertEqual((self.state / "core").read_text().strip(), two)
        commit = "c" * 40
        p = self.install("--core", commit)
        self.assertEqual((self.state / "core").read_text().strip(), commit)
        self.assertEqual((self.home / "ws-args").read_text().strip(), "setup")
        p = self.install("--core", "nothing")
        self.assertEqual(p.returncode, 1)
        self.assertIn("no branch or tag nothing", p.stderr)

    def test_refused_before_any_change(self):
        p = self.install("--new", ROOT_FS="ext4")
        self.assertEqual(p.returncode, 1)
        self.assertIn("/ is not Btrfs", p.stderr)
        (self.root / "os-release").write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
        p = self.install("--new")
        self.assertIn("Ubuntu 26.04 only (this is ubuntu-24.04)", p.stderr)
        self.assertEqual(self.log(), [])


if __name__ == "__main__":
    unittest.main()
