import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
import fcntl
import signal
import time
from backup_fixture import Boundary, U
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import backup

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationTests(unittest.TestCase):
    def test_boolean_schema_version_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'c.json'
            p.write_text('{"schema_version":true}')
            with self.assertRaisesRegex(ValueError, 'schema_version'):
                backup.load_config(p)
    def test_unknown_fields_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'c.json'
            p.write_text('{"schema_version":1,"private_key":"secret"}')
            with self.assertRaisesRegex(ValueError, 'unknown'):
                backup.load_config(p)

    def test_unsafe_alias_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'c.json'
            p.write_text('{"schema_version":1,"ssh_host":"host;bad"}')
            with self.assertRaisesRegex(ValueError, 'safe SSH'):
                backup.load_config(p)


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.b = Boundary()
        self.addCleanup(self.b.close)
        self.snapshots = self.b.root / 'snapshots'
        self.snapshots.mkdir(mode=0o700)
        self.remote = self.b.root / 'remote'
        self.remote.mkdir(mode=0o700)
        self.rcfg = self.b.root / 'receiver.conf'
        self.rcfg.write_text(f'ROOT={self.remote}\nFS_UUID={U}\nHOST_ID=mbp16\n')
        self.rcfg.chmod(0o600)
        # Substitute only sudo/SSH privilege and network boundaries. Actual
        # source/receiver scripts, subprocess pipelines, files and state run.
        (self.b.bin / 'sudo').write_text('#!/bin/sh\nexec "$@"\n')
        (self.b.bin / 'sudo').chmod(0o755)
        ssh = self.b.bin / 'ssh'
        ssh.write_text('#!/usr/bin/env python3\nimport os,sys\nos.environ["SSH_ORIGINAL_COMMAND"]=sys.argv[-1]\nos.execv("/bin/bash",["bash",' + repr(str(ROOT / 'backup/unraid/wsbackup-receiver')) + ',' + repr(str(self.rcfg)) + '])\n')
        ssh.chmod(0o755)
        self.config_dir = self.b.root / 'config/workstation'
        self.config_dir.mkdir(parents=True)
        self.config_dir.joinpath('backup.json').write_text(json.dumps({
            'schema_version': 1, 'ssh_host': 'backup-nas', 'remote_host_id': 'mbp16',
            'source_fs_uuid': U, 'receiver_fs_uuid': U,
            'source_snapshot_root': str(self.snapshots), 'remote_root': str(self.remote)}))
        self.env = dict(self.b.env, WSCONFIG=str(ROOT),
                        XDG_CONFIG_HOME=str(self.b.root / 'config'),
                        XDG_STATE_HOME=str(self.b.root / 'state'))

    def cli(self, *args):
        return subprocess.run([str(ROOT / 'bin/wsbackup'), *args], env=self.env,
                              text=True, capture_output=True)

    def test_successful_send_records_verified_parent_and_payload(self):
        p = self.cli('send', 'home')
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        id = result['home']['id']
        self.assertEqual((self.remote / 'mbp16/home' / id / 'payload').read_text(), 'preserved data')
        q = self.cli('status')
        self.assertEqual(json.loads(q.stdout)['last_success']['home']['id'], id)

    def test_failed_stream_preserves_previous_success(self):
        first = self.cli('send', 'home')
        self.assertEqual(first.returncode, 0, first.stderr)
        previous = json.loads(first.stdout)['home']['id']
        self.b.update(send_error=True)
        failed = self.cli('send', 'home')
        self.assertNotEqual(failed.returncode, 0)
        last = json.loads(self.cli('status').stdout)['last_success']['home']['id']
        self.assertEqual(last, previous)

    def test_second_send_uses_verified_parent(self):
        first = self.cli('send', 'home')
        self.assertEqual(first.returncode, 0, first.stderr)
        id = json.loads(first.stdout)['home']['id']
        second = self.cli('send', 'home')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)['home']['parent'], id)
        self.assertEqual(json.loads(second.stdout)['home']['mode'], 'incremental')

    def test_concurrent_backup_refused_before_snapshot(self):
        state = self.b.root / 'state/workstation/backup'
        state.mkdir(parents=True)
        with (state / 'lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            p = self.cli('send', 'home')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('backup busy', p.stderr)
        self.assertEqual(list(self.snapshots.iterdir()), [])

    def test_missing_remote_parent_is_explicit_full_backup(self):
        first = self.cli('send', 'home')
        self.assertEqual(first.returncode, 0, first.stderr)
        id = json.loads(first.stdout)['home']['id']
        # Model an operator moving the remote parent aside, not Btrfs deletion.
        (self.remote / 'mbp16/home' / id).rename(self.remote / 'saved-parent')
        second = self.cli('send', 'home')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)['home']['mode'], 'full')

    def test_writable_remote_parent_is_rejected(self):
        first = self.cli('send', 'home')
        self.assertEqual(first.returncode, 0, first.stderr)
        id = json.loads(first.stdout)['home']['id']
        meta = self.remote / 'mbp16/home' / id / '.fixture-meta'
        data = json.loads(meta.read_text()); data['ro'] = False
        meta.write_text(json.dumps(data))
        p = self.cli('send', 'home')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('not read-only', p.stderr)
        self.assertEqual(len(list((self.snapshots / 'home').iterdir())), 1)

    def test_nonempty_restore_target_is_never_overwritten(self):
        target = self.b.root / 'restore'
        target.mkdir()
        target.joinpath('important').write_text('do not overwrite')
        p = self.cli('restore-test', 'home', 'unknown', str(target), '--verify', 'payload')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('empty directory', p.stderr)
        self.assertEqual(target.joinpath('important').read_text(), 'do not overwrite')

    def test_backup_failure_journal_and_lock_release(self):
        self.b.update(send_error=True)
        p = self.cli('send', 'home')
        self.assertNotEqual(p.returncode, 0)
        state = self.b.root / 'state/workstation/backup'
        records = [json.loads(x.read_text()) for x in (state / 'operations').glob('*.json')]
        self.assertEqual(records[0]['status'], 'failed')
        self.assertIn('transfer', records[0]['phase'])
        self.b.update()
        p = self.cli('send', 'home')
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_sigterm_records_failure_and_releases_lock(self):
        self.b.update(receive_delay=10)
        p = subprocess.Popen([str(ROOT / 'bin/wsbackup'), 'send', 'home'],
                             env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        operations = self.b.root / 'state/workstation/backup/operations'
        deadline = time.monotonic() + 8
        try:
            while time.monotonic() < deadline:
                files = list(operations.glob('*.json'))
                if files and 'transfer' in json.loads(files[0].read_text())['phase']:
                    break
                time.sleep(.05)
            else:
                self.fail('transfer did not start')
            p.send_signal(signal.SIGTERM)
            p.communicate(timeout=8)
            record = json.loads(files[0].read_text())
            self.assertEqual(record['status'], 'failed')
            with (operations.parent / 'lock').open('r+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            if p.poll() is None:
                p.kill(); p.communicate()

    def test_restore_checks_files_in_separate_empty_directory(self):
        first = self.cli('send', 'home')
        self.assertEqual(first.returncode, 0, first.stderr)
        id = json.loads(first.stdout)['home']['id']
        target = self.b.root / 'restore'
        target.mkdir(mode=0o700)
        p = self.cli('restore-test', 'home', id, str(target), '--verify', 'payload')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((target / id / 'payload').read_text(), 'preserved data')
        self.assertTrue(json.loads(self.cli('status').stdout)['restore_tests'])

    def test_checksum_mismatch_does_not_record_verified_restore(self):
        first = self.cli('send', 'home')
        self.assertEqual(first.returncode, 0, first.stderr)
        id = json.loads(first.stdout)['home']['id']
        (self.remote / 'mbp16/home' / id / 'payload').write_text('corrupted')
        target = self.b.root / 'restore'
        target.mkdir(mode=0o700)
        p = self.cli('restore-test', 'home', id, str(target), '--verify', 'payload')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('checksum mismatch', p.stderr)
        self.assertFalse(json.loads(self.cli('status').stdout)['restore_tests'])


class BackupCLI(unittest.TestCase):
    def run_cli(self, *args):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, WSCONFIG=str(ROOT), XDG_CONFIG_HOME=d,
                       XDG_STATE_HOME=d)
            return subprocess.run([str(ROOT / 'bin/ws'), 'backup', *args],
                                  env=env, text=True, capture_output=True)

    def test_plan_without_address_is_useful_and_successful(self):
        p = self.run_cli('plan', 'all')
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        self.assertFalse(result['configured'])
        self.assertEqual(result['sources'], {'home': '/home', 'vms': '/var/lib/vms'})
        self.assertIn('ssh_host', result['missing'])

    def test_send_without_config_refuses_before_privilege_or_network(self):
        p = self.run_cli('send', 'home')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('configuration incomplete', p.stderr)

    def test_status_without_config_reports_unconfigured(self):
        p = self.run_cli('status')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(json.loads(p.stdout)['configured'])


if __name__ == '__main__':
    unittest.main()
