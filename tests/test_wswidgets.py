"""wswidgets against the host choices nix/hosts/HOST/widgets.toml and a
fixed catalog: list,
enabled, enable, disable, apply without a terminal and update with nix and
ws switch replaced by stubs, in a throwaway Git checkout."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
WSWIDGETS = ROOT / "bin/wswidgets"

CATALOG = [
    {"id": "example", "label": "Example"},
    {"id": "compact", "label": "Compact"},
    {"id": "clock", "label": "Clock"},
]


def lock(rev):
    return json.dumps({"nodes": {"wswidgets": {"locked": {
        "owner": "kkkingqz", "repo": "wswidgets", "rev": rev, "lastModified": 1791883161,
        "type": "github"}}}, "root": "root", "version": 7})


# nix flake update wswidgets --flake REPO: the lock moves to $NEW_REV and
# the catalog to $NEW_CATALOG.
NIX_STUB = r'''#!/usr/bin/env bash
echo "nix $*" >> "$WSW_TEST_LOG"
[[ "$1 $2 $3" == "flake update wswidgets" ]] || exit 1
python3 - "$5/flake.lock" "$NEW_REV" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["nodes"]["wswidgets"]["locked"]["rev"] = sys.argv[2]
open(sys.argv[1], "w").write(json.dumps(d))
PY
[[ -z "${NEW_CATALOG:-}" ]] || cp "$NEW_CATALOG" "$WSWIDGETS_CATALOG"
'''


class WswidgetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "repo"
        (self.repo / "nix/hosts/test").mkdir(parents=True)
        (self.repo / "nix/hosts/other").mkdir(parents=True)
        self.list = self.repo / "nix/hosts/test/widgets.toml"
        self.other = self.repo / "nix/hosts/other/widgets.toml"
        self.catalog = root / "catalog.json"
        self.catalog.write_text(json.dumps(CATALOG))
        self.log = root / "calls"
        stubs = root / "bin"
        stubs.mkdir()
        (stubs / "nix").write_text(NIX_STUB)
        (stubs / "nix").chmod(0o755)
        (stubs / "switch").write_text('#!/bin/sh\necho switch >> "$WSW_TEST_LOG"\nexit "${SWITCH_RC:-0}"\n')
        (stubs / "switch").chmod(0o755)
        (self.repo / "flake.lock").write_text(lock("a" * 40))
        git = ["git", "-C", str(self.repo)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "flake.lock"], check=True)
        subprocess.run([*git, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"], check=True)
        self.env = dict(os.environ, PATH=f"{stubs}:{os.environ['PATH']}", WSCONFIG=str(self.repo),
                        WSWIDGETS_CATALOG=str(self.catalog), WSWIDGETS_SWITCH=str(stubs / "switch"),
                        WSWIDGETS_FACT="yes", WS_HOST="test", WSW_TEST_LOG=str(self.log),
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

    def run_w(self, *args, **env):
        return subprocess.run([str(WSWIDGETS), *args], env=dict(self.env, **env), text=True,
                              capture_output=True, stdin=subprocess.DEVNULL)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_list_shows_states_and_choices_missing_from_the_catalog(self):
        self.list.write_text('yes = ["example", "gone"]\nno = ["clock"]\n')
        result = self.run_w("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wswidgets aaaaaaa", result.stdout)
        rows = {line.split()[0]: line.split()[1] for line in result.stdout.splitlines()[1:]}
        self.assertEqual(rows, {"example": "yes", "compact": "ask", "clock": "no", "gone": "yes"})
        self.assertIn("not in this wswidgets version", result.stdout)

    def test_enabled_is_this_host_yes_in_order(self):
        self.list.write_text('# c\nyes = ["compact", "clock"]\n')
        self.other.write_text('yes = ["example"]\n')
        self.assertEqual(self.run_w("enabled").stdout.split(), ["compact", "clock"])

    def test_enable_marks_yes_and_switches(self):
        self.list.write_text('# mine\nno = ["example"]\n')
        result = self.run_w("enable", "example", "clock")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.list.read_text(), '# mine\nno = []\nyes = ["example", "clock"]\n')
        self.assertEqual(self.calls(), ["switch"])

    def test_enable_no_switch_and_unknown_id(self):
        self.assertEqual(self.run_w("enable", "-n", "compact").returncode, 0)
        self.assertEqual(self.calls(), [])
        result = self.run_w("enable", "nope", "example")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no widget nope", result.stderr)
        self.assertIn('yes = ["compact"]', self.list.read_text())

    def test_disable_marks_no(self):
        self.list.write_text('yes = ["example", "compact"]\n')
        self.other.write_text('yes = ["compact"]\n')
        result = self.run_w("disable", "-n", "example", "compact")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.list.read_text(), 'yes = []\nno = ["example", "compact"]\n')
        self.assertEqual(self.other.read_text(), 'yes = ["compact"]\n')
        self.assertNotEqual(self.run_w("disable", "clock").returncode, 0)

    def test_without_layer(self):
        self.list.write_text('no = ["example"]\n')
        result = self.run_w("enable", "example", WSWIDGETS_FACT="no")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('widgets = "no"', result.stderr)
        result = self.run_w("apply", WSWIDGETS_FACT="no")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.list.read_text(), 'no = ["example"]\n')

    def test_apply_without_terminal_leaves_ask(self):
        self.list.write_text('yes = ["example"]\n')
        result = self.run_w("apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("compact clock", result.stderr)
        self.assertEqual(self.list.read_text(), 'yes = ["example"]\n')
        self.assertEqual(self.calls(), [])

    def test_apply_after_ws_apply_asked_offers_nothing(self):
        self.list.write_text('yes = ["example"]\n')
        result = self.run_w("apply", WS_OFFERED="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no widgets to offer on test", result.stdout)

    def test_apply_with_nothing_to_offer(self):
        self.list.write_text('yes = ["example", "compact"]\nno = ["clock"]\n')
        result = self.run_w("apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no widgets to offer on test", result.stdout)

    def test_update_moves_lock_and_switches_without_committing(self):
        self.list.write_text('yes = ["example"]\n')
        result = self.run_w("update", NEW_REV="b" * 40)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("aaaaaaa -> bbbbbbb", result.stdout)
        self.assertIn("compare/" + "a" * 40 + "..." + "b" * 40, result.stdout)
        self.assertEqual(self.calls()[-1], "switch")
        head = subprocess.run(["git", "-C", str(self.repo), "log", "-1", "--format=%s"],
                              text=True, capture_output=True).stdout.strip()
        self.assertEqual(head, "init")
        self.assertIn('"rev": "' + "b" * 40, (self.repo / "flake.lock").read_text().replace('":"', '": "'))
        self.assertIn("not published (ws sync)", result.stdout)

    def test_update_refuses_to_drop_an_enabled_widget(self):
        self.other.write_text('yes = ["compact"]\n')
        smaller = self.catalog.with_name("new.json")
        smaller.write_text(json.dumps(CATALOG[:1]))
        before = (self.repo / "flake.lock").read_text()
        result = self.run_w("update", NEW_REV="b" * 40, NEW_CATALOG=str(smaller))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no compact", result.stderr)
        self.assertEqual((self.repo / "flake.lock").read_text(), before)
        self.assertNotIn("switch", self.calls())

    def test_update_restores_lock_when_switch_fails(self):
        before = (self.repo / "flake.lock").read_text()
        result = self.run_w("update", NEW_REV="b" * 40, SWITCH_RC="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.repo / "flake.lock").read_text(), before)

    def test_update_when_newest(self):
        result = self.run_w("update", NEW_REV="a" * 40)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("is the newest", result.stdout)

    def test_usage(self):
        self.assertEqual(self.run_w("what").returncode, 64)
        self.assertEqual(self.run_w("help").returncode, 0)


if __name__ == "__main__":
    unittest.main()
