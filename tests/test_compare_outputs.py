"""tests/compare-outputs on fake store trees (helpws plan-v2, 0.1)."""
from importlib.machinery import SourceFileLoader
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = SourceFileLoader("compare_outputs", str(ROOT / "tests/compare-outputs"))
spec = importlib.util.spec_from_loader("compare_outputs", loader)
co = importlib.util.module_from_spec(spec)
loader.exec_module(co)


class CompareOutputsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = os.path.join(tmp.name, "nix/store")
        os.makedirs(self.store)

    def path(self, name, letter):
        return f"{self.store}/{letter * 32}-{name}"

    def file(self, name, letter, content, mode=0o444):
        p = self.path(name, letter)
        Path(p).write_text(content)
        os.chmod(p, mode)
        return p

    def tree(self, name, letter, entries):
        """entries: {relpath: str content | ('link', target)}."""
        root = self.path(name, letter)
        os.makedirs(root, exist_ok=True)
        for rel, value in entries.items():
            p = Path(root, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(value, tuple):
                p.symlink_to(value[1])
            else:
                p.write_text(value)
        return root

    def system(self, letter, files, manifest):
        entries = {f"files{k}": v for k, v in files.items()}
        entries["manifest"] = manifest
        return self.tree("system-t2-mbp16", letter, entries)

    def home(self, letter, files, activate=None):
        hf = self.tree("home-manager-files", letter, files)
        gen = self.path("home-manager-generation", letter)
        return self.tree("home-manager-generation", letter, {
            "home-files": ("link", hf),
            "activate": activate if activate is not None else f"#!/bin/sh\n{gen}/home-files\n",
        })

    def compare(self, base, work, allow=()):
        c = co.Comparator(self.store)
        co.compare_outputs(base, work, c)
        findings, unused = co.apply_allow(c.findings, list(allow))
        return findings, unused

    def kinds(self, findings):
        return {(k, label) for k, label, _ in findings}

    def test_identical_outputs(self):
        s = self.system("a", {"/etc/x": "x\n"}, "file\t0644\t/etc/x\n")
        findings, _ = self.compare({"system-mbp16": s}, {"system-mbp16": s})
        self.assertEqual(findings, [])

    def test_system_file_content_is_kind_1(self):
        a = self.system("a", {"/etc/x": "old\n"}, "file\t0644\t/etc/x\n")
        b = self.system("b", {"/etc/x": "new\n"}, "file\t0644\t/etc/x\n")
        findings, _ = self.compare({"system-mbp16": a}, {"system-mbp16": b})
        self.assertEqual(self.kinds(findings), {(1, "system-mbp16/files/etc/x")})
        self.assertIn("+new", findings[0][2])

    def test_manifest_lines_are_kind_2(self):
        a = self.system("a", {}, "unit\tenabled\ta.service\n")
        b = self.system("b", {}, "unit\tenabled\ta.service\nrestart\t-\ta.service\n")
        findings, _ = self.compare({"system-mbp16": a}, {"system-mbp16": b})
        self.assertEqual(self.kinds(findings), {(2, "system-mbp16/manifest:+restart - a.service")})

    def test_store_paths_only_is_kind_3(self):
        sa = self.file("helper", "c", "echo hi\n")
        sb = self.file("helper", "d", "echo hi\n")
        a = self.system("a", {"/etc/x": f"run {sa}\n"}, "file\t0644\t/etc/x\n")
        b = self.system("b", {"/etc/x": f"run {sb}\n"}, "file\t0644\t/etc/x\n")
        findings, _ = self.compare({"system-mbp16": a}, {"system-mbp16": b})
        self.assertEqual(self.kinds(findings), {(3, "system-mbp16/files/etc/x")})

    def test_referenced_script_change_is_reported_with_its_chain(self):
        sa = self.file("helper", "c", "echo old\n")
        sb = self.file("helper", "d", "echo new\n")
        a = self.home("a", {".config/systemd/user/x.service": f"ExecStart={sa}\n"})
        b = self.home("b", {".config/systemd/user/x.service": f"ExecStart={sb}\n"})
        findings, _ = self.compare({"home-mbp16": a}, {"home-mbp16": b})
        self.assertEqual(self.kinds(findings),
                         {(2, "home-mbp16/home-files/.config/systemd/user/x.service <- helper")})

    def test_generation_self_reference_adds_nothing(self):
        a = self.home("a", {".config/x": "old\n"})
        b = self.home("b", {".config/x": "new\n"})
        findings, _ = self.compare({"home-mbp16": a}, {"home-mbp16": b})
        self.assertEqual(self.kinds(findings), {(2, "home-mbp16/home-files/.config/x")})

    def test_home_file_list_and_out_of_store_links(self):
        a = self.home("a", {".local/bin/ws": ("link", "/home/u/wsconfig/bin/ws"),
                            ".local/bin/dotgit": ("link", "/home/u/wsconfig/bin/dotgit")})
        b = self.home("b", {".local/bin/ws": ("link", "/home/u/wsconfig/bin/ws")})
        findings, _ = self.compare({"home-mbp16": a}, {"home-mbp16": b})
        self.assertEqual(self.kinds(findings), {(2, "home-mbp16/home-files/.local/bin/dotgit")})

    def test_allow_moves_to_kind_4_and_reports_unused_patterns(self):
        a = self.home("a", {".local/bin/dotgit": ("link", "/home/u/wsconfig/bin/dotgit")})
        b = self.home("b", {})
        findings, unused = self.compare({"home-mbp16": a}, {"home-mbp16": b},
                                        ["home-*/home-files/.local/bin/dotgit", "system-*/files/etc/none"])
        self.assertEqual(self.kinds(findings), {(4, "home-mbp16/home-files/.local/bin/dotgit")})
        self.assertEqual(unused, ["system-*/files/etc/none"])

    def test_output_only_on_one_side(self):
        s = self.system("a", {}, "")
        findings, _ = self.compare({"system-mbp16": s}, {})
        self.assertEqual(self.kinds(findings), {(2, "system-mbp16")})

    def test_report_prints_every_kind(self):
        out = io.StringIO()
        co.report([(3, "system-mbp16/files/etc/x", "")], False, out)
        self.assertEqual(out.getvalue().splitlines(), [
            "1. content of managed system files: none",
            "2. manifests and parameters: none",
            "3. /nix/store paths only: 1",
            "  system-mbp16/files/etc/x",
            "4. allowed by --allow: none",
        ])

    def test_read_allow_skips_comments(self):
        with tempfile.NamedTemporaryFile("w", suffix=".allow", delete=False) as f:
            f.write("# step 1.1\nhome-*/home-files/.local/bin/dotgit  # removed\n\n")
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(co.read_allow(f.name), ["home-*/home-files/.local/bin/dotgit"])


if __name__ == "__main__":
    unittest.main()
