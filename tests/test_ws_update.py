import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        (self.repo / 'bin').mkdir(parents=True)
        (self.repo / 'flatpak').mkdir()
        shutil.copyfile(ROOT / 'bin/ws', self.repo / 'bin/ws')
        for name in ('apps.txt', 'overrides.txt'):
            (self.repo / 'flatpak' / name).write_text('')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.org')
        self.git('add', '.')
        self.git('commit', '-qm', 'initial')
        self.initial = self.git('rev-parse', 'HEAD')
        (self.repo / 'flatpak/apps.txt').write_text('flathub org.example.App\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        nix = self.bin / 'nix'
        nix.write_text('''#!/bin/sh
printf '%s\n' "$*" >> "$CALLS"
case "$1" in
    flake) exit 0 ;;
    build) echo /tmp/test-generation; exit "${BUILD_STATUS:-0}" ;;
    run)
        case "$2" in
            *'#home-manager') exit "${SWITCH_STATUS:-0}" ;;
            *'#nvd') exit 0 ;;
            *) exit 99 ;;
        esac ;;
    *) exit 99 ;;
esac
''')
        nix.chmod(0o755)
        gdbus = self.bin / 'gdbus'
        gdbus.write_text('#!/bin/sh\nexit "${DBUS_STATUS:-0}"\n')
        gdbus.chmod(0o755)
        extensions = self.root / '.local/share/workstation/gnome'
        extensions.mkdir(parents=True)
        (extensions / 'extensions').write_text('example@local local\n')
        self.calls = self.root / 'calls'
        self.env = dict(os.environ, HOME=str(self.root), WSCONFIG=str(self.repo),
                        XDG_STATE_HOME=str(self.root / 'state'), WS_HOST='test',
                        PATH=str(self.bin) + ':' + os.environ['PATH'], CALLS=str(self.calls))

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def update(self, step='nix', **statuses):
        return subprocess.run(['bash', str(self.repo / 'bin/ws'), 'update', step],
                              env=dict(self.env, **statuses), capture_output=True, text=True)

    def test_failed_activation_is_reported_without_committing_lists(self):
        generation = self.root / 'old-generation'
        generation.mkdir()
        profile = self.root / 'state/nix/profiles/home-manager'
        profile.parent.mkdir(parents=True)
        profile.symlink_to(generation)
        result = self.update(SWITCH_STATUS='42')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('FAIL  nix (exit 42)', result.stdout)
        self.assertTrue(any('#home-manager' in call for call in self.calls.read_text().splitlines()),
                        'activation was not reached after diffing the existing generation')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial)

    def test_failed_build_stops_before_activation(self):
        result = self.update(BUILD_STATUS='41')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('FAIL  nix (exit 41)', result.stdout)
        self.assertFalse(any(call.startswith('run ') for call in self.calls.read_text().splitlines()))
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial)

    def test_successful_activation_commits_lists(self):
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OK    nix', result.stdout)
        self.assertNotEqual(self.git('rev-parse', 'HEAD'), self.initial)
        self.assertEqual(self.git('show', 'HEAD:flatpak/apps.txt'), 'flathub org.example.App')

    def test_failed_commit_is_reported(self):
        hook = self.repo / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        result = self.update()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('FAIL  nix', result.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial)

    def test_failed_extension_update_is_reported(self):
        result = self.update('extensions', DBUS_STATUS='42')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('FAIL  extensions (exit 42)', result.stdout)


if __name__ == '__main__':
    unittest.main()
