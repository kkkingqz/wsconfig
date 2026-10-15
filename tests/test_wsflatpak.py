import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


APP = "org.example.App"
RUNTIME = "org.gnome.Platform/x86_64/48"
APP_REF = "app/org.example.App/x86_64/stable"
OTHER = "org.example.Other"
OTHER_REF = "app/org.example.Other/x86_64/stable"
BETA_REF = "app/org.example.App/x86_64/beta"
OTHER_RUNTIME = "org.freedesktop.Platform/x86_64/24.08"
SCRIPT = Path(__file__).resolve().parents[1] / "libexec/wsflatpak"


class FlatpakState:
    """External CLI double with branches, runtimes and automatic pinning."""

    def __init__(self, system_runtime=False, user_runtime=False, app=False):
        self.system_runtime = system_runtime
        self.apps = {APP_REF: RUNTIME} if app else {}
        self.catalog = {APP_REF: RUNTIME, OTHER_REF: OTHER_RUNTIME,
                        BETA_REF: OTHER_RUNTIME}
        self.runtimes = {RUNTIME} if user_runtime else set()
        self.pins = set()
        self.runtime_installs = 0
        self.fail_runtime_install = False
        self.empty_runtime = False
        self.origin = "flathub"
        self.remotes = ["flathub"]
        self.runtime_remotes = {"flathub"}
        self.runtime_source = None
        self.fuzzy_selection = None

    @property
    def app(self):
        return APP_REF in self.apps

    @property
    def user_runtime(self):
        return RUNTIME in self.runtimes

    def run(self, args, **kwargs):
        if "--user" not in args or "--system" in args:
            raise AssertionError(f"Expected a user installation: {args}")
        command = args[1]
        code, output = 0, ""
        if command == "remotes":
            output = "\n".join(self.remotes) + "\n"
        elif command == "remote-info":
            code = 0 if args[-2] in self.runtime_remotes else 1
        elif command == "list":
            if "--columns=ref" in args:
                # Flatpak's ref column omits the app/ prefix.
                output = "\n".join(r.removeprefix("app/") for r in sorted(self.apps))
            else:
                output = "\n".join(ref.split("/")[1] for ref in self.apps)
        elif command == "info":
            ref = args[-1]
            if ref.startswith("runtime/") or ref in (RUNTIME, OTHER_RUNTIME):
                code = 0 if ref.removeprefix("runtime/") in self.runtimes else 1
            else:
                matches = [r for r in self.apps
                           if r == ref or r.split("/")[1] == ref]
                code = 0 if len(matches) == 1 else 1
                if code == 0:
                    if "--show-runtime" in args and not self.empty_runtime:
                        output = self.apps[matches[0]] + "\n"
                    if "--show-origin" in args:
                        output = self.origin + "\n"
        elif command == "install":
            ref = args[-1]
            if ref.startswith("runtime/"):
                if args[-2] not in self.runtime_remotes:
                    if len(self.runtime_remotes) != 1:
                        return subprocess.CompletedProcess(args, 1, "", "")
                self.runtime_source = args[-2]
                self.runtime_installs += 1
                if self.fail_runtime_install:
                    code = 7
                else:
                    runtime = ref.removeprefix("runtime/")
                    self.runtimes.add(runtime)
                    if "--no-auto-pin" not in args:
                        self.pins.add(runtime)
            else:
                for index, token in enumerate(args):
                    for app_ref, runtime in self.catalog.items():
                        branch = app_ref.split("/")[-1]
                        requested_branch = (args[index + 1]
                                            if index + 1 < len(args)
                                            and args[index + 1] == "beta"
                                            else "stable")
                        if (token == "org.example" and app_ref == self.fuzzy_selection
                                or token == app_ref or (token == app_ref.split("/")[1]
                                                and branch == requested_branch)):
                            self.apps[app_ref] = runtime
                            if not self.system_runtime:
                                self.runtimes.add(runtime)
        elif command == "uninstall" and "--unused" in args:
            self.runtimes.intersection_update(set(self.apps.values()) | self.pins)
        elif command == "uninstall":
            for ref in [r for r in self.apps if r.split("/")[1] == args[-1]]:
                del self.apps[ref]
        elif command not in ("override", "remote-add"):
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, code, output, "")


