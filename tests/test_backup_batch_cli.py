import json
from pathlib import Path
import subprocess
import unittest
from test_backup_timeshift import TransferFixture, ROOT


class BatchCLI(TransferFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.config_dir = self.b.root / 'config/workstation'
        self.config_dir.mkdir(parents=True)
        self.config_file = self.config_dir / 'backup.json'
        self.config_file.write_text(json.dumps(self.c))
        self.state = self.b.root / 'state/workstation/backup'
        self.cli_env = dict(self.env, WSCONFIG=str(ROOT),
                            XDG_CONFIG_HOME=str(self.b.root / 'config'),
                            XDG_STATE_HOME=str(self.b.root / 'state'))

    def cli(self, *args):
        return subprocess.run([str(ROOT / 'bin/ws'), 'backup', *args],
                              env=self.cli_env, text=True, capture_output=True)

    def test_default_cli_runs_batch(self):
        self.snapshot()
        p = self.cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(set(result['retained']), {'system', 'home'})
        status = json.loads(self.cli('status').stdout)['timeshift']
        self.assertEqual(len(status['records']), 2)
        self.assertTrue(all(r['local_present'] for r in status['records']))

    def test_unconfigured_plan_status_have_no_side_effects(self):
        self.config_file.unlink()
        for command in ('plan', 'status'):
            p = self.cli(command)
            self.assertEqual(p.returncode, 0, p.stderr)
            result = json.loads(p.stdout)
            self.assertFalse(result['configured'])
            if command == 'plan':
                self.assertEqual(result['workflow'], 'timeshift-batch')
                self.assertEqual(set(result['sources']), {'system', 'home'})
        self.assertFalse(self.state.exists())
        self.assertEqual(list(self.managed.iterdir()), [])

    def test_unconfigured_backup_refuses_before_sudo_or_ssh(self):
        self.config_file.unlink()
        p = self.cli()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('configuration incomplete', p.stderr)
        self.assertFalse(self.state.exists())
        self.assertEqual(list(self.remote_root.iterdir()), [])

    def test_restore_pruned_copy_reports_missing_baseline(self):
        from backup_timeshift import run_batch
        self.snapshot(); self.snapshot('2026-10-02_12-00-00')
        result = run_batch(self.c, self.state)
        old = result['transferred'][0]
        target = self.b.root / 'restore'; target.mkdir()
        p = self.cli('restore-test', old['scope'], old['id'], str(target), '--verify', 'payload')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('local baseline removed', p.stderr)
        self.assertEqual(list(target.iterdir()), [])
        self.assertFalse((self.state / 'restore-tests').exists())

    def test_retained_system_restore_checks_payload(self):
        from backup_timeshift import run_batch
        self.snapshot(); result = run_batch(self.c, self.state)
        r = result['retained']['system']
        target = self.b.root / 'restore'; target.mkdir()
        p = self.cli('restore-test', 'system', r['id'], str(target), '--verify', 'payload')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((target / r['id'] / 'payload').read_text(), 'first@')
        self.assertTrue((self.state / 'restore-tests' / ('system-' + r['id'] + '.json')).exists())

    def test_restore_deleted_baseline_with_stale_journal_refuses_before_network(self):
        from backup_timeshift import run_batch
        self.snapshot(); self.snapshot('2026-10-02_12-00-00')
        result = run_batch(self.c, self.state)
        old = result['transferred'][0]
        path = self.state / 'timeshift/records' / (old['id'] + '.json')
        record = json.loads(path.read_text())
        # Crash window: deletion succeeded, but its journal update did not.
        record['local_present'] = True
        path.write_text(json.dumps(record))
        marker = self.b.root / 'network-called'
        (self.b.bin / 'ssh').write_text('#!/bin/sh\ntouch ' + str(marker) + '\nexit 255\n')
        target = self.b.root / 'restore'; target.mkdir()
        p = self.cli('restore-test', old['scope'], old['id'], str(target), '--verify', 'payload')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('local baseline removed', p.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(list(target.iterdir()), [])
        self.assertFalse((self.state / 'restore-tests').exists())

    def test_legacy_vm_command_preserved(self):
        p = self.cli('send', 'vms')
        self.assertEqual(p.returncode, 0, p.stderr)
        r = json.loads(p.stdout)['vms']
        self.assertTrue((self.managed / 'vms' / r['id']).exists())
