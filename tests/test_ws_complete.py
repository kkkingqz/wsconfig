"""The completion of ws (lib/ws_complete.py): made from the usage of the
commands, so every command of bin/ws completes; the grammar of a usage
line; the values of the placeholders; and the real fish, which loads only
ws.fish (the tools are not in PATH)."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ws_complete as wc  # noqa: E402

FISH = shutil.which("fish")
SPEC = None


def spec():
    global SPEC
    if SPEC is None:
        SPEC = wc.build(ROOT)
    return SPEC


def names(candidates):
    return [c.split("\t", 1)[0] for c in candidates]


class GrammarTests(unittest.TestCase):
    def test_a_line(self):
        full, short = wc.parse_line("  ws box run NAME COMMAND [ARG...]   run a command")
        self.assertEqual(full["desc"], "run a command")
        self.assertEqual([(e["lit"], e["ph"], e["rep"]) for e in full["el"]],
                         [(["box"], None, False), (["run"], None, False), ([], "NAME", False),
                          ([], "COMMAND", False), ([], "ARG", True)])
        self.assertEqual(len(short["el"]), 4)

    def test_options_values_and_alternatives(self):
        lines = wc.parse_line("ws setup --new [DIR] [--host NAME] [--select | a|b|NAME...]")
        self.assertEqual(lines[0]["opt"], {"--new": None, "--host": "NAME", "--select": None})
        words = {tuple("|".join(e["lit"] + ([e["ph"]] if e["ph"] else [])) for e in l["el"])
                 for l in lines}
        self.assertIn(("setup", "DIR", "a|b|NAME"), words)
        self.assertIn(("setup",), words)
        [line] = wc.parse_line("ws windows exec [--desktop[=WxH]] PROGRAM  run")
        self.assertEqual(line["opt"], {"--desktop": "WxH"})
        self.assertEqual(line["el"][2]["ph"], "PROGRAM")

    def test_option_descriptions(self):
        _, about = wc.parse_help("Usage:\n  ws x y [-n]\n\n  -n, --no-apply  only edit\n"
                                 "--keep-days N   keep them\n")
        self.assertEqual(about, {"-n": "only edit", "--no-apply": "only edit",
                                 "--keep-days": "keep them"})


class SpecTests(unittest.TestCase):
    def test_every_command_of_ws_completes(self):
        ws = (ROOT / "bin/ws").read_text()
        top = {e["lit"][0] for l in spec()["lines"] if l["top"] for e in l["el"][:1]}
        owners = {**wc.dispatch(ws), **wc.modules(ws)}
        self.assertTrue(set(owners) <= top, set(owners) - top)
        self.assertEqual(spec()["tools"], owners)
        for cmd in owners:
            sub = [l for l in spec()["lines"] if not l["top"] and wc.line_cmd(l) == cmd]
            self.assertTrue(sub, f"ws {cmd}: no usage lines of its tool")

    def test_every_placeholder_has_values_or_is_free(self):
        unknown = sorted(f"{c} {p}" for c, p in wc.placeholders(spec()) if not wc.known(c, p))
        self.assertEqual(unknown, [], "add them to VALUES, FILES or FREE of lib/ws_complete.py")

    def test_the_spec_of_the_package_is_the_one_used(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / wc.SPEC).parent.mkdir(parents=True)
            (Path(d) / wc.SPEC).write_text(json.dumps({"lines": [], "x": 1}))
            self.assertEqual(wc.load_spec(Path(d))["x"], 1)


class CompleteTests(unittest.TestCase):
    def c(self, *words):
        *before, current = words
        return names(wc.complete(spec(), list(before), current))

    def test_commands_and_modules(self):
        top = self.c("")
        for cmd in ("apply", "flatpak", "gpu", "box", "clean", "help", "script"):
            self.assertIn(cmd, top)
        self.assertIn("apply\tapply the configuration of this host", wc.complete(spec(), [], ""))

    def test_arguments_of_the_tools(self):
        self.assertIn("install", self.c("flatpak", ""))
        self.assertEqual(self.c("gpu", ""), ["status", "env", "run"])
        self.assertIn("t2bce-build", self.c("suspend", ""))
        self.assertIn("boot-gpu", self.c("gmux", ""))
        self.assertEqual(self.c("gmux", "boot-gpu", ""), ["integrated", "discrete"])
        self.assertEqual(self.c("game", "mode", ""), ["game", "desktop"])
        self.assertIn("gnome-apps", self.c("keyboard", ""))
        self.assertEqual(self.c("system", ""), ["diff", "check", "manifest", "tree"])
        self.assertIn("restore-test", self.c("backup", ""))
        self.assertEqual(self.c("backup", "send", ""), ["home", "vms", "all"])

    def test_options(self):
        self.assertEqual(self.c("clean", "--"), ["--dry-run", "--keep-days", "--yes"])
        self.assertIn("--json", self.c("check", "apt", "--"))
        self.assertEqual(self.c("flatpak", "check", "--"), ["--json"])
        self.assertIn("--remote", self.c("flatpak", "install", "--"))
        self.assertEqual(self.c("widgets", "enable", "--"), ["-n", "--no-apply"])
        # The value of an option is skipped.
        self.assertEqual(self.c("windows", "prefix", "--box", "wine", "x", "")[:2],
                         ["init", "winecfg"])

    def test_static_values(self):
        self.assertEqual(self.c("clean", "nix", ""), ["nix", "podman", "flatpak"])
        self.assertIn("extensions", self.c("apply", ""))
        self.assertIn("core", self.c("update", ""))
        self.assertIn("plan-v2", self.c("help", ""))
        self.assertIn("man", self.c("help", ""))
        self.assertEqual(self.c("windows", "install", ""), ["@files"])
        self.assertEqual(self.c("setup", "--repo", ""), ["@files"])
        self.assertEqual(self.c("gpu", "run", ""), ["@commands"])

    def test_values_from_the_state_and_the_manifests(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / ".local/state/wsconfig/checkpoints/v2-split").mkdir(parents=True)
            box = home / ".local/share/wsconfig/distrobox"
            box.mkdir(parents=True)
            (box / "boxes.json").write_text(json.dumps([
                {"name": "arch", "exports": {"code": "code.desktop"}},
                {"name": "wine", "profile": "wine", "exports": {}}]))
            (home / "wsconfig/hosts/mbp16").mkdir(parents=True)
            env = {"HOME": str(home), "WS_STATE": "", "WS_CONFIG": "", "WSCONFIG": ""}
            with unittest.mock.patch.dict(os.environ, env):
                del os.environ["WS_STATE"]
                self.assertEqual(self.c("checkpoint", "show", ""), ["v2-split"])
                self.assertEqual(self.c("box", "enter", ""), ["arch", "wine"])
                self.assertEqual(self.c("box", "export", "arch", ""), ["code"])
                self.assertEqual(self.c("windows", "shell", "--box", ""), ["wine"])
                self.assertEqual(self.c("container", "build", ""), ["mbp16"])


APP = "org.example.Installed"


class FlatpakValueTests(unittest.TestCase):
    """The values of ws flatpak (as tests/test_wsflatpak_completions before)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        repo = root / "repo/flatpak"
        repo.mkdir(parents=True)
        (repo / "catalog.toml").write_text(
            '[remotes]\nflathub = "https://example.org"\n\n'
            '[[apps]]\nid = "org.example.Removed"\nremote = "flathub"\nfilesystems = ["host"]\n\n'
            f'[[apps]]\nid = "{APP}"\nremote = "flathub"\nfilesystems = ["home:ro"]\n'
            'env = { GDK_SCALE = "2" }\n')
        host = root / "repo/hosts/mbp16"
        host.mkdir(parents=True)
        (host / "flatpak.toml").write_text(f'[overrides."{APP}"]\ntalk = ["org.example.Service"]\n')
        cfg = root / "cfg"
        cfg.mkdir()
        (cfg / "flatpak.json").write_text(
            '{"remotes": {"flathub": "https://example.org", "flatpark": "https://example.net"}}')
        stub = root / "flatpak"
        stub.write_text(f"#!{sys.executable}\n" + '''import sys
args = sys.argv[1:]
if args[0] == "list":
    print("org.example.Installed")
elif args[0] == "remote-ls":
    print("org.example.Park/x86_64/stable" if args[-1] == "flatpark" else "org.example.New/x86_64/stable")
elif args[0] == "remotes":
    print("flathub\\nflatpark")
''')
        stub.chmod(0o755)
        patch = unittest.mock.patch.dict(os.environ, {
            "HOME": str(root), "WSCONFIG": str(repo.parent), "WSFLATPAK_CONFIG": str(cfg),
            "WS_HOST": "mbp16", "PATH": f"{root}:{os.environ['PATH']}"})
        patch.start()
        self.addCleanup(patch.stop)

    def c(self, *words):
        *before, current = words
        return names(wc.complete(spec(), list(before), current))

    def test_install_offers_the_apps_of_the_remote(self):
        self.assertIn("org.example.New", self.c("flatpak", "install", ""))
        self.assertIn("org.example.Park", self.c("flatpak", "install", "--remote", "flatpark", ""))
        self.assertIn("app/org.example.Park/x86_64/stable",
                      self.c("flatpak", "install", "--remote=flatpark", ""))
        self.assertEqual(self.c("flatpak", "install", "--remote", ""), ["flathub", "flatpark"])

    def test_apps_and_declared_values(self):
        self.assertIn(APP, self.c("flatpak", "env", ""))
        self.assertNotIn(APP, self.c("flatpak", "env", APP, ""))
        self.assertIn("org.example.Removed", self.c("flatpak", "unmanage", ""))
        self.assertIn("home:ro", self.c("flatpak", "unfilesystem", APP, ""))
        self.assertIn("GDK_SCALE", self.c("flatpak", "unenv", APP, ""))
        self.assertIn("org.example.Service", self.c("flatpak", "untalk", APP, ""))
        self.assertIn("flatpark", self.c("flatpak", "manage", APP, ""))

    def test_scope_flags_and_help(self):
        self.assertIn("--host", self.c("flatpak", "env", "--"))
        self.assertIn("--all", self.c("flatpak", "unenv", "--"))
        self.assertIn("remote-add", self.c("flatpak", "help", ""))


