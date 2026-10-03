import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


FISH = os.environ.get("WSFLATPAK_TEST_FISH") or shutil.which("fish")
COMPLETIONS = Path(__file__).resolve().parents[1] / "terminal/fish/completions/wsflatpak.fish"
APP = "org.example.Installed"


@unittest.skipUnless(FISH, "fish is required for completion tests")
class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        repo = root / "repo/flatpak"
        repo.mkdir(parents=True)
        (repo / "apps.txt").write_text("flathub org.example.Removed# managed app\n")
        (repo / "overrides.txt").write_text(
            f"{APP} filesystem home:ro# read-only home\n{APP} env GDK_SCALE=2\n"
            f"{APP} talk org.example.Service\n"
            "org.example.Removed filesystem host\n")
        cfg = root / "cfg"
        cfg.mkdir()
        (cfg / "remotes.conf").write_text("flathub https://example.org\nflatpark https://example.net\n")
        stub = root / "flatpak"
        stub.write_text(f"#!{sys.executable}\n" + '''import sys
args = sys.argv[1:]
if args[0] == "list":
    print("org.example.Installed")
elif args[0] == "remote-ls":
    assert "--user" in args and "--cached" in args
    if args[-1] == "flatpark":
        print("org.example.Park/x86_64/stable")
    else:
        print("org.example.New/x86_64/stable")
elif args[0] == "remotes":
    print("flathub\\nflatpark")
else:
    raise AssertionError(args)
''')
        stub.chmod(0o755)
        self.env = dict(os.environ, HOME=str(root), WSCONFIG=str(repo.parent),
                        WSFLATPAK_CONFIG=str(cfg), PATH=f"{root}:{os.environ['PATH']}")

    def candidates(self, line):
        result = subprocess.run(
            [FISH, "--no-config", "-c",
             f"source {shlex.quote(str(COMPLETIONS))}; complete -C {shlex.quote(line)}"],
            env=self.env, text=True, capture_output=True, check=True)
        self.assertEqual(result.stderr, "")
        return {line.split("\t", 1)[0] for line in result.stdout.splitlines()}

    def test_missing_command_and_flags_are_completed(self):
        self.assertIn("remote-add", self.candidates("wsflatpak "))
        self.assertIn("--json", self.candidates("wsflatpak check --"))
        self.assertIn("--help", self.candidates("wsflatpak install --h"))

    def test_help_completes_command_topics(self):
        self.assertIn("install", self.candidates("wsflatpak help ins"))
        self.assertIn("remote-add", self.candidates("wsflatpak help remote-"))

    def test_install_offers_apps_and_full_refs_from_selected_remote(self):
        self.assertIn("org.example.Park", self.candidates("wsflatpak install --remote flatpark "))
        self.assertIn("app/org.example.Park/x86_64/stable",
                      self.candidates("wsflatpak install --remote=flatpark "))

    def test_install_remote_option_uses_configuration(self):
        self.assertEqual(self.candidates("wsflatpak install --remote "), {"flathub", "flatpark"})

    def test_app_candidates_stop_after_app_argument(self):
        self.assertIn(APP, self.candidates("wsflatpak env "))
        self.assertNotIn(APP, self.candidates(f"wsflatpak env {APP} "))

    def test_unmanage_offers_declared_app_even_if_not_installed(self):
        self.assertIn("org.example.Removed", self.candidates("wsflatpak unmanage "))

    def test_removing_override_offers_declared_value(self):
        self.assertIn("home:ro", self.candidates(f"wsflatpak unfilesystem {APP} "))
        self.assertIn("GDK_SCALE", self.candidates(f"wsflatpak unenv {APP} "))
        self.assertIn("org.example.Service", self.candidates(f"wsflatpak untalk {APP} "))

    def test_manage_second_argument_offers_remotes(self):
        self.assertIn("flatpark", self.candidates(f"wsflatpak manage {APP} "))
        self.assertNotIn(APP, self.candidates(f"wsflatpak manage {APP} "))


if __name__ == "__main__":
    unittest.main()
