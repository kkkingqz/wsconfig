"""lib/apt.bash: the apt lists of a host by its facts (helpws plan-v2, 2.3)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

FACTS = '{\n  boot = "%s";\n  vm = "%s";\n  nativeSteam = "%s";\n  gameMode = "%s";\n}\n'


class AptListsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        for d in ("nix/hosts", "virt", "steam", "gaming"):
            (self.repo / d).mkdir(parents=True, exist_ok=True)
        (self.repo / "nix/hosts/apt.txt").write_text("# common\nfish   # shell\n\nppa:x/y\n")
        (self.repo / "nix/hosts/machine-apt.txt").write_text("rec:tlp\n")
        (self.repo / "virt/apt.txt").write_text("qemu-kvm\n")
        (self.repo / "steam/apt.txt").write_text("arch:i386\nsteam\n")
        (self.repo / "gaming/apt.txt").write_text("sddm\n")

    def host(self, name, boot="grub", vm="no", steam="no", game="no", apt="purge:snapd\n"):
        d = self.repo / "nix/hosts" / name
        d.mkdir()
        (d / "facts.nix").write_text(FACTS % (boot, vm, steam, game))
        (d / "apt.txt").write_text(apt)

    def bash(self, script):
        env = {**os.environ, "WS_CORE": str(ROOT)}
        p = subprocess.run(["bash", "-c", f'repo={self.repo}; . {ROOT}/lib/apt.bash; {script}'],
                           text=True, capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.splitlines()

    def rel(self, lines):
        return [str(Path(l).relative_to(self.repo)) for l in lines]

    def test_plain_machine(self):
        self.host("pc")
        self.assertEqual(self.rel(self.bash("apt_host pc; apt_lists")),
                         ["nix/hosts/apt.txt", "nix/hosts/pc/apt.txt", "nix/hosts/machine-apt.txt"])
        self.assertEqual(self.bash("apt_host pc; apt_lines"),
                         ["fish", "ppa:x/y", "purge:snapd", "rec:tlp"])

    def test_layers_by_facts(self):
        self.host("go", vm="yes", steam="yes", game="yes")
        self.assertEqual(self.rel(self.bash("apt_host go; apt_lists"))[2:],
                         ["nix/hosts/machine-apt.txt", "virt/apt.txt", "steam/apt.txt", "gaming/apt.txt"])

    def test_container_host_has_no_machine_list(self):
        self.host("box", boot="container")
        self.assertEqual(self.rel(self.bash("apt_host box; apt_lists")),
                         ["nix/hosts/apt.txt", "nix/hosts/box/apt.txt"])

    def test_a_fact_that_is_not_yes_counts_as_no(self):
        self.host("odd", vm="maybe")
        self.assertNotIn("virt/apt.txt", self.rel(self.bash("apt_host odd; apt_lists")))

    def test_bootstrap_variables_without_facts(self):
        # bootstrap.sh and the image build set the variables themselves.
        self.host("pc")
        out = self.bash(f"host_list={self.repo}/nix/hosts/pc/apt.txt container=true vm=yes "
                        "native_steam=no game_mode=no; apt_lists")
        self.assertEqual(self.rel(out), ["nix/hosts/apt.txt", "nix/hosts/pc/apt.txt", "virt/apt.txt"])


if __name__ == "__main__":
    unittest.main()
