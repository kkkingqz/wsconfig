"""wsbox apply, create, remove and check against the workstation marks of
hosts/HOST/boxes.toml, with podman and distrobox replaced by shell stubs: a
container is a file in the state directory. The checklist runs on the gum of
the tests (tests/fixtures/bin/gum)."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
WSBOX = ROOT / "libexec/wsbox"

STUB = r'''#!/usr/bin/env bash
# podman and distrobox for wsbox: containers are files in $WSBOX_TEST_STATE.
state="$WSBOX_TEST_STATE"
echo "${0##*/} $*" >> "$state/.calls"
case "${0##*/}" in
    podman)
        case "$1 ${2:-}" in
            "container exists") [[ -e "$state/$3" ]] ;;
            "info "*) echo true ;;
            # A test sets the state (.NAME.state) and the logs (.NAME.logs);
            # a test of the setup wait turns the logs done after N reads.
            "inspect "*) [[ -e "$state/.${!#}.state" ]] && cat "$state/.${!#}.state" || exit 1 ;;
            "logs "*)
                n="$state/.$2.reads"; echo x >> "$n"
                if [[ -e "$state/.$2.done-after" ]] && (($(wc -l < "$n") > $(cat "$state/.$2.done-after"))); then
                    echo container_setup_done
                else
                    cat "$state/.$2.logs" 2>/dev/null
                fi ;;
            *) exit 1 ;;
        esac ;;
    distrobox)
        case "$1" in
            assemble)
                while (($#)); do [[ "$1" == --name ]] && touch "$state/$2"; shift; done ;;
            rm) rm -f "$state/${!#}" ;;
            enter) [[ "${!#}" != fail ]] ;;
            *) exit 1 ;;
        esac ;;
esac
'''

CONTAINERS = "[a]\nimage=img-a\n\n[b]\nimage=img-b\n\n[c]\nimage=img-c\n"


class WsboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = self.root = Path(self.temp.name)
        self.state = root / "state"
        cfg = root / "cfg"
        stubs = root / "bin"
        for d in (self.state, cfg, stubs, root / "run"):
            d.mkdir()
        for name in ("podman", "distrobox", "distrobox-assemble"):
            (stubs / name).write_text(STUB)
            (stubs / name).chmod(0o755)
        (cfg / "containers.ini").write_text(CONTAINERS)
        self.cfg = cfg
        self.defaults()
        config = root / "config"
        for host in ("test", "other"):
            (config / "hosts" / host).mkdir(parents=True)
        self.hosts = config / "hosts/test/boxes.toml"
        self.other = config / "hosts/other/boxes.toml"
        self.env = dict(os.environ, PATH=f"{stubs}:{os.environ['PATH']}",
                        WSBOX_CONFIG=str(cfg), WSCONFIG=str(config),
                        WSBOX_TEST_STATE=str(self.state), XDG_RUNTIME_DIR=str(root / "run"),
                        WS_HOST="test", WSBOX_SETUP_POLL="0")
        # ws apply after a change of the choice: recorded, not run.
        self.applied = root / "applied"
        apply = stubs / "ws-apply"
        apply.write_text(f'#!/bin/sh\necho "$*" >> {self.applied}\n')
        apply.chmod(0o755)
        self.env["WS_APPLY_CMD"] = str(apply)

    def marks(self, text):
        self.hosts.write_text(text)

    def defaults(self, **defaults):
        """boxes.json of a, b and c; c defaults to no unless DEFAULTS say."""
        defaults = {"c": "no", **defaults}
        (self.cfg / "boxes.json").write_text(json.dumps(
            [{"name": n, "image": f"img-{n}", "home": "${HOME}/distrobox/" + n,
              "pre_init_hooks": [], "init_hooks": [], "exports": {}, "default": defaults.get(n, "ask")}
             for n in "abc"]))

    def exists(self, *names):
        for name in names:
            (self.state / name).touch()

    def containers(self):
        return {p.name for p in self.state.iterdir() if not p.name.startswith(".")}

    def wsbox(self, *args):
        """wsbox ARGS without a terminal."""
        return subprocess.run([str(WSBOX), *args], env=self.env, text=True,
                              capture_output=True, stdin=subprocess.DEVNULL)

    def wsbox_ui(self, answers, *args):
        """wsbox ARGS with the gum of the tests (lib/ws_ui.py): ANSWERS one per
        dialog (tests/fixtures/bin/gum). Returns (exit code, output, the
        arguments of each gum call)."""
        log, replies = self.root / "gum-log", self.root / "gum-answers"
        log.unlink(missing_ok=True)
        replies.write_text("".join(json.dumps(a) + "\n" for a in answers))
        env = self.env | {"WS_GUM": str(ROOT / "tests/fixtures/bin/gum"), "WS_UI_TTY": "/dev/null",
                          "WS_GUM_LOG": str(log), "WS_GUM_ANSWERS": str(replies)}
        p = subprocess.run([str(WSBOX), *args], env=env, text=True,
                           capture_output=True, stdin=subprocess.DEVNULL)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return p.returncode, p.stdout + p.stderr, calls

    def test_apply_creates_yes_marks_existing_and_waits_for_a_terminal(self):
        self.marks('# mine\nyes = ["a"]\n')
        self.exists("b")
        p = self.wsbox("apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.containers(), {"a", "b"})
        # c defaults to no: nothing to offer, no question.
        self.assertNotIn("no terminal", p.stderr)
        # b existed in state ask: yes now.
        self.assertEqual(self.hosts.read_text(), '# mine\nyes = ["a", "b"]\nno = []\n')

    def test_apply_without_terminal_names_the_offered(self):
        self.marks('yes = ["a"]\n')
        self.defaults(c="ask")
        p = self.wsbox("apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("no terminal to ask): b c;", p.stderr)
        self.assertEqual(self.hosts.read_text(), 'yes = ["a"]\n')

    def test_apply_asks_and_writes_the_answer(self):
        self.marks('no = ["a"]\n')
        self.defaults(c="ask")
        # Offered: b, c (ask), both checked; uncheck b, keep c.
        code, out, calls = self.wsbox_ui([["c"]], "apply")
        self.assertEqual(code, 0, out)
        self.assertEqual([a for a in calls[0] if a.startswith("--selected=")],
                         ["--selected=b  img-b", "--selected=c  img-c"])
        self.assertEqual(self.containers(), {"c"})
        self.assertEqual(self.hosts.read_text(), 'no = ["a", "b"]\nyes = ["c"]\n')

    def test_select_offers_declined_unchecked(self):
        self.marks('no = ["a"]\nyes = ["b"]\n')
        self.exists("b")
        code, out, calls = self.wsbox_ui([["a", "c"]], "apply", "--select")
        self.assertEqual(code, 0, out)
        # a (declined) and c (default no) were offered unchecked, then taken.
        self.assertIn("a  img-a (declined)\ta", calls[0])
        self.assertFalse([a for a in calls[0] if a.startswith("--selected=")])
        self.assertEqual(self.containers(), {"a", "b", "c"})
        self.assertEqual(self.hosts.read_text(), 'no = []\nyes = ["b", "a", "c"]\n')

    def test_cancel_answers_only_the_question(self):
        self.marks('yes = ["a"]\n')
        self.defaults(c="ask")
        self.exists("b")
        code, out, _ = self.wsbox_ui(["esc"], "apply")
        self.assertEqual(code, 0, out)
        self.assertIn("choice cancelled", out)
        self.assertEqual(self.containers(), {"a", "b"})
        self.assertEqual(self.hosts.read_text(), 'yes = ["a", "b"]\nno = []\n')

    def test_unreadable_choice_stops_apply(self):
        self.marks('yes = "a"\n')
        p = self.wsbox("apply")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("yes must be a list", p.stderr)
        self.assertEqual(self.containers(), set())
        calls = self.state / ".calls"
        self.assertNotIn("distrobox assemble", calls.read_text() if calls.exists() else "")

    def test_apply_name_and_create_put_it_in_yes(self):
        self.assertEqual(self.wsbox("apply", "c").returncode, 0)
        self.assertEqual(self.wsbox("create", "b").returncode, 0)
        self.assertEqual(self.containers(), {"b", "c"})
        self.assertEqual(ws_catalog_yes(self.hosts), ["c", "b"])

    def calls(self):
        path = self.state / ".calls"
        return path.read_text().splitlines() if path.exists() else []

    def test_a_new_container_is_set_up_by_the_command_that_made_it(self):
        self.marks('yes = ["a"]\n')
        self.exists("b")
        self.assertEqual(self.wsbox("apply").returncode, 0)
        self.assertEqual(self.wsbox("create", "c").returncode, 0)
        p = self.wsbox("recreate", "b")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("first start of b", p.stdout)
        # b existed at apply: no first start there.
        self.assertEqual([c for c in self.calls() if c.startswith("distrobox enter")],
                         [f"distrobox enter --name {n} -- true" for n in "acb"])
        # apply NAME of an existing container starts nothing.
        self.assertEqual(self.wsbox("apply", "a").returncode, 0)
        self.assertEqual(sum(c.startswith("distrobox enter") for c in self.calls()), 3)

    def test_run_waits_for_the_setup_of_a_running_container(self):
        self.exists("a")
        (self.state / ".a.state").write_text("running\n")
        (self.state / ".a.logs").write_text(
            "container_setup_done\n+ x\ndistrobox: Executing init hooks...\ninstalling wine\n")
        (self.state / ".a.done-after").write_text("2\n")
        p = self.wsbox("run", "a", "wine", "x.exe")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("a is still setting up", p.stderr)
        self.assertEqual(self.calls()[-1], "distrobox enter --name a -- wine x.exe")
        self.assertEqual(len((self.state / ".a.reads").read_text().split()), 3)

    def test_run_does_not_wait_when_set_up_stopped_or_without_marks(self):
        self.exists("a", "b", "c")
        (self.state / ".a.state").write_text("running\n")
        (self.state / ".a.logs").write_text("distrobox: Setting up...\ncontainer_setup_done\n+ set +x\n")
        (self.state / ".b.state").write_text("exited\n")
        (self.state / ".c.state").write_text("running\n")
        for name in "abc":
            p = self.wsbox("run", name, "true")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertNotIn("setting up", p.stderr)
        self.assertFalse((self.state / ".b.reads").exists())

    def test_a_container_that_stops_during_setup_fails_the_run(self):
        self.exists("a")
        (self.state / ".a.state").write_text("running\n")
        (self.state / ".a.logs").write_text("distrobox: Installing basic packages...\n")
        env = self.env
        # Stopped after the first look at the logs.
        stub = self.root / "bin/podman"
        stub.write_text(STUB.replace('"logs "*)', '"logs "*) echo exited > "$state/.$2.state";', 1))
        p = subprocess.run([str(WSBOX), "run", "a", "true"], env=env, text=True,
                           capture_output=True, stdin=subprocess.DEVNULL)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("a stopped during its setup", p.stderr)
        self.assertNotIn("distrobox enter --name a -- true", self.calls())

    def test_remove_puts_it_in_no(self):
        self.marks('yes = ["a", "b"]\n')
        self.other.write_text('yes = ["b"]\n')
        self.exists("a", "b")
        for name in ("a", "b"):
            p = self.wsbox("remove", name)
            self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.containers(), set())
        self.assertEqual(self.hosts.read_text(), 'yes = []\nno = ["a", "b"]\n')
        self.assertEqual(self.other.read_text(), 'yes = ["b"]\n')
        # The launchers go with the next home-manager switch.
        self.assertEqual(self.applied.read_text(), "home\nhome\n")

    def test_remove_checks_host_and_choice_before_removing(self):
        self.exists("a")
        for host, text, message in (("legion.go", 'yes = ["a"]\n', "invalid workstation name"),
                                    ("test", 'yes = "a"\n', "cannot read")):
            with self.subTest(host=host):
                self.marks(text)
                self.env["WS_HOST"] = host
                p = self.wsbox("remove", "a")
                self.assertNotEqual(p.returncode, 0)
                self.assertIn(message, p.stderr)
                self.assertEqual(self.containers(), {"a"})
                self.assertEqual(self.hosts.read_text(), text)

    def test_update_without_containers_has_nothing_to_do(self):
        # Every container declined here: not an error for ws update.
        self.marks('no = ["a", "b", "c"]\n')
        result = self.wsbox("update")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing to update", result.stdout)

    def test_check_reports_by_choice(self):
        self.marks('yes = ["a", "ghost"]\nno = ["b"]\n')
        self.defaults(c="ask")
        self.exists("b")
        out = self.wsbox("check").stdout
        self.assertIn("FAIL  managed container missing: a (yes on test; ws box apply)", out)
        self.assertIn("WARN  managed container exists but no on test: b", out)
        self.assertIn("INFO  managed container not offered on test yet: c", out)
        self.assertIn("WARN  hosts/test/boxes.toml chooses an undeclared container: ghost", out)

    def test_check_default_no_is_declined(self):
        self.marks('yes = ["a", "b"]\n')
        out = self.wsbox("check").stdout
        self.assertIn("INFO  managed container declined on test: c", out)


def ws_catalog_yes(path):
    import tomllib
    return tomllib.loads(path.read_text()).get("yes", [])


if __name__ == "__main__":
    unittest.main()
