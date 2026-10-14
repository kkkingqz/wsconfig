"""lib/flatpak_catalog.py: the Flatpak catalog and the overrides of a host
(ws help plan-v2, 3.4). lib/test-catalog.nix checks lib/catalog.nix on the
same fixture."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import flatpak_catalog  # noqa: E402
import ws_catalog  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/catalog"
APP = "org.example.App"


class FlatpakCatalogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name)
        shutil.copytree(FIXTURE, self.config / "nix/hosts")
        (self.config / "flatpak").mkdir()
        shutil.copyfile(FIXTURE / "catalog.toml", self.config / "flatpak/catalog.toml")
        self.catalog = flatpak_catalog.Catalog(self.config)

    def choice(self, host="a"):
        return ws_catalog.Choice("flatpak", host, self.config)

    def test_effective_as_lib_catalog_nix(self):
        values = flatpak_catalog.effective(self.catalog, self.choice(), APP)
        # Nix sorts env names: compare as sets; the order of each kind is kept.
        self.assertEqual(sorted(values), sorted([
            ("filesystem", "home:ro"), ("env", "OTHER=x"), ("talk", "org.example.Kept"),
            ("filesystem", "xdg-download"), ("env", "SCALE=1")]))
        self.assertEqual([v for k, v in values if k == "filesystem"], ["home:ro", "xdg-download"])
        # Without a section: the catalog values.
        self.assertEqual(flatpak_catalog.effective(self.catalog, self.choice("b"), APP),
                         self.catalog.values(APP))

    def test_manifest_overrides(self):
        self.assertEqual(flatpak_catalog.manifest_overrides(self.catalog, self.choice()), {APP: {
            "filesystems": ["home:ro", "xdg-download"],
            "environment": {"OTHER": "x", "SCALE": "1"},
            "session_bus": {"org.example.Kept": "talk"}}})

    def test_default_and_values(self):
        self.assertEqual(self.catalog.default("org.example.Plain"), "no")
        self.assertEqual(self.catalog.default(APP), "ask")
        self.assertEqual(flatpak_catalog.key_of("filesystem", "xdg-run/x:create"), "xdg-run/x")
        self.assertEqual(flatpak_catalog.key_of("env", "A=b=c"), "A")

    def test_invalid_catalogs_are_refused(self):
        bad = {
            'apps = 1\n': r"\[\[apps\]\]",
            '[[apps]]\nid = "a"\nremote = "x"\n': r"not in \[remotes\]",
            '[remotes]\nf = "u"\n[[apps]]\nid = "a"\nremote = "f"\n[[apps]]\nid = "a"\nremote = "f"\n': "twice",
            '[remotes]\nf = "u"\n[[apps]]\nid = "a"\nremote = "f"\nfilesystems = ["home", "home:ro"]\n': "two values",
            '[remotes]\nf = "u"\n[[apps]]\nid = "a"\nremote = "f"\ncolour = "x"\n': "unknown keys",
            '[remotes]\nf = "u"\n[[apps]]\nid = "a"\nremote = "f"\ndefault = "maybe"\n': "default",
        }
        for text, message in bad.items():
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                flatpak_catalog.Catalog.parse(text, "catalog.toml")

    def test_host_section_must_fit_the_catalog(self):
        choice = self.choice()
        flatpak_catalog.check_host(choice, self.catalog)
        path = self.config / "nix/hosts/a/flatpak.toml"
        path.write_text('[overrides."org.example.Unknown"]\nenv = { A = "1" }\n')
        with self.assertRaisesRegex(ValueError, "not in"):
            flatpak_catalog.check_host(self.choice(), self.catalog)

    def test_add_and_remove_keep_comments(self):
        self.assertTrue(self.catalog.add_app("org.example.New", "flathub"))
        self.assertFalse(self.catalog.add_app(APP, "flathub"))
        self.catalog.save()
        text = (self.config / "flatpak/catalog.toml").read_text()
        self.assertTrue(text.startswith("# The Flatpak catalog of the fixture hosts"))
        self.assertTrue(text.endswith('\n\n[[apps]]\nid = "org.example.New"\nremote = "flathub"\n'), text)
        catalog = flatpak_catalog.Catalog(self.config)
        self.assertTrue(catalog.remove_app("org.example.Plain"))
        catalog.save()
        self.assertEqual(flatpak_catalog.Catalog(self.config).ids(), [APP, "org.example.New"])

    def test_summary(self):
        old = (FIXTURE / "catalog.toml").read_text()
        new = old.replace('default = "no"\n', '') + '\n[[apps]]\nid = "org.example.New"\nremote = "flathub"\n'
        self.assertEqual(flatpak_catalog.summary(old, new), "+org.example.New, org.example.Plain (default)")
        self.assertEqual(flatpak_catalog.summary(old, old + "# x\n"), "edited")

    def test_host_summary_names_changed_overrides(self):
        old = 'yes = ["a"]\n[overrides."a"]\nenv = { X = "1" }\n'
        new = 'yes = ["a"]\n[overrides."a"]\nenv = { X = "2" }\n'
        self.assertEqual(ws_catalog.summary(old, new), "overrides a")


if __name__ == "__main__":
    unittest.main()
