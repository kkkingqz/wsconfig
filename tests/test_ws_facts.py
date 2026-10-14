"""lib/ws_facts.py: the one reader of hosts and string facts (helpws plan-v2, 2.2)."""
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

FACTS = '''{
  hostname = "%s";
  user = "king";
  # boot = "commented";
    boot = "grub"; # trailing comment
  boot = "second";
  empty = "";
  kernelParams = [ "a" ];
}
'''


class FactsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name)
        for host, hostname in (("this", socket.gethostname()), ("other", "elsewhere"), ("bad.name", "x")):
            (self.config / "nix/hosts" / host).mkdir(parents=True)
            (self.config / "nix/hosts" / host / "facts.nix").write_text(FACTS % hostname)

    def cli(self, *args, **env):
        e = {k: v for k, v in os.environ.items() if k not in ("WS_HOST", "WS_CONFIG")}
        e.update(WSCONFIG=str(self.config), **env)
        return subprocess.run([sys.executable, str(ROOT / "lib/ws_facts.py"), *args],
                              text=True, capture_output=True, env=e)

    def test_first_string_line_wins(self):
        path = self.config / "nix/hosts/other/facts.nix"
        self.assertEqual(ws_facts.fact_in(path, "boot"), "grub")
        self.assertEqual(ws_facts.fact_in(path, "user"), "king")
        self.assertIsNone(ws_facts.fact_in(path, "kernelParams"))
        self.assertIsNone(ws_facts.fact_in(path, "missing"))
        self.assertIsNone(ws_facts.fact_in(self.config / "nope.nix", "user"))

    def test_host_by_hostname_or_ws_host(self):
        self.assertEqual(self.cli("host").stdout, "this\n")
        self.assertEqual(self.cli("host", WS_HOST="other").stdout, "other\n")

    def test_unknown_host(self):
        for path in self.config.glob("nix/hosts/this/facts.nix"):
            path.unlink()
        p = self.cli("host")
        self.assertEqual(p.returncode, 1)
        self.assertIn("no nix/hosts/*/facts.nix with hostname", p.stderr)

    def test_host_for_marks(self):
        self.assertEqual(self.cli("host", "--for-marks", WS_HOST="other").stdout, "other\n")
        for bad in ("all", "bad.name"):
            p = self.cli("host", "--for-marks", WS_HOST=bad)
            self.assertEqual(p.returncode, 1)
            self.assertIn("invalid workstation name", p.stderr)

    def test_fact_of_this_host_another_host_and_a_file(self):
        self.assertEqual(self.cli("fact", "boot").stdout, "grub\n")
        self.assertEqual(self.cli("fact", "--host", "other", "user").stdout, "king\n")
        f = self.config / "nix/hosts/other/facts.nix"
        self.assertEqual(self.cli("fact", "--file", str(f), "user").stdout, "king\n")

    def test_missing_and_empty_facts_fail(self):
        for args, message in ((("fact", "empty"), "no string fact empty in nix/hosts/this/facts.nix"),
                              (("fact", "kernelParams"), "no string fact kernelParams"),
                              (("fact", "--host", "nope", "user"), "no nix/hosts/nope/facts.nix"),
                              (("fact",), "usage: ws fact")):
            p = self.cli(*args)
            self.assertEqual(p.returncode, 1, args)
            self.assertIn(message, p.stderr)

    def test_ws_uses_it(self):
        p = subprocess.run([str(ROOT / "bin/ws"), "fact", "--host", "other", "user"], text=True,
                           capture_output=True, env={**os.environ, "WSCONFIG": str(self.config)})
        self.assertEqual(p.stdout, "king\n")


if __name__ == "__main__":
    unittest.main()
