"""ws setup (libexec/ws-setup, ws help plan-v2, 9.2, 9.6, 9.7): the
configuration from --repo in ~/wsconfig, then the core it pins, built from
it into WS_STATE/setup/ws, runs the same command again; --new DIR from the
template of this core. Stubs for gh, sudo, nix."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
STUB = "#!/bin/sh\nexit 0\n"
PINNED = "b" * 40
# nix build --out-link LINK REF: LINK to the core $FAKE_CORE, the call kept.
NIX = ('#!/bin/sh\necho "$*" >> "$HOME/nix-calls"\ncase "$1" in\n'
       '  build) ln -sfn "$FAKE_CORE" "$3" ;;\n'
       # nix flake metadata --json github:O/R/REV
       '  flake) printf \'{"locked": {"type": "github", "owner": "o", "repo": "r", "rev": "%s", '
       '"narHash": "sha256-x", "lastModified": 1}}\\n\' "${4##*/}" ;;\nesac\n')
# The ws of the pinned core: records how it was started.
FAKE_WS = '#!/bin/sh\necho "$*" > "$HOME/pinned-args"\n'


class SetupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        stubs = self.root / "bin"
        stubs.mkdir()
        for name in ("gh", "sudo", "apt-get", "xdg-terminal-exec"):
            (stubs / name).write_text(STUB)
        (stubs / "nix").write_text(NIX)
        for f in stubs.iterdir():
            f.chmod(0o755)
        # The core of this run in the store: this checkout without tests/.
        self.core = self.root / "core"
        shutil.copytree(ROOT, self.core, symlinks=True,
                        ignore=lambda d, names: [n for n in names if Path(d) == ROOT
                                                 and n in (".git", "tests")])
        (self.core / ".wsconfig-package").touch()
        self.state = self.home / ".local/state/wsconfig/setup"
        self.state.mkdir(parents=True)
        (self.state / "core").write_text("a" * 40 + "\n")
        # The pinned core nix build gives.
        self.fake = self.root / "pinned"
        (self.fake / "bin").mkdir(parents=True)
        (self.fake / "libexec").mkdir()
        (self.fake / "bin/ws").write_text(FAKE_WS)
        (self.fake / "bin/ws").chmod(0o755)
        (self.fake / "libexec/ws-setup").write_text(STUB)
        (self.fake / "libexec/ws-setup").chmod(0o755)
        gitconfig = self.root / "gitconfig"
        gitconfig.write_text("[user]\n\tname = t\n\temail = t@t\n[init]\n\tdefaultBranch = main\n")
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("WS", "GIT_", "XDG_", "NIX_"))}
        self.env.update(HOME=str(self.home), PATH=f"{stubs}:{os.environ['PATH']}",
                        GIT_CONFIG_GLOBAL=str(gitconfig), GIT_CONFIG_NOSYSTEM="1",
                        WS_SETUP_TTY="/dev/null", FAKE_CORE=str(self.fake))
        self.config = self.root / "config-origin"
        self.config.mkdir()
        (self.config / "wsconfig.toml").write_text("schema = 1\n")
        lock = {"nodes": {"root": {"inputs": {"wsconfig": "wsconfig"}},
                          "wsconfig": {"locked": {"rev": PINNED}}}, "root": "root", "version": 7}
        (self.config / "flake.lock").write_text(json.dumps(lock))
        self.git(self.config, "init", "-q")
        self.git(self.config, "add", ".")
        self.git(self.config, "commit", "-qm", "config")

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], env=self.env, check=True, text=True,
                              capture_output=True).stdout.strip()

    def setup(self, *args, core=None):
        return subprocess.run([str((core or self.core) / "bin/ws"), "setup", *args],
                              env=self.env, text=True, capture_output=True)

    def nix_calls(self):
        f = self.home / "nix-calls"
        return f.read_text().splitlines() if f.exists() else []

    def test_repo_then_the_pinned_core_runs_setup_again(self):
        p = self.setup("--repo", str(self.config))
        self.assertEqual(p.returncode, 0, p.stderr)
        clone = self.home / "wsconfig"
        self.assertEqual(self.git(clone, "rev-parse", "HEAD"), self.git(self.config, "rev-parse", "HEAD"))
        self.assertEqual((self.state / "config").read_text().strip(), str(clone))
        self.assertEqual(self.nix_calls(), [f"build --out-link {self.state / 'ws'} git+file:{clone}#ws"])
        self.assertEqual((self.state / "core").read_text().strip(), PINNED)
        self.assertEqual((self.home / "pinned-args").read_text().strip(), f"setup --repo {self.config}")

    def test_the_pinned_core_goes_on_to_the_host(self):
        # A second run (after the exec): the same core, no build; the host
        # question reads the terminal (here empty).
        (self.state / "core").write_text(PINNED + "\n")
        p = self.setup("--repo", str(self.config))
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.nix_calls(), [])
        self.assertIn("не найден", p.stdout)
        self.assertIn("ws setup: no answer", p.stderr)
        # Without --repo it goes on with the configuration of the state.
        p = self.setup()
        self.assertIn("ws setup: no answer", p.stderr)

    def test_a_core_older_than_ws_setup(self):
        (self.fake / "libexec/ws-setup").unlink()
        p = self.setup("--repo", str(self.config))
        self.assertEqual(p.returncode, 1)
        self.assertIn("older than ws setup", p.stderr)
        self.assertFalse((self.home / "pinned-args").exists())

    def test_nothing_is_overwritten(self):
        (self.home / "wsconfig").mkdir()
        (self.home / "wsconfig/notes").write_text("mine\n")
        p = self.setup("--repo", str(self.config))
        self.assertEqual(p.returncode, 1)
        self.assertIn("is not a clone of", p.stderr)
        self.assertEqual((self.home / "wsconfig/notes").read_text(), "mine\n")
        self.assertFalse((self.state / "config").exists())

    def test_not_a_configuration(self):
        (self.config / "wsconfig.toml").unlink()
        self.git(self.config, "commit", "-qam", "no schema")
        p = self.setup("--repo", str(self.config))
        self.assertEqual(p.returncode, 1)
        self.assertIn("is not a configuration of wsconfig", p.stderr)

    def test_no_configuration(self):
        p = self.setup()
        self.assertEqual(p.returncode, 1)
        self.assertIn("ws setup --repo URL or --new", p.stderr)

    def test_a_checkout_of_the_core_is_not_replaced(self):
        (self.core / ".wsconfig-package").unlink()
        p = self.setup("--repo", str(self.config))
        self.assertEqual(p.returncode, 1)
        self.assertIn(f"checkout {self.core}", p.stdout)
        self.assertEqual(self.nix_calls(), [])

    def test_new_from_the_template_of_this_core(self):
        own = "a" * 40
        p = self.setup("--new")
        # It goes on to the host question (the terminal is empty here).
        self.assertIn("ws setup: no answer", p.stderr)
        cfg = self.home / "wsconfig"
        for f in ("flake.nix", "wsconfig.toml", ".gitignore", "apt.txt", "flatpak/catalog.toml"):
            self.assertTrue((cfg / f).is_file(), f)
        lock = json.loads((cfg / "flake.lock").read_text())
        self.assertEqual(lock["nodes"]["wsconfig"]["locked"]["rev"], own)
        self.assertEqual(self.nix_calls(), [f"flake metadata --json github:kkkingqz/wsconfig/{own}"])
        self.assertEqual(self.git(cfg, "log", "--format=%s"),
                         "Configuration from the template of wsconfig aaaaaaaaaaaa (ws setup --new)")
        self.assertEqual(self.git(cfg, "status", "--porcelain"), "")
        self.assertEqual((self.state / "mode").read_text().strip(), "new")
        self.assertEqual((self.state / "config").read_text().strip(), str(cfg))

    def test_new_never_into_a_full_directory(self):
        (self.root / "mine").mkdir()
        (self.root / "mine/notes").write_text("x\n")
        p = self.setup("--new", str(self.root / "mine"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("is not empty: nothing is overwritten", p.stderr)
        self.assertEqual(sorted(x.name for x in (self.root / "mine").iterdir()), ["notes"])

    def test_a_schema_this_core_does_not_read(self):
        (self.state / "core").write_text(PINNED + "\n")
        (self.config / "wsconfig.toml").write_text("schema = 99\n")
        self.git(self.config, "commit", "-qam", "schema 99")
        p = self.setup("--repo", str(self.config))
        self.assertEqual(p.returncode, 1)
        self.assertIn("it needs a migration", p.stderr)

    def test_usage(self):
        self.assertEqual(self.setup("--bogus").returncode, 64)
        p = self.setup("--help")
        self.assertEqual(p.returncode, 0)
        self.assertIn("ws setup --repo URL|PATH", p.stdout)


if __name__ == "__main__":
    unittest.main()
