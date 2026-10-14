"""lib/ws_facts.py: the one reader of hosts and facts (ws help plan-v2, 2.2 and 4)."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ws_facts  # noqa: E402

HOST = '''# boot = "commented"
[host]
hostname = "%s"
user = "king"

[platform]
boot = "grub" # trailing comment
empty = ""
displayScale = 1.5
kernelParams = ["a"]

[layers]
vm = true
widgets = false

[container]
image = "local/x"
port = 3390
'''


class FactsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name)
        for host, hostname in (("this", socket.gethostname()), ("other", "elsewhere"), ("bad.name", "x")):
            (self.config / "nix/hosts" / host).mkdir(parents=True)
            (self.config / "nix/hosts" / host / "host.toml").write_text(HOST % hostname)

    def cli(self, *args, **env):
        e = {k: v for k, v in os.environ.items() if k not in ("WS_HOST", "WS_CONFIG")}
        e.update(WSCONFIG=str(self.config), WS_STATE=str(self.config / "state"), **env)
        return subprocess.run([sys.executable, str(ROOT / "lib/ws_facts.py"), *args],
                              text=True, capture_output=True, env=e)

    def test_facts_of_the_sections(self):
        path = self.config / "nix/hosts/other/host.toml"
        self.assertEqual(ws_facts.fact_in(path, "boot"), "grub")
        self.assertEqual(ws_facts.fact_in(path, "user"), "king")
        self.assertEqual(ws_facts.fact_in(path, "displayScale"), "1.5")
        # true and false as the bash checks compare them.
        self.assertEqual(ws_facts.fact_in(path, "vm"), "yes")
        self.assertEqual(ws_facts.fact_in(path, "widgets"), "no")
        self.assertIsNone(ws_facts.fact_in(path, "kernelParams"))
        # [container] holds no facts.
        self.assertIsNone(ws_facts.fact_in(path, "image"))
        self.assertIsNone(ws_facts.fact_in(path, "missing"))
        self.assertIsNone(ws_facts.fact_in(self.config / "nope.toml", "user"))

    def test_host_by_hostname_or_ws_host(self):
        self.assertEqual(self.cli("host").stdout, "this\n")
        self.assertEqual(self.cli("host", WS_HOST="other").stdout, "other\n")

    def test_record_and_host_json(self):
        p = self.cli("record", WS_HOST="other")
        self.assertEqual(p.returncode, 0, p.stderr)
        record = json.loads((self.config / "state/host.json").read_text())
        self.assertEqual(record, {"host": "other", "config": str(self.config)})
        # Unchanged: not written again.
        self.assertEqual(self.cli("record", WS_HOST="other").stderr, "")
        # The record names the host of its configuration only.
        self.assertEqual(self.cli("host").stdout, "other\n")
        record["config"] = "/elsewhere"
        (self.config / "state/host.json").write_text(json.dumps(record))
        self.assertEqual(self.cli("host").stdout, "this\n")
        # record finds the host again, not from the old record.
        record["config"] = str(self.config)
        (self.config / "state/host.json").write_text(json.dumps(record))
        self.cli("record")
        self.assertEqual(json.loads((self.config / "state/host.json").read_text())["host"], "this")

    def test_unknown_host(self):
        (self.config / "nix/hosts/this/host.toml").unlink()
        p = self.cli("host")
        self.assertEqual(p.returncode, 1)
        self.assertIn("no nix/hosts/*/host.toml with hostname", p.stderr)

    def test_broken_toml_names_the_file(self):
        (self.config / "nix/hosts/other/host.toml").write_text("[host\n")
        p = self.cli("fact", "--host", "other", "user")
        self.assertEqual(p.returncode, 1)
        self.assertIn("nix/hosts/other/host.toml:", p.stderr)

    def test_host_for_marks(self):
        self.assertEqual(self.cli("host", "--for-marks", WS_HOST="other").stdout, "other\n")
        for bad in ("all", "bad.name"):
            p = self.cli("host", "--for-marks", WS_HOST=bad)
            self.assertEqual(p.returncode, 1)
            self.assertIn("invalid workstation name", p.stderr)

    def test_fact_of_this_host_another_host_and_a_file(self):
        self.assertEqual(self.cli("fact", "boot").stdout, "grub\n")
        self.assertEqual(self.cli("fact", "--host", "other", "user").stdout, "king\n")
        f = self.config / "nix/hosts/other/host.toml"
        self.assertEqual(self.cli("fact", "--file", str(f), "vm").stdout, "yes\n")

    def test_section_as_json(self):
        p = self.cli("section", "--host", "other", "container")
        self.assertEqual(json.loads(p.stdout), {"image": "local/x", "port": 3390})
        p = self.cli("section", "--host", "other", "nope")
        self.assertEqual(p.returncode, 1)
        self.assertIn("no section [nope] in nix/hosts/other/host.toml", p.stderr)

    def test_missing_and_empty_facts_fail(self):
        for args, message in ((("fact", "empty"), "no fact empty in nix/hosts/this/host.toml"),
                              (("fact", "kernelParams"), "no fact kernelParams"),
                              (("fact", "--host", "nope", "user"), "no nix/hosts/nope/host.toml"),
                              (("fact",), "usage: ws fact")):
            p = self.cli(*args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn(message, p.stderr)

    def test_ws_uses_it(self):
        p = subprocess.run([str(ROOT / "bin/ws"), "fact", "--host", "other", "user"], text=True,
                           capture_output=True, env={**os.environ, "WSCONFIG": str(self.config)})
        self.assertEqual(p.stdout, "king\n")

    def test_hosts_of_the_repository(self):
        # Every host has the facts the bash tools read (lib/host.nix checks
        # the rest with Nix).
        for path in sorted((ROOT / "nix/hosts").glob("*/host.toml")):
            with self.subTest(host=path.parent.name):
                for name in ("hostname", "user", "wsconfig", "hardware", "boot"):
                    self.assertTrue(ws_facts.fact_in(path, name), name)
                for name in ("vm", "nativeSteam", "gameMode", "widgets"):
                    self.assertIn(ws_facts.fact_in(path, name), ("yes", "no"), name)


if __name__ == "__main__":
    unittest.main()
