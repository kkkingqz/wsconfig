"""lib/common.bash and lib/ws_common.py: roots and helpers (helpws plan-v2, 2.1)."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ws_common  # noqa: E402

SOURCE = '. "$(dirname "$(readlink -f "$0")")/../lib/common.bash"'


class CommonTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        # A tool in bin/ of this checkout, so common.bash is found by its path.
        self.tool = self.tmp / "core/bin/tool"
        self.tool.parent.mkdir(parents=True)
        (self.tmp / "core/lib").mkdir()
        for name in ("common.bash", "ws_common.py"):
            (self.tmp / "core/lib" / name).write_bytes((ROOT / "lib" / name).read_bytes())

    def run_tool(self, body, env=None):
        self.tool.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + SOURCE + "\n" + body)
        self.tool.chmod(0o755)
        base = {k: v for k, v in os.environ.items() if k not in ("WSCONFIG", "WS_CONFIG", "WS_STATE", "WS_CORE")}
        base["HOME"] = str(self.tmp / "home")
        base.pop("XDG_STATE_HOME", None)
        base.update(env or {})
        return subprocess.run([str(self.tool)], text=True, capture_output=True, env=base)

    def test_roots_default_to_the_tool_checkout(self):
        p = self.run_tool('echo "$WS_CORE|$WS_CONFIG|$WS_STATE|$repo"\n')
        core = str(self.tmp / "core")
        self.assertEqual(p.stdout.strip(), f"{core}|{core}|{self.tmp}/home/.local/state/wsconfig|{core}")

    def test_wsconfig_sets_config_only(self):
        p = self.run_tool('echo "$WS_CORE|$WS_CONFIG|$repo"\n', {"WSCONFIG": "/data"})
        self.assertEqual(p.stdout.strip(), f"{self.tmp / 'core'}|/data|/data")

    def test_roots_from_ws_are_kept_and_exported(self):
        p = self.run_tool('bash -c \'echo "$WS_CONFIG|$WS_STATE"\'\n',
                          {"WS_CONFIG": "/cfg", "WS_STATE": "/st", "WS_CORE": "/elsewhere"})
        self.assertEqual(p.stdout.strip(), "/cfg|/st")
        p = self.run_tool('echo "$WS_CORE"\n', {"WS_CORE": "/elsewhere"})
        self.assertEqual(p.stdout.strip(), str(self.tmp / "core"))

    def test_xdg_state_home(self):
        p = self.run_tool('echo "$WS_STATE"\n', {"XDG_STATE_HOME": "/xdg"})
        self.assertEqual(p.stdout.strip(), "/xdg/wsconfig")

    def test_die_uses_the_command_name_or_ws_prog(self):
        p = self.run_tool('die "broken"\n')
        self.assertEqual((p.returncode, p.stderr), (1, "tool: broken\n"))
        p = self.run_tool('ws_prog="ws thing"\ndie "broken"\n')
        self.assertEqual(p.stderr, "ws thing: broken\n")

    def test_need(self):
        p = self.run_tool('need sh\nneed ws-no-such-command\n')
        self.assertEqual((p.returncode, p.stderr), (1, "tool: missing command: ws-no-such-command\n"))

    def test_python_roots(self):
        self.assertEqual(ws_common.CORE, ROOT)
        env = {"WS_STATE": "/st"}
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            self.assertEqual(ws_common.state_dir(), Path("/st"))
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        with self.assertRaises(SystemExit) as e:
            ws_common.die("tool", "broken")
        self.assertEqual(str(e.exception), "tool: broken")

    def test_manifest_get(self):
        manifest = self.tmp / "m.json"
        manifest.write_text('[{"name": "a", "home": "${HOME}/a", "exports": {"x": "/x.desktop", "y": "/y"},'
                            ' "hooks": ["h1 arg", "h2"], "n": 3, "on": true}, {"name": "b"}]')
        p = self.run_tool(f'''f={manifest}
manifest_get "$f"; echo -
manifest_get "$f" a exports; echo -
manifest_get "$f" a exports y; manifest_get "$f" a hooks; manifest_get "$f" a n; manifest_get "$f" a on
manifest_get "$f" a home; manifest_get "$f" b home; manifest_get "$f" c home; manifest_get /nope a; echo end
''')
        self.assertEqual(p.stdout.split("\n"), ["a", "b", "-", "x", "y", "-", "/y", "h1 arg", "h2", "3", "true",
                                                "${HOME}/a", "end", ""])

    def test_manifest_rows(self):
        manifest = self.tmp / "k.json"
        manifest.write_text('{"shortcuts": [{"schema": "s", "key": "k", "value": "[\'a b\']", "kind": "required"},'
                            ' {"schema": "t", "key": "x", "value": "@as []"}]}')
        p = self.run_tool(f'''while IFS=$'\\t' read -r schema key value kind; do
    echo "$schema|$key|$value|$kind"
done < <(manifest_rows {manifest} schema,key,value,kind shortcuts)
manifest_rows {manifest} key nothing; echo end
''')
        self.assertEqual(p.stdout, "s|k|['a b']|required\nt|x|@as []|\nend\n")

    def test_state_name_is_the_same_everywhere(self):
        name = ws_common.STATE_NAME
        self.assertIn('/.local/state}/%s}"' % name, (ROOT / "lib/common.bash").read_text())
        self.assertIn('wsState = ".local/state/%s";' % name, (ROOT / "flake.nix").read_text())
        self.assertIn("~/.local/state/%s/$dir" % name,
                      (ROOT / "terminal/fish/completions/ws.fish").read_text())

    def test_tools_find_their_checkout_only_through_common(self):
        # ws-doc-build runs as a lone store file in nix/pkgs/man.nix.
        offenders = []
        for path in sorted((ROOT / "bin").iterdir()):
            if not path.is_file() or path.name == "ws-doc-build":
                continue
            for line in path.read_text(errors="replace").splitlines():
                if 'readlink -f "$0"' in line and line.strip() != SOURCE:
                    offenders.append(f"{path.name}: {line.strip()}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
