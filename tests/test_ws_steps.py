"""ws apply, update and check walk their step tables (helpws plan-v2, 2.5
and stage 6): the order of apply, the names, the summary."""
import json
import tempfile
import unittest

from ws_fixture import Workspace

APPLY = {"ws-gnome": 0, "ws-tiling-apply": 69, "ws-keyboard-apply": 3,
         "wsflatpak": 0, "wsbox": 0, "wswidgets": 0}
CHECK = ["ws-check-repo", "ws-check-home", "ws-keyboard", "ws-gnome", "wsflatpak", "wsbox", "wswin",
         "ws-suspend", "wsgame", "ws-workstation-verify"]
RESULT = json.dumps({"status": "warn", "passes": 1, "warnings": 1, "failures": 0,
                     "messages": [{"level": "warn", "text": "w"}]})


class StepsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Workspace(tmp.name)
        for name, rc in APPLY.items():
            self.w.stub(name, f'echo "{name} $* applying=${{WS_APPLYING:-}} offered=${{WS_OFFERED:-}}"\n'
                              f'[ "$1" = check ] && echo \'{RESULT}\' && exit 0\nexit {rc}\n')
        for name in CHECK:
            if name not in APPLY:
                self.w.stub(name, f"echo '{RESULT}'\n")

    def ws(self, *args, **env):
        return self.w.ws(*args, **env)

    def headers(self, out):
        return [l for l in out.splitlines() if l.startswith("===")]

    def test_apply_all_in_order(self):
        rc, out, _ = self.ws("apply")
        self.assertEqual(rc, 1)
        self.assertEqual(self.headers(out), [
            "=== choices: ws_catalog offer --all flatpak boxes widgets",
            "=== build: home-manager generation, system tree",
            "=== home: home-manager switch",
            "=== extensions: ws-gnome extensions", "=== tiling: ws-tiling-apply",
            "=== keyboard: ws-keyboard-apply", "=== flatpak: wsflatpak apply",
            "=== distrobox: wsbox apply", "=== widgets: wswidgets apply", "=== ws apply"])
        summary = out[out.index("=== ws apply"):].splitlines()
        self.assertEqual(summary[1:12], [
            "  OK        choices", "  OK        build", "  OK        apt (nothing to do)",
            "  OK        system (nothing to do)", "  OK        home", "  OK        extensions",
            "  PREFLIGHT tiling", "  FAIL      keyboard (exit 3)", "  OK        flatpak",
            "  OK        distrobox", "  OK        widgets"])
        self.assertIn("    log out and in, then: ws apply tiling", summary)
        # The module steps run inside ws apply and ask nothing.
        self.assertIn("wsflatpak apply applying=1 offered=1", out)

    def test_named_steps_run_the_nix_stages_and_only_them(self):
        rc, out, _ = self.ws("apply", "widgets", "extensions")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.headers(out), [
            "=== choices: ws_catalog offer --all widgets",
            "=== build: home-manager generation, system tree", "=== home: home-manager switch",
            "=== extensions: ws-gnome extensions", "=== widgets: wswidgets apply", "=== ws apply"])
        self.assertNotIn("apt", out[out.index("=== ws apply"):])

    def test_home_alone(self):
        rc, out, _ = self.ws("apply", "home")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("choices", out)
        self.assertEqual(self.headers(out)[-2:], ["=== home: home-manager switch", "=== ws apply"])

    def test_pending_system_not_named_is_left(self):
        (self.w.state / "system-todo").write_text("file: /etc/x\nfile: /etc/y\n")
        rc, out, _ = self.ws("apply", "home")
        self.assertEqual(rc, 0, out)
        self.assertIn("    ws apply system: 2 to do", out)
        self.assertFalse(any(c.startswith("sudo") for c in self.w.take_calls()))
        rc, out, _ = self.ws("apply", "system")
        self.assertIn("  OK        system", out)
        self.assertIn("to do: file: /etc/x", out)

    def test_failed_build_applies_nothing(self):
        (self.w.state / "system-todo").write_text("file: /etc/x\n")
        rc, out, _ = self.ws("apply", BUILD_STATUS="1")
        self.assertEqual(rc, 2)
        self.assertIn("  FAIL      build", out)
        self.assertIn("  nothing applied", out)
        calls = self.w.take_calls()
        self.assertFalse(any("#home-manager" in c or c.startswith(("sudo", "ws-system apply")) for c in calls))

    def test_failed_home_skips_the_modules(self):
        rc, out, _ = self.ws("apply", "flatpak", SWITCH_STATUS="1")
        self.assertEqual(rc, 1)
        self.assertIn("  FAIL      home", out)
        self.assertIn("  SKIP      flatpak (home failed)", out)

    def test_records_host_json(self):
        self.ws("apply", "home")
        record = json.loads((self.w.root / ".state/wsconfig/host.json").read_text())
        self.assertEqual(record, {"host": "test", "config": str(self.w.repo)})

    def test_unknown_step(self):
        rc, out, err = self.ws("apply", "nosuch")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("ws: unknown apply step: nosuch (steps: home apt system extensions", err)
        rc, out, err = self.ws("update", "nosuch")
        self.assertEqual((rc, out, err), (1, "", "ws: unknown update step: nosuch\n"))

    def test_switch_is_gone(self):
        rc, _, err = self.ws("switch")
        self.assertEqual(rc, 1)
        self.assertIn("ws switch is gone: ws apply", err)

    def test_check_summary(self):
        rc, out, _ = self.ws("check")
        lines = out.splitlines()
        self.assertIn("=== repo: ws-check-repo (exit 0)", lines)
        self.assertIn("  WARN  w", lines)
        tail = lines[lines.index("=== ws check"):]
        self.assertEqual(tail[1], "  WARN  repo (1)")
        self.assertRegex(tail[-1], r"^  FAIL=\d+ WARN=\d+$")

    def test_steps_lists(self):
        self.assertEqual(self.ws("steps", "apply")[1].split(),
                         ["home", "apt", "system", "extensions", "tiling", "keyboard", "flatpak",
                          "distrobox", "widgets"])


