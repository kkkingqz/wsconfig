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
               '/srv/box/config:/config:ro'],
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
        # A checkout of core and data together (until ws help plan-v2, 8.11).
        (self.repo / 'bin').mkdir()
        (self.repo / 'bin/ws').write_text('')
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
        # ssh: log the remote command and its stdin size; `test -d` of a
        # mount source fails for the paths in $MISSING.
        self.stub('ssh', '''shift 3
printf '%s\\n' "$*" >> "$CALLS"
case "$1" in
    test) case " $MISSING " in *" $3 "*) exit 1 ;; esac ;;
    *docker*build*) wc -c >> "$CALLS" ;;
esac
exit 0
''')
        self.calls = self.root / 'calls'
        self.env = dict(os.environ, WSCONFIG=str(self.repo),
                        CALLS=str(self.calls), MISSING='',
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

    def ws(self, *args, **env):
        return subprocess.run([str(self.repo / 'libexec/ws-container'), *args], text=True,
                              capture_output=True, env=dict(self.env, **env))

    def test_run_dry_run_expands_home(self):
        p = self.ws('run', 'box', '--dry-run')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('-v /srv/box/home:/home/tester ', p.stdout)
        self.assertIn('-v /srv/projects:/home/tester/Projects ', p.stdout)
        self.assertIn('-v /srv/box/config:/config:ro ', p.stdout)
        self.assertIn('-p 3390:3389', p.stdout)
        self.assertIn('--device /dev/fuse', p.stdout)
        self.assertTrue(p.stdout.rstrip().endswith('local/box:latest'))
        self.assertFalse(self.calls.exists())

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

    def test_build_needs_clean_checkout(self):
        (self.repo / 'new').write_text('x')
        p = self.ws('build', 'box')
        self.assertEqual(p.returncode, 1)
        self.assertIn('the checkout has changes', p.stderr)

    def test_build_sends_commit(self):
        commit = self.git('rev-parse', '--short', 'HEAD')
        p = self.ws('build', 'box')
        self.assertEqual(p.returncode, 0, p.stderr)
        call, size = self.calls.read_text().splitlines()[-2:]
        self.assertIn(f"'local/box:{commit}'", call)
        self.assertIn("'HOST=box'", call)
        self.assertIn("-f container/Dockerfile -", call.replace("'", ''))
        self.assertGreater(int(size), 0)


    def separate(self):
        """The checkout as a configuration of its own, a core checkout
        beside it."""
        self.git('rm', '-q', 'bin/ws')
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
