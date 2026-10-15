"""The scripts of the configuration (ws help scripts): the catalog of
scripts/ (lib/ws_catalog.py, as lib/scripts.nix: nix flake check scripts),
ws script (libexec/wsscript) and the new files ws apply adds to Git (ws help
plan-v2, stage 10)."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import fast_tmp  # noqa: F401  (tmpfs)
from ws_fixture import Workspace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ws_catalog  # noqa: E402
import ws_select  # noqa: E402

IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t"}


def write(path, text, mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name)
        self.scripts = self.config / "scripts"

    def test_files_are_the_scripts(self):
        write(self.scripts / "b.py", "#!/usr/bin/env python3\n\n# Second one.\nprint()\n")
        write(self.scripts / "a", "#!/bin/sh\n# shellcheck disable=SC2034\n# First one.\n")
        write(self.scripts / "plain", "#!/bin/sh\necho no comment\n")
        write(self.scripts / ".hidden", "")
        write(self.scripts / "lib/common.sh", "# library\n")
        write(self.scripts / "catalog.toml",
              '[[scripts]]\nname = "plain"\ndefault = "yes"\ndescription = "Mine"\n', 0o644)
        self.assertEqual(ws_catalog.script_catalog(self.config), [
            ("a", "ask", "First one."), ("b.py", "ask", "Second one."), ("plain", "yes", "Mine")])
        self.assertEqual(ws_catalog.script_problems(self.config), [])

    def test_what_the_build_refuses(self):
        write(self.scripts / "-bad", "")
        write(self.scripts / "tools/x", "")
        write(self.scripts / "ok", "")
        write(self.scripts / "catalog.toml",
              '[[scripts]]\nname = "ok"\ndefault = "maybe"\nother = 1\n', 0o644)
        self.assertEqual([n for n, _, _ in ws_catalog.script_catalog(self.config)], ["ok"])
        problems = ws_catalog.script_problems(self.config)
        self.assertEqual(len(problems), 4, problems)
        self.assertTrue(problems[0].startswith("scripts/-bad: not a command name"))
        self.assertTrue(problems[1].startswith("scripts/tools/: no directories"))
        self.assertIn("unknown key other", problems[2])
        self.assertIn("default must be ask, no or yes", problems[3])

    def test_no_scripts_directory(self):
        self.assertEqual(ws_catalog.script_catalog(self.config), [])
        self.assertEqual(ws_catalog.script_problems(self.config), [])

    def test_the_test_configuration(self):
        # As the flake check builds it: hello yes on t2-mbp16.
        self.assertEqual(ws_catalog.script_catalog(ROOT / "tests/config"), [
            ("disk-report.py", "ask", "Free space of the mounted filesystems."),
            ("hello", "ask", "Greet the user (an example script of the test configuration).")])
        choice = ws_catalog.Choice("scripts", "t2-mbp16", ROOT / "tests/config")
        self.assertEqual((choice.yes(), choice.no()), (["hello"], ["disk-report.py"]))

    def test_setup_asks_about_the_scripts(self):
        write(self.scripts / "hello", "#!/bin/sh\n# Hi.\n")
        write(self.scripts / "never", "#!/bin/sh\n")
        write(self.scripts / "catalog.toml", '[[scripts]]\nname = "never"\ndefault = "no"\n', 0o644)
        (self.config / "flatpak").mkdir()
        (self.config / "flatpak/catalog.toml").write_text("[remotes]\n")
        (self.config / "hosts/new").mkdir(parents=True)
        asked = []

        def checklist(term, title, items, checked):
            asked.append((title, items, checked))
            return ["hello"]
        with mock.patch.object(ws_select, "checklist", checklist), \
                mock.patch.object(ws_catalog.ws_common, "git_add_new"):
            written = ws_catalog.setup(self.config, "new", io.StringIO())
        self.assertEqual(asked, [("Scripts on new", [("hello", "Hi."), ("never", "")], [True, False])])
        self.assertEqual(written, ["hosts/new/scripts.toml"])
        choice = ws_catalog.Choice("scripts", "new", self.config)
        self.assertEqual((choice.yes(), choice.no()), (["hello"], ["never"]))

    def test_apply_offer_asks_about_the_ask_scripts(self):
        write(self.scripts / "hello", "#!/bin/sh\n# Hi.\n")
        (self.config / "hosts/new").mkdir(parents=True)
        asked = []

        def choose(offered, what, unchecked, tty):
            asked.append((what, offered))
            return ["hello"]
        with mock.patch.object(ws_catalog.ws_common, "CONFIG", self.config), \
                mock.patch.object(ws_select, "choose", choose), \
                mock.patch.object(ws_catalog.ws_common, "git_add_new"):
            written = ws_catalog.apply_offer("new", ["scripts"])
        self.assertEqual(asked, [("scripts", [("hello", "Hi.")])])
        self.assertEqual([Path(p).name for p in written], ["scripts.toml"])


class WsScriptTests(unittest.TestCase):
    """libexec/wsscript on a configuration of its own, ws apply stubbed."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "config"
        self.home = self.root / "home"
        self.calls = self.root / "calls"
        self.system = self.root / "system-bin"
        self.system.mkdir()
        write(self.system / "ls", "#!/bin/sh\n")
        write(self.root / "apply", f'#!/bin/sh\necho "ws apply $*" >> {self.calls}\n')
        for host in ("test", "other"):
            (self.repo / "hosts" / host).mkdir(parents=True)
            (self.repo / "hosts" / host / "host.toml").write_text('[platform]\nboot = "grub"\n')
        (self.repo / "wsconfig.toml").write_text("schema = 1\n")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("WS", "GIT_"))}
        self.env.update(IDENTITY, HOME=str(self.home), WSCONFIG=str(self.repo), WS_HOST="test",
                        WS_APPLY_CMD=str(self.root / "apply"), WSSCRIPT_PATH=str(self.system),
                        GIT_CONFIG_GLOBAL=str(self.root / "gitconfig"), GIT_CONFIG_NOSYSTEM="1")
        (self.root / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "init")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env, check=True,
                              text=True, capture_output=True).stdout.strip()

    def script(self, *args, **env):
        # A session of its own: no /dev/tty, nothing to ask on.
        p = subprocess.run([str(ROOT / "libexec/wsscript"), *args], env=dict(self.env, **env), text=True,
                           capture_output=True, stdin=subprocess.DEVNULL, start_new_session=True)
        return p.returncode, p.stdout, p.stderr

    def applied(self):
        lines = self.calls.read_text().splitlines() if self.calls.exists() else []
        self.calls.unlink(missing_ok=True)
        return lines

    def choice(self, host="test"):
        return ws_catalog.Choice("scripts", host, self.repo)

    def link(self, name):
        """~/.local/bin/NAME as home-manager leaves it, and the manifest."""
        bin_dir = self.home / ".local/bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / name).symlink_to(self.repo / "scripts" / name)
        manifest = self.home / ".local/share/wsconfig/scripts/scripts.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        names = json.loads(manifest.read_text())["scripts"] if manifest.exists() else []
        manifest.write_text(json.dumps({"scripts": names + [name], "dir": str(self.repo / "scripts")}))

    def test_add_a_stub(self):
        rc, out, err = self.script("add", "photos-import")
        self.assertEqual(rc, 0, out + err)
        path = self.repo / "scripts/photos-import"
        self.assertTrue(os.access(path, os.X_OK))
        self.assertTrue(path.read_text().startswith("#!/usr/bin/env bash\n"))
        self.assertIn("A  scripts/photos-import", self.git("status", "--short"))
        self.assertEqual(self.choice().yes(), ["photos-import"])
        self.assertEqual(self.applied(), ["ws apply scripts"])

    def test_add_a_file_without_applying(self):
        source = self.root / "db.sh"
        write(source, "#!/bin/sh\n# Dump the db.\n", 0o644)
        rc, out, err = self.script("add", "-n", "backup-db", str(source))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual((self.repo / "scripts/backup-db").read_text(), source.read_text())
        self.assertTrue(os.access(self.repo / "scripts/backup-db", os.X_OK))
        self.assertIn("then: ws apply scripts", out)
        self.assertEqual(self.applied(), [])

    def test_add_refuses(self):
        write(self.repo / "scripts/taken", "#!/bin/sh\n")
        write(self.repo / "home/.local/bin/mine", "#!/bin/sh\n")
        for name, message in (("taken", "exists"), ("-x", "not a command name"),
                              ("lib", "not a command name"), ("ws", "the ws of the core"),
                              ("xremap", "keyboard/xremap.nix"),
                              ("mine", "home/.local/bin/mine of the configuration"),
                              ("ls", f"would hide {self.system}/ls")):
            rc, _, err = self.script("add", name)
            self.assertEqual(rc, 1, name)
            self.assertIn(message, err, name)
        self.assertEqual(self.applied(), [])

    def test_enable_disable(self):
        write(self.repo / "scripts/hello", "#!/bin/sh\n# Hi.\n")
        rc, out, err = self.script("enable", "hello")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(self.choice().yes(), ["hello"])
        rc, out, err = self.script("disable", "-n", "hello")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(self.choice().no(), ["hello"])
        self.assertEqual(self.applied(), ["ws apply scripts"])
        rc, _, err = self.script("enable", "missing")
        self.assertEqual(rc, 1)
        self.assertIn("no script missing", err)

    def test_list(self):
        write(self.repo / "scripts/hello", "#!/bin/sh\n# Hi.\n")
        write(self.repo / "scripts/other", "#!/bin/sh\n")
        (self.repo / "hosts/test/scripts.toml").write_text('yes = ["hello", "gone"]\n')
        self.link("hello")
        rc, out, err = self.script("list")
        self.assertEqual(rc, 0, out + err)
        rows = [line.split() for line in out.splitlines()[1:]]
        self.assertEqual(rows, [["hello", "yes", "linked", "Hi."], ["other", "ask", "-"],
                                ["gone", "yes", "-", "(no", "file", "in", "scripts/)"]])

    def test_delete_drops_every_choice_and_the_entry(self):
        write(self.repo / "scripts/hello", "#!/bin/sh\n")
        write(self.repo / "scripts/catalog.toml",
              '# mine\n[[scripts]]\nname = "hello"\ndefault = "yes"\n\n[[scripts]]\nname = "x"\n', 0o644)
        (self.repo / "hosts/test/scripts.toml").write_text('yes = ["hello"]\n')
        (self.repo / "hosts/other/scripts.toml").write_text('no = ["hello"]\n')
        self.git("add", ".")
        self.git("commit", "-qm", "hello")
        rc, out, err = self.script("delete", "hello")
        self.assertEqual(rc, 0, out + err)
        self.assertFalse((self.repo / "scripts/hello").exists())
        self.assertIn("D  scripts/hello", self.git("status", "--short"))
        self.assertEqual((self.choice().yes(), self.choice("other").no()), ([], []))
        self.assertEqual(ws_catalog.script_entries(self.repo).keys(), {"x"})
        self.assertTrue((self.repo / "scripts/catalog.toml").read_text().startswith("# mine\n"))
        self.assertEqual(self.applied(), ["ws apply scripts"])

    def test_apply_inside_ws_apply_sets_the_execute_bit(self):
        write(self.repo / "scripts/hello", "#!/bin/sh\n", 0o644)
        write(self.repo / "scripts/asked", "#!/bin/sh\n", 0o644)
        (self.repo / "hosts/test/scripts.toml").write_text('yes = ["hello"]\n')
        rc, out, err = self.script("apply", WS_APPLYING="1", WS_OFFERED="1")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("executable: scripts/hello", out)
        self.assertTrue(os.access(self.repo / "scripts/hello", os.X_OK))
        self.assertFalse(os.access(self.repo / "scripts/asked", os.X_OK))
        self.assertEqual(self.applied(), [])

    def test_apply_without_a_terminal_names_the_ask_scripts(self):
        write(self.repo / "scripts/asked", "#!/bin/sh\n")
        rc, out, err = self.script("apply")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("no terminal to ask): asked;", err)
        self.assertEqual(self.choice().text, None)
        self.assertEqual(self.applied(), [])

    def test_check(self):
        write(self.repo / "scripts/hello", "#!/bin/sh\n# Hi.\n")
        write(self.repo / "scripts/ls", "#!/bin/sh\n")
        write(self.repo / "scripts/noshebang", "echo\n")
        write(self.repo / "scripts/wanted", "#!/bin/sh\n")
        (self.repo / "hosts/test/scripts.toml").write_text(
            'yes = ["hello", "ls", "noshebang", "wanted"]\n')
        (self.repo / "hosts/other/scripts.toml").write_text('no = ["gone"]\n')
        rc, out, _ = self.script("check")
        self.assertEqual(rc, 1)
        self.assertIn("no " + str(self.home / ".local/share/wsconfig/scripts/scripts.json"), out)
        for name in ("hello", "ls", "noshebang"):
            self.link(name)
        rc, out, err = self.script("check", "--json")
        self.assertEqual(rc, 0, out + err)
        result = json.loads(out)
        texts = [m["text"] for m in result["messages"]]
        self.assertEqual(result["failures"], 0, texts)
        self.assertIn("hello: ~/.local/bin/hello", texts)
        self.assertIn("wanted: yes on test, not in the build (ws apply scripts)", texts)
        self.assertIn(f"ls: hides {self.system}/ls (~/.local/bin comes first in PATH); rename the script", texts)
        self.assertIn("noshebang: no #! line: what runs it is up to the caller", texts)
        self.assertTrue(any(t.startswith("hosts/other/scripts.toml: gone has no file") for t in texts), texts)
        (self.repo / "scripts/hello").chmod(0o644)
        rc, out, _ = self.script("check", "--json")
        self.assertEqual(rc, 1)
        self.assertIn("hello: not executable (ws apply scripts sets it)",
                      [m["text"] for m in json.loads(out)["messages"]])