@unittest.skipUnless(FISH, "fish is required for the completion test")
class FishTests(unittest.TestCase):
    """The real fish with only ws.fish: a ws in PATH that is this checkout."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "bin").mkdir()
        (root / "bin/ws").symlink_to(ROOT / "bin/ws")
        cache = root / "cache/ws"
        cache.mkdir(parents=True)
        (cache / f"complete-{wc.source_key(ROOT)}.json").write_text(json.dumps(spec()))
        self.env = {**os.environ, "HOME": str(root), "XDG_CACHE_HOME": str(root / "cache"),
                    "PATH": f"{root / 'bin'}:{os.environ['PATH']}"}

    def candidates(self, line):
        completions = ROOT / "terminal/fish/completions/ws.fish"
        p = subprocess.run([FISH, "--no-config", "-c",
                            f"source {shlex.quote(str(completions))}; complete -C {shlex.quote(line)}"],
                           env=self.env, text=True, capture_output=True, timeout=60)
        self.assertEqual(p.stderr, "")
        return names(p.stdout.splitlines())

    def test_every_command_with_subcommands_completes_them(self):
        for cmd in sorted(spec()["tools"]):
            expected = [n for n in self_complete(cmd) if not n.startswith("@")]
            if not expected:
                continue
            with self.subTest(cmd=cmd):
                got = self.candidates(f"ws {cmd} ")
                self.assertTrue(set(expected) <= set(got), (expected, got))

    def test_files_and_options(self):
        self.assertIn("--dry-run", self.candidates("ws clean --"))
        home = self.env["HOME"]
        self.assertIn(f"{home}/bin/", self.candidates(f"ws collect {home}/b"))
        self.assertIn("plan-v2", self.candidates("ws help plan-"))


def self_complete(cmd):
    return names(wc.complete(spec(), [cmd], ""))


if __name__ == "__main__":
    unittest.main()
