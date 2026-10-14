"""ws update: nix through ws apply, flake.lock back only when nothing was
applied (ws help plan-v2, stage 6); extensions."""
import tempfile
import unittest

from ws_fixture import Workspace

MODULES = ("ws-gnome", "ws-tiling-apply", "ws-keyboard-apply", "wsflatpak", "wsbox", "wswidgets")


class UpdateTests(unittest.TestCase):
    SPLIT = False

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Workspace(tmp.name, split=self.SPLIT, modules={m: "exit 0\n" for m in MODULES})
        self.initial = self.w.git("rev-parse", "HEAD")
        (self.w.repo / "flatpak/catalog.toml").write_text('[remotes]\nflathub = "u"\n')
        self.w.stub("gdbus", 'exit "${DBUS_STATUS:-0}"\n', where="bin")
        extensions = self.w.root / ".local/share/wsconfig/gnome"
        extensions.mkdir(parents=True)
        (extensions / "extensions.json").write_text(
            '{"order": ["example@local"], "by_source": {"local": ["example@local"]}, "pins": {}}')

    def update(self, step="nix", **env):
        return self.w.ws("update", step, **env)

    def test_failed_activation_keeps_the_new_lock(self):
        rc, out, err = self.update(SWITCH_STATUS="42")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("FAIL  nix (exit 1)", out)
        self.assertIn("flake.lock stays new", err)
        self.assertTrue(any("#home-manager" in c for c in self.w.take_calls()))
        self.assertEqual(self.w.git("rev-parse", "HEAD"), self.initial)

    def test_failed_build_restores_the_lock(self):
        rc, out, err = self.update(BUILD_STATUS="41")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("flake.lock restored", err)
        self.assertFalse(any(c.startswith("nix run") and "home-manager" in c for c in self.w.take_calls()))

    def test_success_names_what_is_not_published(self):
        rc, out, err = self.update()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("OK    nix", out)
        # Nothing is committed: ws sync publishes (ws help plan-v2, 2.7).
        self.assertEqual(self.w.git("rev-parse", "HEAD"), self.initial)
        self.assertIn("not published: flatpak/catalog.toml (ws sync)", out)

    def test_failed_extension_update_is_reported(self):
        rc, out, _ = self.update("extensions", DBUS_STATUS="42")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("FAIL  extensions (exit 42)", out)


class SplitUpdateTests(UpdateTests):
    """The tests that read paths, with the configuration apart from the
    core (ws help plan-v2, 8.1); the rest does not depend on it."""
    SPLIT = True
    test_failed_activation_keeps_the_new_lock = None
    test_failed_extension_update_is_reported = None


if __name__ == "__main__":
    unittest.main()