class AutoAddTests(unittest.TestCase):
    """ws apply adds a new file of scripts/ to Git before the flake sees the
    tree, and nothing else (ws help plan-v2, 10.1)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        modules = {m: "exit 0\n" for m in ("ws-gnome", "ws-tiling-apply", "ws-keyboard-apply",
                                            "wsflatpak", "wsbox", "wswidgets", "wsscript")}
        self.w = Workspace(tmp.name, modules=modules)

    def test_apply_adds_new_scripts(self):
        write(self.w.repo / "scripts/hello", "#!/bin/sh\n")
        rc, out, err = self.w.ws("apply", "scripts")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("added to Git: scripts/hello", err)
        self.assertEqual(self.w.git("ls-files", "scripts"), "scripts/hello")

    def test_other_files_are_named_not_added(self):
        write(self.w.repo / "scripts/hello", "#!/bin/sh\n")
        write(self.w.repo / "stray.txt", "")
        rc, _, err = self.w.ws("apply", "scripts")
        self.assertEqual(rc, 2)
        self.assertIn("not tracked): stray.txt", err)
        # scripts/ is added all the same: the next apply sees it.
        self.assertEqual(self.w.git("ls-files", "scripts", "stray.txt"), "scripts/hello")

    def test_ignored_and_outward_links(self):
        (self.w.repo / ".gitignore").write_text("scripts/*.bak\n")
        write(self.w.repo / "scripts/old.bak", "")
        rc, out, err = self.w.ws("apply", "scripts")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(self.w.git("ls-files", "scripts"), "")
        (self.w.repo / "scripts/out").symlink_to(self.w.root / "elsewhere")
        rc, _, err = self.w.ws("apply", "scripts")
        self.assertEqual(rc, 2)
        self.assertIn("scripts/out is a symbolic link out of scripts/", err)
        self.assertEqual(self.w.git("ls-files", "scripts"), "")


if __name__ == "__main__":
    unittest.main()
