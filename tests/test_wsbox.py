"""wsbox apply, create, remove and check against the workstation marks of
nix/hosts/HOST/boxes.toml, with podman and distrobox replaced by shell stubs: a
container is a file in the state directory. The checklist runs on a real
pseudo terminal (pty.fork gives wsbox a controlling terminal)."""
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
WSBOX = ROOT / "bin/wsbox"

STUB = r'''#!/usr/bin/env bash
# podman and distrobox for wsbox: containers are files in $WSBOX_TEST_STATE.
state="$WSBOX_TEST_STATE"
echo "${0##*/} $*" >> "$state/.calls"
case "${0##*/}" in
    podman)
        case "$1 ${2:-}" in
            "container exists") [[ -e "$state/$3" ]] ;;
            "info "*) echo true ;;
            *) exit 1 ;;
        esac ;;
    distrobox)
        case "$1" in
            assemble)
                while (($#)); do [[ "$1" == --name ]] && touch "$state/$2"; shift; done ;;
            rm) rm -f "$state/${!#}" ;;
            *) exit 1 ;;
        esac ;;
esac
'''

CONTAINERS = "[a]\nimage=img-a\n\n[b]\nimage=img-b\n\n[c]\nimage=img-c\n"


class WsboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
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
            (config / "nix/hosts" / host).mkdir(parents=True)
        self.hosts = config / "nix/hosts/test/boxes.toml"
        self.other = config / "nix/hosts/other/boxes.toml"
        self.env = dict(os.environ, PATH=f"{stubs}:{os.environ['PATH']}",
                        WSBOX_CONFIG=str(cfg), WSCONFIG=str(config),
                        WSBOX_TEST_STATE=str(self.state), XDG_RUNTIME_DIR=str(root / "run"),
                        WS_HOST="test")

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

    def wsbox_tty(self, keys, *args):
        """wsbox ARGS on a pseudo terminal; KEYS are typed one chunk at a
        time once the question is on the screen. Returns (exit code, screen)."""
        pid, master = pty.fork()
        if pid == 0:
            try:
                os.execve(str(WSBOX), [str(WSBOX), *args], self.env)
            finally:
                os._exit(127)
        screen, keys = b"", list(keys)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if keys and b"[Y/n]" in screen:
                time.sleep(0.02)
                os.write(master, keys.pop(0).encode())
            if not select.select([master], [], [], 0.05)[0]:
                continue
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if not data:
                break
            screen += data
        os.close(master)
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status), screen.decode(errors="replace")

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
        # Offered: b, c (ask); uncheck b, keep c.
        code, screen = self.wsbox_tty(["n\n", " ", "\r"], "apply")
        self.assertEqual(code, 0, screen)
        self.assertIn("Поставить все? [Y/n]", screen)
        self.assertEqual(self.containers(), {"c"})
        self.assertEqual(self.hosts.read_text(), 'no = ["a", "b"]\nyes = ["c"]\n')

    def test_select_offers_declined_unchecked(self):
        self.marks('no = ["a"]\nyes = ["b"]\n')
        self.exists("b")
        code, screen = self.wsbox_tty(["\n"], "apply", "--select")
        self.assertEqual(code, 0, screen)
        self.assertIn("(отказались)", screen)
        # a (declined) and c (default no) were offered and taken.
        self.assertEqual(self.containers(), {"a", "b", "c"})
        self.assertEqual(self.hosts.read_text(), 'no = []\nyes = ["b", "a", "c"]\n')

    def test_cancel_answers_only_the_question(self):
        self.marks('yes = ["a"]\n')
        self.defaults(c="ask")
        self.exists("b")
        code, screen = self.wsbox_tty(["n\n", "\x1b"], "apply")
        self.assertEqual(code, 0, screen)
        self.assertIn("выбор отменён", screen)
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
        self.assertIn("WARN  nix/hosts/test/boxes.toml chooses an undeclared container: ghost", out)

    def test_check_default_no_is_declined(self):
        self.marks('yes = ["a", "b"]\n')
        out = self.wsbox("check").stdout
        self.assertIn("INFO  managed container declined on test: c", out)


def ws_catalog_yes(path):
    import tomllib
    return tomllib.loads(path.read_text()).get("yes", [])


if __name__ == "__main__":
    unittest.main()
