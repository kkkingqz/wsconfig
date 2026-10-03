import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "lib/gnome_extension_files.py"


class ExtensionFilesTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), "extension file owner not implemented")
        spec = importlib.util.spec_from_file_location("extension_files", MODULE)
        self.owner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.owner)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.dest = self.root / "destination"
        (self.source / "extension.js").write_text("export default class Extension {}")
        (self.source / "metadata.json").write_text('{"uuid":"test@local"}')
        (self.source / "lib").mkdir()
        (self.source / "lib/old.js").write_text("old")

    def test_upgrade_delivers_nested_files_and_preserves_foreign(self):
        self.owner.install_files(self.source, self.dest)
        (self.dest / "foreign.txt").write_text("keep")
        (self.source / "lib/old.js").unlink()
        (self.source / "lib/new.js").write_text("new")
        self.owner.install_files(self.source, self.dest)
        self.assertEqual((self.dest / "lib/new.js").read_text(), "new")
        self.assertFalse((self.dest / "lib/old.js").exists())
        self.assertEqual((self.dest / "foreign.txt").read_text(), "keep")
        self.assertEqual(self.owner.verify_files(self.source, self.dest), [])

    def test_verification_detects_changed_and_missing_module(self):
        self.owner.install_files(self.source, self.dest)
        (self.dest / "lib/old.js").write_text("changed")
        self.assertIn("lib/old.js", self.owner.verify_files(self.source, self.dest))
        (self.dest / "lib/old.js").unlink()
        self.assertIn("lib/old.js", self.owner.verify_files(self.source, self.dest))

    def test_source_symlink_cannot_escape(self):
        (self.source / "lib/out.js").symlink_to(self.root / "outside")
        with self.assertRaises(ValueError):
            self.owner.install_files(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_destination_symlink_cannot_escape(self):
        self.dest.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (self.dest / "lib").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.owner.install_files(self.source, self.dest)
        self.assertEqual(list(outside.iterdir()), [])

    def test_invalid_previous_manifest_cannot_delete_outside(self):
        self.dest.mkdir()
        outside = self.root / "outside"
        outside.write_text("keep")
        (self.dest / ".ws-owned-files.json").write_text('["../outside"]')
        with self.assertRaises(ValueError):
            self.owner.install_files(self.source, self.dest)
        self.assertEqual(outside.read_text(), "keep")

    def test_generated_schema_is_not_source_and_assets_are_delivered(self):
        (self.source / "schemas").mkdir()
        (self.source / "schemas/gschemas.compiled").write_bytes(b"generated")
        (self.source / "schemas/test.gschema.xml").write_text("<schemalist/>")
        (self.source / "lib/icon.svg").write_text("<svg/>")
        self.owner.install_files(self.source, self.dest)
        self.assertFalse((self.dest / "schemas/gschemas.compiled").exists())
        self.assertTrue((self.dest / "schemas/test.gschema.xml").exists())
        self.assertTrue((self.dest / "lib/icon.svg").exists())
