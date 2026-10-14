import contextlib
import hashlib
import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bin/wsgame"


class WsgameTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.g = runpy.run_path(str(SCRIPT))["main"].__globals__
        data = self.root / "gaming"
        self.g.update(DATA=data, SOURCES=data / "sources.json", SRC=data / "src", DEBS=data / "debs")
        data.mkdir()

    def file_source(self, name, content):
        path = self.root / name
        path.write_bytes(content)
        return {"url": path.as_uri(), "sha256": hashlib.sha256(content).hexdigest(), "version": "1-1ws1"}

    def quiet(self, fn, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = fn(*args)
        return result, out.getvalue()

    def test_download_names(self):
        f = self.g["src_file"]
        self.assertEqual(f("steamos-manager", {"url": "https://x/archive/abc.tar.gz"}).name, "steamos-manager.tar.gz")
        self.assertEqual(f("extest", {"url": "https://x/libextest.so"}).name, "extest.so")
        self.assertEqual(f("powerbuttond-debounce", {"url": "https://x/0001-a.patch"}).name, "powerbuttond-debounce.patch")

    def test_fetch_checks_sha256_and_keeps_good_files(self):
        sources = {"extest": self.file_source("libextest.so", b"elf")}
        self.assertEqual(self.quiet(self.g["cmd_fetch"], sources)[0], 0)
        self.assertEqual((self.g["SRC"] / "extest.so").read_bytes(), b"elf")
        self.assertIn("present: extest.so", self.quiet(self.g["cmd_fetch"], sources)[1])
        bad = {"inputplumber": dict(self.file_source("ip.deb", b"deb"), sha256="0" * 64)}
        with self.assertRaises(SystemExit) as e:
            self.quiet(self.g["cmd_fetch"], bad)
        self.assertIn("sha256", str(e.exception))
        self.assertEqual(sorted(p.name for p in self.g["SRC"].iterdir()), ["extest.so"])

    def test_versions_for_the_build_script(self):
        env = self.g["versions_env"]({"steamos-manager": {"version": "26.4.1-1ws1"},
                                      "powerbuttond-debounce": {"version": ""}})
        self.assertEqual(env, "VERSION_steamos_manager='26.4.1-1ws1'\n")

    def check(self, game, installed):
        self.g["SOURCES"].write_text(json.dumps({n: {"version": "1-1ws1"} for n in self.g["PACKAGES"]}))
        self.g["fact"] = lambda name: game
        self.g["installed_version"] = lambda name: installed.get(name)
        self.g["ok"] = lambda args: True
        rc, out = self.quiet(self.g["cmd_check"], True)
        return rc, json.loads(out)

    def test_check_without_game_mode_or_packages_is_quiet(self):
        rc, result = self.check("no", {})
        self.assertEqual((rc, result["status"]), (0, "pass"))
        self.assertIn("no Game Mode", result["messages"][0]["text"])
        rc, result = self.check("yes", {})
        self.assertEqual((rc, result["status"]), (0, "pass"))
        self.assertIn("not installed yet", result["messages"][0]["text"])

    def test_check_reports_missing_and_other_versions(self):
        rc, result = self.check("yes", {"steamos-manager": "0-old", "inputplumber": "1-1ws1"})
        self.assertEqual(rc, 1)
        texts = [m["text"] for m in result["messages"]]
        self.assertIn("package missing: powerbuttond (ws game install)", texts)
        self.assertTrue(any(t.startswith("steamos-manager 0-old installed, 1-1ws1 pinned") for t in texts))
        self.assertIn("inputplumber 1-1ws1", texts)


if __name__ == "__main__":
    unittest.main()
