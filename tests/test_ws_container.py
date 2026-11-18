import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

SPEC = {
    'server': 'root@server.test',
    'image': 'local/box',
    'port': 3390,
    'mounts': ['/srv/box/home:~', '/srv/box/nix:/nix', '/srv/projects:~/Projects',
               '/srv/box/config:/config:ro', '/srv/box/grd:/var/lib/gnome-remote-desktop'],
    'devices': ['/dev/fuse'],
}


class ContainerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        (self.repo / 'libexec').mkdir(parents=True)
        shutil.copyfile(ROOT / 'libexec/ws-container', self.repo / 'libexec/ws-container')
        (self.repo / 'lib').mkdir(exist_ok=True)
        for name in ('common.bash', 'ws_common.py', 'ws_facts.py'):
            shutil.copyfile(ROOT / 'lib' / name, self.repo / 'lib' / name)
        (self.repo / 'libexec/ws-container').chmod(0o755)
        shutil.copyfile(ROOT / '.gitignore', self.repo / '.gitignore')
        self.host('box', 'container')
        self.host('pc', 'grub')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.org')
        self.git('add', '.')
        self.git('commit', '-qm', 'initial')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        # ssh: log the remote command and its stdin size; `test` of a
        # path fails for the paths in $MISSING and, as ssh does, reads
        # stdin; a file written (put_remote) goes to $WRITES.
        self.stub('ssh', '''shift 3
printf '%s\\n' "$*" >> "$CALLS"
case "$1" in
    test) cat >/dev/null; case " $MISSING " in *" $3 "*) exit 1 ;; esac ;;
    *docker*build*) wc -c >> "$CALLS" ;;
    umask*) cat >> "$WRITES" ;;
    *docker\\ exec\\ -i*) cat >> "$WRITES" ;;
    *) cat >/dev/null ;;
esac
exit 0
''')
        self.calls = self.root / 'calls'
        self.writes = self.root / 'writes'
        self.env = dict(os.environ, WSCONFIG=str(self.repo),
                        CALLS=str(self.calls), MISSING='', WRITES=str(self.writes),
                        PATH=str(self.bin) + ':' + os.environ['PATH'])

    def host(self, name, boot):
        d = self.repo / 'hosts' / name
        d.mkdir(parents=True)
        text = f'[host]\nuser = "tester"\n\n[platform]\nboot = "{boot}"\n'
        if boot == 'container':
            # JSON strings and lists are TOML here.
            text += '\n[container]\n' + ''.join(f'{k} = {json.dumps(v)}\n' for k, v in SPEC.items())
        (d / 'host.toml').write_text(text)

    def stub(self, name, body):
        p = self.bin / name
        p.write_text('#!/bin/sh\n' + body)
        p.chmod(0o755)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def ws(self, *args, input='', **env):
        return subprocess.run([str(self.repo / 'libexec/ws-container'), *args], text=True,
                              input=input, capture_output=True, env=dict(self.env, **env))

    def test_run_dry_run_expands_home(self):
        p = self.ws('run', 'box', '--dry-run')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('-v /srv/box/home:/home/tester ', p.stdout)
        self.assertIn('-v /srv/projects:/home/tester/Projects ', p.stdout)
        self.assertIn('-v /srv/box/config:/config:ro ', p.stdout)
        self.assertIn('-p 3390:3389', p.stdout)
        self.assertIn('--device /dev/fuse', p.stdout)
        self.assertTrue(p.stdout.rstrip().endswith('local/box:latest'))
        self.assertNotIn('--memory', p.stdout)
        self.assertFalse(self.calls.exists())

    def test_run_with_a_memory_limit(self):
        toml = self.repo / 'hosts/box/host.toml'
        toml.write_text(toml.read_text() + 'memory = "16g"\n')
        p = self.ws('run', 'box', '--dry-run')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('--memory 16g --memory-swap 16g ', p.stdout)

    def test_not_a_container_host(self):
        p = self.ws('status', 'pc')
        self.assertEqual(p.returncode, 1)
        self.assertIn('not a container host', p.stderr)

    def test_run_needs_mount_sources(self):
        p = self.ws('run', 'box', MISSING='/srv/projects')
        self.assertEqual(p.returncode, 1)
        self.assertIn('/srv/projects does not exist', p.stderr)
        self.assertNotIn('docker run', self.calls.read_text())

    def test_run_replaces_container(self):
        p = self.ws('run', 'box')
        self.assertEqual(p.returncode, 0, p.stderr)
        last = self.calls.read_text().splitlines()[-1]
        self.assertTrue(last.startswith("docker rm -f 'box'"), last)
        self.assertIn("'/srv/box/home:/home/tester'", last)
        # Every mount, not only the first: ssh of `test -d` reads stdin.
        for m in ("'/srv/box/nix:/nix'", "'/srv/projects:/home/tester/Projects'", "'/srv/box/config:/config:ro'"):
            self.assertIn(m, last)

    HASH = '/srv/box/config/password.hash'
    CRED = '/srv/box/grd/.local/share/gnome-remote-desktop/credentials.ini'

    def test_run_asks_what_the_server_lacks_once(self):
        p = self.ws('run', 'box', input='s3cret\ns3cret\n\nrdp pw\nrdp pw\n',
                    MISSING=f'{self.HASH} {self.CRED}')
        self.assertEqual(p.returncode, 0, p.stderr)
        calls = self.calls.read_text()
        writes = self.writes.read_text()
        # A crypt hash of the password, never the password, on the server.
        self.assertNotIn('s3cret', calls + writes)
        hash_ = writes.splitlines()[0]
        self.assertTrue(hash_.startswith('$6$'), hash_)
        self.assertEqual(subprocess.check_output(
            ['openssl', 'passwd', '-6', '-salt', hash_.split('$')[2], 's3cret'], text=True).strip(), hash_)
        self.assertIn("credentials={'username': <'tester'>, 'password': <'rdp pw'>}", writes)
        self.assertNotIn('rdp pw', calls)
        # Written before the old container goes.
        lines = calls.splitlines()
        self.assertLess(max(i for i, l in enumerate(lines) if l.startswith('umask')),
                        next(i for i, l in enumerate(lines) if l.startswith('docker rm')))
        self.assertIn(f"mv -f '{self.HASH}.tmp' '{self.HASH}'", calls)

    def test_run_asks_nothing_when_the_server_has_both(self):
        p = self.ws('run', 'box')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn('umask', self.calls.read_text())
        self.assertFalse(self.writes.exists())

    def test_password_mismatch_changes_nothing(self):
        p = self.ws('password', 'box', input='one\ntwo\n')
        self.assertEqual(p.returncode, 1)
        self.assertIn('passwords differ', p.stderr)
        self.assertNotIn('umask', self.calls.read_text() if self.calls.exists() else '')

    def test_password_removes_the_plain_text_file_and_applies_live(self):
        self.stub('ssh', self.bin.joinpath('ssh').read_text().replace(
            'case "$1" in', 'case "$1" in\n    docker) [ "$2" = inspect ] && echo true ;;', 1))
        p = self.ws('password', 'box', input='pw\npw\n')
        self.assertEqual(p.returncode, 0, p.stderr)
        calls = self.calls.read_text()
        self.assertIn('rm -f /srv/box/config/password\n', calls)
        self.assertIn('usermod --password "$h" tester', calls)
        self.assertNotIn('pw\n', calls)

    def test_rdp_password_removes_the_plain_text_files(self):
        p = self.ws('password', 'box', '--rdp', input='me\nx\nx\n')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('rm -f /srv/box/config/rdp-user /srv/box/config/rdp-password', self.calls.read_text())
        self.assertIn("<'me'>", self.writes.read_text())

    def test_build_needs_clean_checkout(self):
        (self.repo / 'new').write_text('x')
        p = self.ws('build', 'box')
        self.assertEqual(p.returncode, 1)
        self.assertIn('the checkout has changes', p.stderr)

    def separate(self):
        """The configuration pins a core; a core checkout beside it."""
        (self.repo / 'flake.lock').write_text(json.dumps(
            {'nodes': {'root': {'inputs': {'wsconfig': 'wsconfig'}},
                       'wsconfig': {'locked': {'rev': 'c' * 40}}}, 'root': 'root', 'version': 7}))
        self.git('add', 'flake.lock')
        self.git('commit', '-qm', 'separate')
        core = self.root / 'core'
        (core / 'container').mkdir(parents=True)
        (core / 'container/Dockerfile').write_text('FROM scratch\n')
        g = ['git', '-C', str(core)]
        subprocess.run([*g, 'init', '-q'], check=True)
        subprocess.run([*g, 'add', '.'], check=True)
        subprocess.run([*g, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'core'], check=True)
        return core, subprocess.check_output([*g, 'rev-parse', '--short', 'HEAD'], text=True).strip()

    def test_build_of_a_separate_configuration_sends_config_and_core(self):
        core, core_rev = self.separate()
        commit = self.git('rev-parse', '--short', 'HEAD')
        p = self.ws('build', 'box', WS_CORE_PATH=str(core))
        self.assertEqual(p.returncode, 0, p.stderr)
        call, size = self.calls.read_text().splitlines()[-2:]
        flat = call.replace("'", '')
        self.assertIn(f'-t local/box:{commit}-{core_rev}', flat)
        self.assertIn('CONFIG=config', flat)
        self.assertIn(f'org.wsconfig.core.revision={core_rev}', flat)
        self.assertIn('-f core/container/Dockerfile -', flat)
        self.assertGreater(int(size), 0)

    def test_dry_run_of_a_separate_configuration_names_the_pinned_core(self):
        self.separate()
        p = self.ws('build', 'box', '--dry-run')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('+ core ccccccc |', p.stdout)

    def test_dirty_core_checkout_is_refused(self):
        core, _ = self.separate()
        (core / 'x').write_text('x')
        p = self.ws('build', 'box', WS_CORE_PATH=str(core))
        self.assertEqual(p.returncode, 1)
        self.assertIn('has changes', p.stderr)


if __name__ == '__main__':
    unittest.main()
