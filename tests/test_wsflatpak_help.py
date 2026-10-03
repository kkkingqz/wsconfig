from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "bin/wsflatpak"


class HelpTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              text=True, capture_output=True)

    def test_help_command_works_without_flatpak_configuration(self):
        result = self.cli("help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--unmanaged", result.stdout)
        self.assertIn("ws switch", result.stdout)

    def test_help_topic_does_not_require_topic_arguments(self):
        result = self.cli("help", "install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--remote", result.stdout)
        self.assertIn("--unmanaged", result.stdout)

    def test_help_accepts_command_alias(self):
        result = self.cli("help", "uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--keep-data", result.stdout)

    def test_unknown_help_topic_is_rejected(self):
        self.assertEqual(self.cli("help", "does-not-exist").returncode, 2)


if __name__ == "__main__":
    unittest.main()
