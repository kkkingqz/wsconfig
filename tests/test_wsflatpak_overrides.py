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

ROOT = Path(__file__).resolve().parents[1]
APP = 'org.example.App'


class OverrideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        cfg = self.root / 'cfg'
        cfg.mkdir()
        self.overrides = cfg / 'overrides'
        self.overrides.mkdir()
        (cfg / 'desktop').mkdir()
        (cfg / 'apps.conf').write_text(f'flathub {APP}\n')
        (cfg / 'remotes.conf').write_text('flathub https://example.org/repo\n')
        self.apps = self.root / 'apps.txt'
        self.apps.write_text(f'flathub {APP} test=yes all=ask\n')
        self.list = self.root / 'overrides.txt'
        self.list.write_text('')
        self.g = runpy.run_path(str(ROOT / 'bin/wsflatpak'))['cmd_check'].__globals__
        self.g.update(CFG=cfg, APPS=cfg / 'apps.conf', REMOTES=cfg / 'remotes.conf',
                      OVERRIDES=self.overrides, DESKTOP_OVERRIDES=cfg / 'desktop',
                      APPS_LIST=self.apps, OVERRIDES_LIST=self.list,
                      this_host=lambda: 'test')
        self.runtime = ''
        self.addCleanup(patch.stopall)
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
        # APP is marked test=yes; org.example.Other is not on this workstation.
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
        self.assertIn(f'managed desktop override not applied: {APP}.desktop (test=yes; run ws switch)',
                      texts(result)['fail'])
        self.assertIn('managed desktop override not linked: org.example.Other is not on test',
                      texts(result)['info'])
        for app in (APP, 'org.example.Other'):
            (applications / f'{app}.desktop').symlink_to(desktop / f'{app}.desktop')
        status, result = self.check()
        self.assertEqual(result['failures'], 0)
        self.assertIn('managed desktop override linked but org.example.Other is not marked '
                      'test=yes: org.example.Other.desktop (run ws switch)', texts(result)['warn'])

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
        self.g['APPS'].write_text(f'flathub app/{APP}/x86_64/stable\n')
        self.apps.write_text(f'flathub app/{APP}/x86_64/stable\n')
        self.runtime = '[Context]\nfilesystems=home;\n'
        status, result = self.check()
        self.assertEqual(status, 1)
        self.assertIn(f'untracked filesystem override: {APP}: home',
                      [message['text'] for message in result['messages']])

    def test_declared_permissions_match_runtime(self):
        self.runtime = '[Context]\nfilesystems=home:ro;\n[Environment]\nEXAMPLE=value\n[Session Bus Policy]\norg.example.Service=talk\n'
        (self.overrides / f'{APP}.conf').write_text(self.runtime)
        status, result = self.check()
        self.assertEqual(status, 0)
        self.assertEqual(result['failures'], 0)

    def test_filesystem_mode_replaces_previous_mode(self):
        for old, new in [('home', 'home:ro'), ('home:ro', 'home:rw'),
                         ('xdg-download:create', 'xdg-download:ro')]:
            with self.subTest(old=old, new=new):
                self.list.write_text(f'{APP} filesystem {old}\n')
                with contextlib.redirect_stdout(io.StringIO()):
                    self.g['overrides_add']((APP, 'filesystem', new))
                self.assertEqual(self.list.read_text(), f'{APP} filesystem {new}\n')

    def test_replacing_mode_removes_old_duplicates_and_preserves_other_lines(self):
        self.list.write_text(f'# permissions\n{APP} filesystem home\n{APP} env EXAMPLE=value\n{APP} filesystem home:ro\n')
        with contextlib.redirect_stdout(io.StringIO()):
            self.g['overrides_add']((APP, 'filesystem', 'home:ro'))
        self.assertEqual(self.list.read_text(),
                         f'# permissions\n{APP} filesystem home:ro\n{APP} env EXAMPLE=value\n')

    def test_unfilesystem_removes_declared_path_regardless_of_mode(self):
        self.list.write_text(f'{APP} filesystem home:ro\n')
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                self.g['cmd_override'](SimpleNamespace(cmd='unfilesystem', app=APP, value='home'))
            except SystemExit as error:
                self.fail(f'declared filesystem could not be removed: {error}')
        self.assertEqual(self.list.read_text(), '')


if __name__ == '__main__':
    unittest.main()
