"""ws-window against a stub wsdbus-ctl (WSDBUS_CTL): which windows each
action minimizes or closes, the focused window last, stale windows and the
errors of the contract."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
WS_WINDOW = ROOT / "libexec/ws-window"

# Prints $WINDOWS for `--json windows`, logs every call; `window ID ACTION`
# exits with $STALE_STATUS for the id $STALE_ID, `--json windows` with
# $LIST_STATUS.
CTL_STUB = r'''#!/usr/bin/env bash
echo "$*" >> "$CTL_LOG"
if [[ "$1 $2" == "--json info" ]]; then
    printf '{"provider":"gnome","version":1,"capabilities":%s}\n' "${CAPABILITIES:-[\"windows\",\"WindowAction\"]}"
    exit 0
fi
if [[ "$1 $2" == "--json windows" ]]; then
    [[ -z "${LIST_STATUS:-}" ]] || { echo "wsdbus-ctl: failure" >&2; exit "$LIST_STATUS"; }
    printf '{"revision":4,"windows":%s}\n' "$WINDOWS"
    exit 0
fi
[[ "$1" == window && "$2" == "${STALE_ID:-none}" ]] && exit "${STALE_STATUS:-5}"
[[ "$1" == window ]] && exit 0
exit 2
'''


def window(id, app, focused=False, minimized=False):
    return {"id": id, "app": app, "class": app, "title": "", "workspace": "1",
            "monitor": "eDP-1", "focused": focused, "minimized": minimized,
            "maximized": False, "floating": True, "fullscreen": False}


WINDOWS = [
    window("1", "org.gnome.Ptyxis"),
    window("2", "org.gnome.Nautilus", minimized=True),
    window("3", "org.gnome.Ptyxis", focused=True),
    window("4", "org.mozilla.firefox"),
    window("5", "org.gnome.Ptyxis", minimized=True),
]


class WsWindowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.stub = tmp / "wsdbus-ctl"
        self.stub.write_text(CTL_STUB)
        self.stub.chmod(0o755)
        self.log = tmp / "log"

    def run_action(self, action, windows=WINDOWS, **env):
        full = dict(os.environ, WSDBUS_CTL=str(self.stub), CTL_LOG=str(self.log),
                    WINDOWS=json.dumps(windows), **env)
        done = subprocess.run([str(WS_WINDOW), action], env=full, text=True, capture_output=True)
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return done, [c for c in calls if c != "--json windows"]

    def test_hide_current_minimizes_the_visible_windows_of_the_app(self):
        for action in ("hide-current", "minimize-current"):
            self.log.unlink(missing_ok=True)
            done, calls = self.run_action(action)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(calls, ["window 1 minimize", "window 3 minimize"])

    def test_hide_others_minimizes_the_visible_windows_of_other_apps(self):
        done, calls = self.run_action("hide-others")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(calls, ["window 4 minimize"])

    def test_close_current_closes_the_focused_window_last(self):
        done, calls = self.run_action("close-current")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(calls, ["window 1 close", "window 5 close", "window 3 close"])

    def test_a_window_closed_meanwhile_is_skipped(self):
        done, calls = self.run_action("close-current", STALE_ID="1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(calls, ["window 1 close", "window 5 close", "window 3 close"])

    def test_no_focused_window(self):
        done, calls = self.run_action("hide-current", windows=[window("1", "a")])
        self.assertEqual(done.returncode, 1)
        self.assertIn("no focused window", done.stderr)
        self.assertEqual(calls, [])

    def test_errors_of_the_contract(self):
        for status, text in ((3, "no wsdbus provider"), (6, "locked"), (1, "failed: wsdbus-ctl: failure")):
            done, _ = self.run_action("hide-others", LIST_STATUS=str(status))
            self.assertEqual(done.returncode, 1)
            self.assertIn(text, done.stderr)
        done, _ = self.run_action("hide-others", STALE_ID="4", STALE_STATUS="6")
        self.assertEqual(done.returncode, 1)
        self.assertIn("locked", done.stderr)

    def test_check_needs_windows_and_window_action(self):
        done, _ = self.run_action("check")
        self.assertEqual(done.returncode, 0, done.stderr)
        done, _ = self.run_action("check", CAPABILITIES='["windows"]')
        self.assertEqual(done.returncode, 1)
        self.assertIn("lacks WindowAction", done.stderr)
        done, _ = self.run_action("check", LIST_STATUS="3")
        self.assertEqual(done.returncode, 0, "info is not the window list")

    def test_usage(self):
        done, _ = self.run_action("unknown")
        self.assertEqual(done.returncode, 2)
        done = subprocess.run([str(WS_WINDOW)], text=True, capture_output=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("usage: ws-window", done.stderr)


if __name__ == "__main__":
    unittest.main()
