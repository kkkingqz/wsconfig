"""setup.sh on two repositories (ws help plan-v2, 8.10): the configuration
is cloned to ~/wsconfig, the core it pins to ~/.cache/wsconfig/core, and the
setup.sh of that core goes on with WSCONFIG. Stubs for gh, sudo, apt."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
STUB = "#!/bin/sh\nexit 0\n"
# The setup.sh of the core: records how it was started.
CORE_SETUP = '#!/bin/sh\necho "core setup: WSCONFIG=$WSCONFIG args=$*" > "$HOME/started"\n'


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
            (stubs / name).chmod(0o755)
        gitconfig = self.root / "gitconfig"
        gitconfig.write_text("[user]\n\tname = t\n\temail = t@t\n[init]\n\tdefaultBranch = main\n"
                             "[credential \"https://github.com\"]\n\thelper = !gh auth git-credential\n")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("WS", "GIT_", "XDG_"))}
        self.env.update(HOME=str(self.home), PATH=f"{stubs}:{os.environ['PATH']}",
                        GIT_CONFIG_GLOBAL=str(gitconfig), GIT_CONFIG_NOSYSTEM="1", WS_SETUP_TTY="/dev/null")
        self.core = self.root / "core-origin"
        self.core.mkdir()
        (self.core / "setup.sh").write_text(CORE_SETUP)
        self.rev = self.commit(self.core, "core")
        self.config = self.root / "config-origin"
        self.config.mkdir()
        lock = {"nodes": {"root": {"inputs": {"wsconfig": "wsconfig"}},
                          "wsconfig": {"locked": {"rev": self.rev}}}, "root": "root", "version": 7}
        (self.config / "flake.lock").write_text(json.dumps(lock))
        self.commit(self.config, "config")
        self.env["WS_SETUP_CORE_URL"] = str(self.core)

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], env=self.env, check=True, text=True,
                              capture_output=True).stdout.strip()

    def commit(self, d, msg):
        self.git(d, "init", "-q")
        self.git(d, "add", ".")
        self.git(d, "commit", "-qm", msg)
        return self.git(d, "rev-parse", "HEAD")

    def setup(self, *args):
        # As wget | bash -s -- ARGS: the script on stdin, no path of its own.
        return subprocess.run(["bash", "-s", "--", *args], input=(ROOT / "setup.sh").read_text(),
                              env=self.env, text=True, capture_output=True)

    def test_config_then_the_pinned_core_then_its_setup(self):
        # The core moved on after the configuration pinned it.
        (self.core / "later").write_text("x\n")
        self.git(self.core, "add", "later")
        self.git(self.core, "commit", "-qm", "later")
        p = self.setup(str(self.config))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git(self.home / "wsconfig", "rev-parse", "HEAD"),
                         self.git(self.config, "rev-parse", "HEAD"))
        self.assertEqual(self.git(self.home / ".cache/wsconfig/core", "rev-parse", "HEAD"), self.rev)
        self.assertEqual((self.home / "started").read_text().strip(),
                         f"core setup: WSCONFIG={self.home / 'wsconfig'} args=")

    def test_a_configuration_that_pins_no_core(self):
        (self.config / "flake.lock").write_text('{"nodes": {"root": {"inputs": {}}}, "root": "root"}')
        self.git(self.config, "commit", "-qam", "no core")
        p = self.setup(str(self.config))
        self.assertEqual(p.returncode, 1)
        self.assertIn("pins no core", p.stderr)

    def test_no_url(self):
        p = self.setup()
        self.assertEqual(p.returncode, 1)
        self.assertIn("no configuration repository", p.stderr)


if __name__ == "__main__":
    unittest.main()