class UserRuntimeTests(unittest.TestCase):
    def declare(self, *apps, default=None):
        """The flatpak.json of ws switch and catalog.toml with these flathub
        apps (DEFAULT: the default of each)."""
        self.manifest.write_text(json.dumps({
            "remotes": {"flathub": "https://example.org/repo"},
            "apps": [{"remote": "flathub", "app": a} for a in apps], "overrides": {}}))
        self.catalog.write_text('[remotes]\nflathub = "https://example.org/repo"\n' + "".join(
            f'\n[[apps]]\nid = "{a}"\nremote = "flathub"\n'
            + (f'default = "{default}"\n' if default else "") for a in apps))

    def choose(self, text):
        """hosts/test/flatpak.toml."""
        self.host.write_text(text)

    def chosen(self):
        import tomllib
        data = tomllib.loads(self.host.read_text()) if self.host.exists() else {}
        return data.get("yes", []), data.get("no", [])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        cfg = root / "cfg"
        cfg.mkdir()
        self.manifest = cfg / "flatpak.json"
        config = root / "config"
        (config / "flatpak").mkdir(parents=True)
        (config / "hosts/test").mkdir(parents=True)
        self.catalog = config / "flatpak/catalog.toml"
        self.host = config / "hosts/test/flatpak.toml"
        self.declare(APP)
        self.g = runpy.run_path(str(SCRIPT))["cmd_install"].__globals__
        self.g.update(MANIFEST=cfg / "flatpak.json", REPO=config,
                      this_host=lambda: "test", cmd_check=lambda: 0)
        self.addCleanup(patch.stopall)
        # The commands apply their module themselves (ws apply flatpak).
        self.applied = []
        patch.object(self.g["ws_common"], "apply_module",
                     side_effect=lambda *m: self.applied.append(m)).start()
        # No terminal: apply asks nothing (apps not offered stay so).
        patch.object(self.g["ws_ui"], "open_tty", return_value=None).start()
        patch("shutil.which", return_value="/fake/flatpak").start()
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def execute(self, state, command="install", unmanaged=False, extra=None, app=APP):
        with patch("subprocess.run", side_effect=state.run):
            if command == "apply":
                return self.g["cmd_apply"]()
            return self.g["cmd_install"](SimpleNamespace(
                remote="flathub", app=app, extra=extra or [], unmanaged=unmanaged))

    def test_install_copies_system_only_runtime_to_user(self):
        state = FlatpakState(system_runtime=True)
        self.execute(state)
        self.assertTrue(state.user_runtime)

    def test_install_with_no_runtime_downloads_user_dependency(self):
        state = FlatpakState()
        self.execute(state)
        self.assertTrue(state.app)
        self.assertTrue(state.user_runtime)

    def test_install_preserves_existing_user_runtime_without_reinstall(self):
        state = FlatpakState(user_runtime=True, system_runtime=True)
        self.execute(state)
        self.assertTrue(state.user_runtime)
        self.assertEqual(state.runtime_installs, 0)

    def test_unmanaged_install_also_has_user_runtime(self):
        state = FlatpakState(system_runtime=True)
        self.execute(state, unmanaged=True)
        self.assertTrue(state.user_runtime)

    def test_apply_repairs_existing_app_using_system_runtime(self):
        state = FlatpakState(system_runtime=True, app=True)
        self.execute(state, "apply")
        self.assertTrue(state.user_runtime)

    def test_apply_installs_app_yes_on_this_host(self):
        state = FlatpakState(system_runtime=True)
        self.choose(f'yes = ["{APP}"]\n')
        self.execute(state, "apply")
        self.assertTrue(state.app)

    def test_apply_follows_the_default_without_a_choice(self):
        state = FlatpakState(system_runtime=True)
        self.declare(APP, default="yes")
        self.execute(state, "apply")
        self.assertTrue(state.app)
        # Installed by the default: no choice written.
        self.assertFalse(self.host.exists())

    def test_apply_leaves_declined_app_alone(self):
        state = FlatpakState(system_runtime=True)
        self.declare(APP, default="yes")
        self.choose(f'no = ["{APP}"]\n')
        self.execute(state, "apply")
        self.assertFalse(state.app)

    def test_not_offered_app_waits_for_a_terminal(self):
        state = FlatpakState(system_runtime=True)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.execute(state, "apply")
        self.assertFalse(state.app)
        self.assertIn(f"no terminal to ask): {APP};", err.getvalue())
        self.assertFalse(self.host.exists())

    def test_answer_is_written_for_this_host(self):
        state = FlatpakState(system_runtime=True)
        self.choose("# mine\n")
        with patch.object(self.g["ws_ui"], "offer", return_value=[APP]):
            self.execute(state, "apply")
        self.assertTrue(state.app)
        self.assertEqual(self.chosen(), ([APP], []))
        self.assertTrue(self.host.read_text().startswith("# mine\n"))
        state = FlatpakState(system_runtime=True)
        self.choose("")
        with patch.object(self.g["ws_ui"], "offer", return_value=[]):
            self.execute(state, "apply")
        self.assertFalse(state.app)
        self.assertEqual(self.chosen(), ([], [APP]))

    def test_cancel_answers_only_the_question(self):
        state = FlatpakState(system_runtime=True)
        self.declare(APP, OTHER)
        self.choose(f'yes = ["{APP}"]\n')
        with patch.object(self.g["ws_ui"], "offer", return_value=None), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertFalse(self.execute(state, "apply"))
        self.assertIn("choice cancelled", err.getvalue())
        self.assertEqual(state.apps.keys(), {APP_REF})
        self.assertEqual(self.host.read_text(), f'yes = ["{APP}"]\n')

    def test_remove_resolves_the_host_before_uninstalling(self):
        state = FlatpakState(system_runtime=True, app=True)
        self.choose(f'yes = ["{APP}"]\n')

        def unknown():
            raise SystemExit("ws host: unknown workstation")
        self.g["this_host"] = unknown
        with patch("subprocess.run", side_effect=state.run), self.assertRaises(SystemExit):
            self.g["cmd_remove"](SimpleNamespace(app=APP, keep_data=True))
        self.assertTrue(state.app)
        self.assertEqual(self.chosen(), ([APP], []))

    def test_installed_app_without_choice_goes_to_yes(self):
        state = FlatpakState(system_runtime=True, app=True)
        self.execute(state, "apply")
        self.assertEqual(self.chosen(), ([APP], []))

    def test_install_puts_a_catalog_app_in_yes(self):
        state = FlatpakState(system_runtime=True)
        self.choose(f'no = ["{APP}"]\n')
        self.execute(state)
        self.assertEqual(self.chosen(), ([APP], []))
        self.assertEqual(self.catalog.read_text().count("[[apps]]"), 1)
        # Once, after the choice: ws apply flatpak builds and applies it.
        self.assertEqual(self.applied, [("flatpak",)])

    def test_install_adds_a_new_app_to_the_catalog(self):
        state = FlatpakState(system_runtime=True)
        self.declare()
        self.catalog.write_text(self.catalog.read_text() + "# end\n")
        self.execute(state)
        text = self.catalog.read_text()
        self.assertIn("# end\n", text)
        self.assertIn(f'\n[[apps]]\nid = "{APP}"\nremote = "flathub"\n', text)
        self.assertEqual(self.chosen(), ([APP], []))

    def test_remove_puts_it_in_no(self):
        state = FlatpakState(system_runtime=True, app=True)
        self.choose(f'yes = ["{APP}"]\n')
        with patch("subprocess.run", side_effect=state.run):
            self.g["cmd_remove"](SimpleNamespace(app=APP, keep_data=True))
        self.assertEqual(self.chosen(), ([], [APP]))
        self.assertIn(APP, self.catalog.read_text())
        self.assertEqual(self.applied, [("flatpak",)])

    def test_unmanage_drops_the_app_everywhere(self):
        self.declare(APP, OTHER)
        self.choose(f'yes = ["{APP}", "{OTHER}"]\n')
        other = self.host.parent.parent / "other"
        other.mkdir()
        (other / "flatpak.toml").write_text(f'no = ["{APP}"]\n')
        self.g["list_remove"](APP)
        self.assertNotIn(APP, self.catalog.read_text())
        self.assertEqual(self.chosen(), ([OTHER], []))
        self.assertNotIn(APP, (other / "flatpak.toml").read_text())

    def test_runtime_install_failure_propagates(self):
        state = FlatpakState(system_runtime=True)
        state.fail_runtime_install = True
        with self.assertRaises(SystemExit) as error:
            self.execute(state)
        self.assertEqual(error.exception.code, 7)

    def test_empty_runtime_metadata_is_an_error(self):
        state = FlatpakState()
        state.empty_runtime = True
        with self.assertRaises(SystemExit):
            self.execute(state)

    def test_apply_selects_origin_when_multiple_remotes_provide_runtime(self):
        state = FlatpakState(system_runtime=True, app=True)
        state.remotes = ["another", "flathub"]
        state.runtime_remotes = {"another", "flathub"}
        self.execute(state, "apply")
        self.assertTrue(state.user_runtime)
        self.assertEqual(state.runtime_source, "flathub")

    def test_runtime_uses_other_user_remote_when_origin_has_only_app(self):
        state = FlatpakState(system_runtime=True)
        state.remotes = ["flathub", "other"]
        state.runtime_remotes = {"other"}
        self.execute(state)
        self.assertTrue(state.user_runtime)
        self.assertEqual(state.runtime_source, "other")

    def test_missing_runtime_in_user_remotes_fails(self):
        state = FlatpakState(system_runtime=True)
        state.runtime_remotes = set()
        with self.assertRaises(SystemExit):
            self.execute(state)

    def test_copied_runtime_is_removed_by_cleanup_when_unused(self):
        state = FlatpakState(system_runtime=True)
        self.execute(state)
        state.apps.clear()
        with patch("subprocess.run", side_effect=state.run), patch(
            "sys.argv", ["wsflatpak", "cleanup"]
        ):
            self.g["main"]()
        self.assertNotIn(RUNTIME, state.runtimes)

    def test_batch_install_ensures_both_user_runtimes(self):
        state = FlatpakState(system_runtime=True)
        self.execute(state, extra=[OTHER])
        self.assertEqual(state.runtimes, {RUNTIME, OTHER_RUNTIME})
        self.assertIn(OTHER, self.chosen()[0])

    def test_batch_reinstall_ensures_existing_apps_runtimes(self):
        state = FlatpakState(system_runtime=True, app=True)
        state.apps[OTHER_REF] = OTHER_RUNTIME
        self.execute(state, extra=[OTHER])
        self.assertEqual(state.runtimes, {RUNTIME, OTHER_RUNTIME})

    def test_install_second_branch_ensures_exact_runtime(self):
        state = FlatpakState(system_runtime=True, app=True)
        self.execute(state, unmanaged=True, extra=["beta"])
        self.assertIn(OTHER_RUNTIME, state.runtimes)

    def test_install_full_ref_ensures_runtime(self):
        state = FlatpakState(system_runtime=True, app=True)
        self.execute(state, unmanaged=True, app=BETA_REF)
        self.assertIn(OTHER_RUNTIME, state.runtimes)

    def test_apply_ensures_runtimes_of_both_managed_branches(self):
        state = FlatpakState(system_runtime=True, app=True)
        state.apps[BETA_REF] = OTHER_RUNTIME
        self.execute(state, "apply")
        self.assertEqual(state.runtimes, {RUNTIME, OTHER_RUNTIME})

    def test_managed_app_presence_and_origin_support_multiple_branches(self):
        state = FlatpakState(system_runtime=True, app=True)
        state.apps[BETA_REF] = OTHER_RUNTIME
        with patch("subprocess.run", side_effect=state.run):
            self.assertTrue(self.g["installed_user"](APP))
            self.assertEqual(self.g["installed_origin"](APP), "flathub")

    def test_existing_runtime_pin_is_preserved(self):
        state = FlatpakState(system_runtime=True, user_runtime=True)
        state.pins.add(RUNTIME)
        self.execute(state)
        self.assertIn(RUNTIME, state.pins)

    def test_unique_new_app_resolves_interactive_fuzzy_install(self):
        state = FlatpakState(system_runtime=True)
        state.apps[OTHER_REF] = OTHER_RUNTIME
        state.fuzzy_selection = APP_REF
        self.execute(state, unmanaged=True, app="org.example")
        self.assertIn(RUNTIME, state.runtimes)



if __name__ == "__main__":
    unittest.main()
