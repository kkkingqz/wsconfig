"""lib/apt.bash: the apt lists of a host by its facts (ws help plan-v2, 2.3)."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

FACTS = '[platform]\nboot = "%s"\n\n[layers]\nvm = %s\nnativeSteam = %s\ngameMode = %s\n'
# yes and no as TOML booleans, anything else as a string.
toml = lambda v: {"yes": "true", "no": "false"}.get(v, f'"{v}"')


class AptListsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        # The lists of the core (what its modules need) in WS_CORE, those of
        # the user and the hosts in the configuration (repo).
        self.core = self.root / "core"
        self.repo = self.root / "config"
        for d in ("system", "virt", "steam", "gaming", "lib"):
            (self.core / d).mkdir(parents=True, exist_ok=True)
        (self.repo / "hosts").mkdir(parents=True)
        for name in ("ws_facts.py", "ws_common.py"):
            shutil.copyfile(ROOT / "lib" / name, self.core / "lib" / name)
        (self.core / "system/apt.txt").write_text("# common\nfish   # shell\n\nppa:x/y\n")
        (self.repo / "apt.txt").write_text("btop\n")
        (self.core / "system/apt-machine.txt").write_text("rec:tlp\n")
        (self.core / "virt/apt.txt").write_text("qemu-kvm\n")
        (self.core / "steam/apt.txt").write_text("arch:i386\nsteam\n")
        (self.core / "gaming/apt.txt").write_text("sddm\n")

    def host(self, name, boot="grub", vm="no", steam="no", game="no", apt="purge:snapd\n"):
        d = self.repo / "hosts" / name
        d.mkdir()
        (d / "host.toml").write_text(FACTS % (boot, toml(vm), toml(steam), toml(game)))
        (d / "apt.txt").write_text(apt)

    def bash(self, script):
        env = {**os.environ, "WS_CORE": str(self.core)}
        p = subprocess.run(["bash", "-c", f'repo={self.repo}; . {ROOT}/lib/apt.bash; {script}'],
                           text=True, capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.splitlines()

    def rel(self, lines):
        """core/… or config/…: whose list it is."""
        return [str(Path(l).relative_to(self.root)) for l in lines]

    def test_plain_machine(self):
        self.host("pc")
        self.assertEqual(self.rel(self.bash("apt_host pc; apt_lists")),
                         ["core/system/apt.txt", "config/apt.txt", "config/hosts/pc/apt.txt",
                          "core/system/apt-machine.txt"])
        self.assertEqual(self.bash("apt_host pc; apt_lines"),
                         ["fish", "ppa:x/y", "btop", "purge:snapd", "rec:tlp"])

    def test_layers_by_facts(self):
        self.host("go", vm="yes", steam="yes", game="yes")
        self.assertEqual(self.rel(self.bash("apt_host go; apt_lists"))[3:],
                         ["core/system/apt-machine.txt", "core/virt/apt.txt", "core/steam/apt.txt",
                          "core/gaming/apt.txt"])

    def test_container_host_has_no_machine_list(self):
        self.host("box", boot="container")
        self.assertEqual(self.rel(self.bash("apt_host box; apt_lists")),
                         ["core/system/apt.txt", "config/apt.txt", "config/hosts/box/apt.txt"])

    def test_a_fact_that_is_not_yes_counts_as_no(self):
        self.host("odd", vm="maybe")
        self.assertNotIn("core/virt/apt.txt", self.rel(self.bash("apt_host odd; apt_lists")))

    def test_bootstrap_variables_without_facts(self):
        # bootstrap.sh and the image build set the variables themselves.
        self.host("pc")
        out = self.bash(f"host_list={self.repo}/hosts/pc/apt.txt container=true vm=yes "
                        "native_steam=no game_mode=no; apt_lists")
        self.assertEqual(self.rel(out), ["core/system/apt.txt", "config/apt.txt", "config/hosts/pc/apt.txt",
                                         "core/virt/apt.txt"])


if __name__ == "__main__":
    unittest.main()