class IdempotenceTests(unittest.TestCase):
    """A second ws apply with nothing changed installs nothing and asks no
    sudo (helpws plan-v2, stage 6)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        modules = {name: f'echo "{name} $*" >> "$CALLS"\n' for name in
                   ("ws-gnome", "ws-tiling-apply", "ws-keyboard-apply", "wsflatpak", "wsbox", "wswidgets")}
        self.w = Workspace(tmp.name, modules=modules)
        (self.w.repo / "nix/hosts/test/apt.txt").write_text("pkg-a\npurge:old-b\n")
        (self.w.state / "installed").write_text("old-b\n")
        (self.w.state / "system-todo").write_text("file: /etc/x\n")
        self.w.git("add", ".")
        self.w.git("commit", "-qm", "lists")

    def test_second_run_changes_nothing(self):
        rc, out, err = self.w.ws("apply")
        self.assertEqual(rc, 0, out + err)
        first = self.w.take_calls()
        self.assertTrue(any(c.startswith("sudo apt-get") and " install " in c and "pkg-a" in c for c in first), first)
        self.assertTrue(any(c.startswith("sudo apt-get") and " purge " in c and "old-b" in c for c in first), first)
        self.assertIn("ws-system apply", first)
        # The stub keeps old-b listed as installed: purge it for real.
        (self.w.state / "installed").write_text("pkg-a\n")

        rc, out, err = self.w.ws("apply")
        self.assertEqual(rc, 0, out + err)
        second = self.w.take_calls()
        self.assertFalse([c for c in second if c.startswith("sudo")], second)
        self.assertFalse([c for c in second if "install" in c and c.startswith("apt-get")], second)
        self.assertIn("  OK        apt (nothing to do)", out)
        self.assertIn("  OK        system (nothing to do)", out)

    def test_purge_that_takes_more_stops(self):
        (self.w.state / "purge-extra").write_text("Purg needs-old-b [1]\n")
        rc, out, err = self.w.ws("apply", "apt")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("would also remove: needs-old-b", out + err)
        self.assertFalse([c for c in self.w.take_calls() if " purge -y" in c])


if __name__ == "__main__":
    unittest.main()
