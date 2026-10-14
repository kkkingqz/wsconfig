import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = 'org.example.App'


class OverrideTests(unittest.TestCase):
    def declare(self, overrides, app=APP):
        """The flatpak.json of ws apply with these overrides."""
        self.manifest.write_text(json.dumps({
            'remotes': {'flathub': 'https://example.org/repo'},
            'apps': [{'remote': 'flathub', 'app': app}], 'overrides': overrides}))

    def catalog_with(self, fields, app=APP, more=''):
        """catalog.toml with APP and its FIELDS (TOML lines)."""
        self.catalog.write_text('[remotes]\nflathub = "https://example.org/repo"\n\n'
                                f'[[apps]]\nid = "{app}"\nremote = "flathub"\n{fields}{more}')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        cfg = self.root / 'cfg'
        cfg.mkdir()
        self.manifest = cfg / 'flatpak.json'
        (cfg / 'desktop').mkdir()
        self.declare({})
        self.config = self.root / 'config'
        (self.config / 'flatpak').mkdir(parents=True)
        (self.config / 'hosts/test').mkdir(parents=True)
        self.catalog = self.config / 'flatpak/catalog.toml'
        self.catalog_with('')
        self.host = self.config / 'hosts/test/flatpak.toml'
        self.host.write_text(f'yes = ["{APP}"]\n')
        self.g = runpy.run_path(str(ROOT / 'libexec/wsflatpak'))['cmd_check'].__globals__
        self.g.update(CFG=cfg, MANIFEST=self.manifest, DESKTOP_OVERRIDES=cfg / 'desktop',
                      REPO=self.config, this_host=lambda: 'test')
        self.runtime = ''
        self.addCleanup(patch.stopall)
        self.applied = []
        patch.object(self.g['ws_common'], 'apply_module',
                     side_effect=lambda *m: self.applied.append(m)).start()
        patch('shutil.which', return_value='/fake/flatpak').start()
        patch('subprocess.run', side_effect=self.flatpak).start()

    def flatpak(self, args, **kwargs):
        self.assertEqual(args[0], 'flatpak')
        command = args[1]
        if command in ('remotes', 'list') and '--system' in args:
            out = ''
        elif command == 'remotes':
            out = 'flathub\n'
        elif command == 'list':
            out = APP + ('/x86_64/stable' if '--columns=ref' in args else '') + '\n'
        elif command == 'info' and '--show-origin' in args:
            out = 'flathub\n'
        elif command == 'override' and '--show' in args:
            out = self.runtime if args[-1] == APP else ''
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, out, '')

    def check(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            status = self.g['cmd_check'](True)
        return status, json.loads(output.getvalue())

    def test_app_without_declared_overrides_accepts_empty_runtime(self):
        status, result = self.check()
        self.assertEqual(status, 0)
        self.assertEqual(result['failures'], 0)

    def test_desktop_overrides_follow_the_marks(self):
        # APP is yes on test; org.example.Other is not on this host.
        desktop = self.g['DESKTOP_OVERRIDES']
        applications = self.root / 'applications'
        applications.mkdir()
        self.g['USER_APPLICATIONS'] = applications
        for app in (APP, 'org.example.Other'):
            (desktop / f'{app}.desktop').write_text('[Desktop Entry]\n')
        texts = lambda result: {level: [m['text'] for m in result['messages'] if m['level'] == level]
                                for level in ('fail', 'warn', 'info')}
        status, result = self.check()
        self.assertEqual(status, 1)
        self.assertIn(f'managed desktop override not applied: {APP}.desktop (yes on test; run ws apply flatpak)',
                      texts(result)['fail'])
        self.assertIn('managed desktop override not linked: org.example.Other is not on test',
                      texts(result)['info'])
        for app in (APP, 'org.example.Other'):
            (applications / f'{app}.desktop').symlink_to(desktop / f'{app}.desktop')
        status, result = self.check()
        self.assertEqual(result['failures'], 0)
        self.assertIn('managed desktop override linked but org.example.Other is not yes '
                      'on test: org.example.Other.desktop (run ws apply flatpak)', texts(result)['warn'])

    def test_app_without_declaration_rejects_filesystem_override(self):
        self.runtime = '[Context]\nfilesystems=home;\n'
        status, result = self.check()
        self.assertEqual(status, 1)
        self.assertIn(f'untracked filesystem override: {APP}: home',
                      [message['text'] for message in result['messages']])

    def test_removed_last_declaration_rejects_leftover_environment(self):
        self.runtime = '[Environment]\nEXAMPLE=untracked\n'
        status, result = self.check()
        self.assertEqual(status, 1)
        self.assertIn(f'untracked environment override: {APP}: EXAMPLE=untracked',
                      [message['text'] for message in result['messages']])

    def test_app_without_declaration_rejects_session_bus_override(self):
        self.runtime = '[Session Bus Policy]\norg.example.Service=talk\n'
        status, result = self.check()
        self.assertEqual(status, 1)
        self.assertIn(f'untracked session-bus override: {APP}: org.example.Service=talk',
                      [message['text'] for message in result['messages']])

    def test_managed_branch_checks_overrides_by_application_id(self):
        self.declare({}, f'app/{APP}/x86_64/stable')
        self.catalog_with('', app=f'app/{APP}/x86_64/stable')
        self.runtime = '[Context]\nfilesystems=home;\n'
        status, result = self.check()
        self.assertEqual(status, 1)
        self.assertIn(f'untracked filesystem override: {APP}: home',
                      [message['text'] for message in result['messages']])

    def test_declared_permissions_match_runtime(self):
        self.runtime = '[Context]\nfilesystems=home:ro;\n[Environment]\nEXAMPLE=value\n[Session Bus Policy]\norg.example.Service=talk\n'
        self.declare({APP: {'filesystems': ['home:ro'], 'environment': {'EXAMPLE': 'value'},
                            'session_bus': {'org.example.Service': 'talk'}}})
        status, result = self.check()
        self.assertEqual(status, 0)
        self.assertEqual(result['failures'], 0)

    def edit(self, catalog, host, *entries, remove=False, **flags):
        """overrides_add (or overrides_remove) of ENTRIES on host test over
        the catalog FIELDS of APP and the host file HOST; both afterwards."""
        self.catalog_with(catalog)
        self.host.write_text(host)
        with contextlib.redirect_stdout(io.StringIO()):
            for entry in entries:
                self.g['overrides_remove' if remove else 'overrides_add'](entry, **flags)
        return tomllib.loads(self.catalog.read_text())['apps'][0], tomllib.loads(self.host.read_text())

    def test_filesystem_mode_replaces_previous_mode(self):
        for old, new in [('home', 'home:ro'), ('home:ro', 'home:rw'),
                         ('xdg-download:create', 'xdg-download:ro')]:
            with self.subTest(old=old, new=new):
                app, _ = self.edit(f'filesystems = ["{old}", "host"]\n', '', (APP, 'filesystem', new))
                self.assertEqual(app['filesystems'], [new, 'host'])

    def test_catalog_value_keeps_comments(self):
        self.catalog_with('# why\nenv = { A = "1" }\n')
        self.host.write_text('# mine\n')
        with contextlib.redirect_stdout(io.StringIO()):
            self.g['overrides_add']((APP, 'env', 'B=2'))
        text = self.catalog.read_text()
        self.assertIn('# why\n', text)
        self.assertEqual(tomllib.loads(text)['apps'][0]['env'], {'A': '1', 'B': '2'})
        self.assertEqual(self.host.read_text(), '# mine\n')

    def test_new_value_goes_to_the_catalog(self):
        app, host = self.edit('', '', (APP, 'env', 'SCALE=2'))
        self.assertEqual(app['env'], {'SCALE': '2'})
        self.assertNotIn('overrides', host)
        self.assertEqual(self.applied, [('flatpak',)])

    def test_host_value_replaces_the_catalog_value_here(self):
        app, host = self.edit('env = { SCALE = "2" }\n', '', (APP, 'env', 'SCALE=1'), own=True)
        self.assertEqual(app['env'], {'SCALE': '2'})
        self.assertEqual(host['overrides'][APP], {'env': {'SCALE': '1'}})
        cat = self.g['catalog']()
        self.assertEqual(self.g['flatpak_catalog'].effective(cat, self.g['host_choice'](cat), APP),
                         [('env', 'SCALE=1')])
        # The catalog value again: the own one goes.
        app, host = self.edit('env = { SCALE = "2" }\n', self.host.read_text(), (APP, 'env', 'SCALE=2'), own=True)
        self.assertNotIn('overrides', host)

    def test_catalog_value_lifts_the_own_one_and_the_skip(self):
        host = f'[overrides."{APP}"]\nenv = {{ SCALE = "1" }}\nskip = ["talk org.example.Bus"]\n'
        app, host = self.edit('talk = ["org.example.Bus"]\n', host,
                              (APP, 'env', 'SCALE=3'), (APP, 'talk', 'org.example.Bus'))
        self.assertEqual(app['env'], {'SCALE': '3'})
        self.assertNotIn('overrides', host)

    def test_value_that_looks_like_a_mark_is_the_value(self):
        app, _ = self.edit('', '', (APP, 'env', 'ENABLE=yes'))
        self.assertEqual(app['env'], {'ENABLE': 'yes'})

    def test_un_skips_a_catalog_value_here(self):
        app, host = self.edit('filesystems = ["home:ro"]\n', '', (APP, 'filesystem', 'home'), remove=True)
        self.assertEqual(app['filesystems'], ['home:ro'])
        self.assertEqual(host['overrides'][APP], {'skip': ['filesystem home']})

    def test_un_all_drops_the_catalog_value_and_the_skips(self):
        other = self.config / 'hosts/other'
        other.mkdir()
        (other / 'flatpak.toml').write_text(f'[overrides."{APP}"]\nskip = ["env SCALE"]\n')
        app, host = self.edit('env = { SCALE = "2" }\n', '', (APP, 'env', 'SCALE'), remove=True, everywhere=True)
        self.assertNotIn('env', app)
        self.assertNotIn('overrides', tomllib.loads((other / 'flatpak.toml').read_text()))

    def test_un_drops_the_own_value(self):
        host = f'[overrides."{APP}"]\ntalk = ["org.example.Own"]\n'
        app, host = self.edit('', host, (APP, 'talk', 'org.example.Own'), remove=True)
        self.assertNotIn('overrides', host)

    def test_un_of_an_override_not_applying_here_fails(self):
        with self.assertRaises(SystemExit) as error:
            self.edit('', '', (APP, 'env', 'SCALE'), remove=True)
        self.assertIn('not declared for test', str(error.exception))

    def test_override_needs_the_app_in_the_catalog(self):
        with self.assertRaises(SystemExit) as error:
            self.edit('', '', ('org.example.Unknown', 'env', 'A=1'))
        self.assertIn('first: ws flatpak manage', str(error.exception))

    def test_skip_must_name_a_catalog_value(self):
        with self.assertRaises(SystemExit) as error:
            self.edit('', f'[overrides."{APP}"]\nskip = ["env NOPE"]\n', (APP, 'env', 'A=1'))
        self.assertIn("skip 'env NOPE' is no catalog value", str(error.exception))

    def test_unfilesystem_removes_declared_path_regardless_of_mode(self):
        self.catalog_with('filesystems = ["home:ro"]\n')
        self.host.write_text(f'[overrides."{APP}"]\nfilesystems = ["xdg-download:ro"]\n')
        with contextlib.redirect_stdout(io.StringIO()):
            for value in ('home', 'xdg-download'):
                try:
                    self.g['cmd_override'](SimpleNamespace(cmd='unfilesystem', app=APP, value=value,
                                                           everywhere=True))
                except SystemExit as error:
                    self.fail(f'declared filesystem could not be removed: {error}')
        self.assertNotIn('filesystems', tomllib.loads(self.catalog.read_text())['apps'][0])
        self.assertNotIn('overrides', tomllib.loads(self.host.read_text()))


if __name__ == '__main__':
    unittest.main()
