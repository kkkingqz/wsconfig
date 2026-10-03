import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch
from backup_fixture import Boundary, U

ROOT = Path(__file__).resolve().parents[1]


class TimeshiftFixture:
    def setUp(self):
        self.b = Boundary()
        self.addCleanup(self.b.close)
        self.top = self.b.root / 'top'
        self.store = self.top / 'timeshift-btrfs/snapshots'
        self.store.mkdir(parents=True)
        self.managed = self.b.root / 'managed'
        self.managed.mkdir(mode=0o700)
        self.b.update(timeshift_top=str(self.top))
        self.env = dict(self.b.env, TMPDIR=str(self.b.root))

    def snapshot(self, name='2026-10-01_12-00-00', home=True, payload='first'):
        directory = self.store / name
        directory.mkdir()
        subvolumes = {'@': ['@', '256', '0', '0', U]}
        for subvol in (['@', '@home'] if home else ['@']):
            path = directory / subvol
            path.mkdir()
            (path / '.fixture-meta').write_text(json.dumps({'uuid': str(uuid.uuid4()), 'ro': False, 'received_uuid': '-'}))
            (path / 'payload').write_text(payload + subvol)
            subvolumes[subvol] = [subvol, '256', '0', '0', U]
        (directory / 'info.json').write_text(json.dumps({'type': 'btrfs', 'created': str(1790856000 + len(list(self.store.iterdir()))), 'sys-uuid': U, 'subvolumes': subvolumes, 'live': 'false'}))
        return directory

    def helper(self, *args):
        return subprocess.run(['bash', str(ROOT / 'backup/wsbackup-timeshift'), '--uuid', U,
                               '--root', str(self.managed), *args], env=self.env,
                              text=True, capture_output=True)

    def inventory(self):
        p = self.helper('inventory')
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)


class TimeshiftBoundary(TimeshiftFixture, unittest.TestCase):

    def test_inventory_oldest_first(self):
        self.snapshot('2026-10-02_12-00-00')
        self.snapshot('2026-10-01_12-00-00')
        # Metadata creation time, not directory traversal order, determines order.
        older = self.store / '2026-10-01_12-00-00/info.json'
        data = json.loads(older.read_text()); data['created'] = '1000'; older.write_text(json.dumps(data))
        rows = self.inventory()['snapshots']
        self.assertEqual(rows[0]['timeshift_name'], '2026-10-01_12-00-00')
        self.assertEqual(len(rows), 4)

    def test_missing_home_reports_coverage(self):
        self.snapshot(home=False)
        result = self.inventory()
        self.assertEqual([r['scope'] for r in result['snapshots']], ['system'])
        self.assertEqual(result['missing_home'], ['2026-10-01_12-00-00'])

    def test_incomplete_metadata_not_imported(self):
        p = self.snapshot(); (p / 'info.json').unlink()
        result = self.inventory()
        self.assertEqual(result['snapshots'], [])
        self.assertTrue(result['excluded'])

    def test_wrong_fs_or_symlink_refused(self):
        self.snapshot()
        self.b.update(timeshift_top=str(self.top), uuid='22222222-2222-2222-2222-222222222222')
        self.assertNotEqual(self.helper('inventory').returncode, 0)
        self.b.update(timeshift_top=str(self.top))
        link = self.b.root / 'linked'; link.symlink_to(self.managed)
        old = self.managed; self.managed = link
        self.assertNotEqual(self.helper('inventory').returncode, 0)
        self.managed = old

    def test_origin_uuid_changed_import_refused(self):
        self.snapshot()
        p = self.helper('import', 'system', 'copy1', '2026-10-01_12-00-00', U)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(list(self.managed.iterdir()), [])

    def test_timeshift_deleted_before_import_refused(self):
        p = self.helper('import', 'system', 'copy1', '2026-10-01_12-00-00', U)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(list(self.managed.iterdir()), [])

    def test_import_keeps_original_writable_and_creates_ro_copy(self):
        original = self.snapshot()
        row = next(r for r in self.inventory()['snapshots'] if r['scope'] == 'system')
        p = self.helper('import', 'system', 'copy1', row['timeshift_name'], row['origin_uuid'])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(json.loads((original / '@/.fixture-meta').read_text())['ro'])
        self.assertTrue(json.loads(p.stdout)['ro'])
        self.assertEqual((self.managed / 'system/copy1/payload').read_text(), 'first@')


class TransferFixture(TimeshiftFixture):
    def setUp(self):
        super().setUp()
        self.remote_root = self.b.root / 'remote'
        self.remote_root.mkdir(mode=0o700)
        cfg = self.b.root / 'receiver.conf'
        cfg.write_text(f'ROOT={self.remote_root}\nFS_UUID={U}\nHOST_ID=mbp16\n')
        cfg.chmod(0o600)
        (self.b.bin / 'sudo').write_text('#!/bin/sh\n[ "$1" != -v ] || exit 0\n[ "$1" != -n ] || shift\nexec "$@"\n')
        (self.b.bin / 'sudo').chmod(0o755)
        ssh = self.b.bin / 'ssh'
        ssh.write_text('#!/usr/bin/env python3\nimport os,sys\nos.environ["SSH_ORIGINAL_COMMAND"]=sys.argv[-1]\nos.execv("/bin/bash",["bash",' + repr(str(ROOT / 'backup/unraid/wsbackup-receiver')) + ',' + repr(str(cfg)) + '])\n')
        ssh.chmod(0o755)
        self.c = {'schema_version': 1, 'ssh_host': 'nas', 'remote_host_id': 'mbp16',
                  'source_fs_uuid': U, 'receiver_fs_uuid': U,
                  'source_snapshot_root': str(self.managed), 'remote_root': str(self.remote_root)}
        self.state = self.b.root / 'state'
        self.environment = patch.dict(os.environ, self.env)
        self.environment.start(); self.addCleanup(self.environment.stop)
        sys.path.insert(0, str(ROOT / 'lib'))

    def copy(self):
        self.snapshot()
        row = next(r for r in self.inventory()['snapshots'] if r['scope'] == 'system')
        p = self.helper('import', 'system', 'copy1', row['timeshift_name'], row['origin_uuid'])
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)['uuid']


class ImportedTransfer(TransferFixture, unittest.TestCase):

    def test_system_receiver_accepts_only_fixed_scope(self):
        from backup_timeshift import send_copy
        record = send_copy(self.c, 'system', 'copy1', self.copy(), None)
        self.assertEqual(record['mode'], 'full')
        self.assertEqual((self.remote_root / 'mbp16/system/copy1/payload').read_text(), 'first@')

    def test_pending_record_precedes_stream(self):
        from backup_timeshift import transfer_record
        u = self.copy()
        path = self.state / 'timeshift/records/copy1.json'
        self.b.update(pending_record_path=str(path))
        record = transfer_record(self.c, self.state, {'scope': 'system', 'id': 'copy1', 'source_uuid': u}, None)
        self.assertEqual(record['status'], 'success')
        self.assertEqual(json.loads(path.read_text())['source_uuid'], u)

    def test_disconnect_after_publish_resumes_without_duplicate(self):
        from backup_timeshift import send_copy, confirm_pending
        u = self.copy()
        record = send_copy(self.c, 'system', 'copy1', u, None)
        self.assertTrue(confirm_pending(self.c, record))
        self.assertFalse(confirm_pending(self.c, dict(record, id='missing')))
        self.assertEqual(len(list((self.remote_root / 'mbp16/system').glob('copy*'))), 1)

    def test_parent_mismatch_refuses(self):
        from backup_timeshift import send_copy
        u = self.copy()
        record = send_copy(self.c, 'system', 'copy1', u, None)
        with self.assertRaisesRegex(ValueError, 'verification'):
            send_copy(self.c, 'system', 'copy1', u, dict(record, source_uuid=U))

    def test_original_timeshift_removed_after_import_still_sends(self):
        from backup_timeshift import send_copy
        import shutil
        u = self.copy()
        shutil.rmtree(self.store)
        send_copy(self.c, 'system', 'copy1', u, None)
        self.assertTrue((self.remote_root / 'mbp16/system/copy1').exists())


class BatchTests(TransferFixture, unittest.TestCase):
    def batch(self):
        from backup_timeshift import run_batch
        return run_batch(self.c, self.state)

    def records(self):
        return [json.loads(p.read_text()) for p in (self.state / 'timeshift/records').glob('*.json')]

    def test_all_existing_sent_oldest_first(self):
        self.snapshot()
        self.snapshot('2026-10-02_12-00-00', payload='next')
        result = self.batch()
        self.assertEqual(len(result['transferred']), 4)
        self.assertEqual([r['mode'] for r in result['transferred']], ['full', 'full', 'incremental', 'incremental'])
        for scope in ('system', 'home'):
            parent = result['retained'][scope]
            self.assertEqual((self.remote_root / 'mbp16' / scope / parent['id'] / 'payload').read_text(), 'next' + ('@' if scope == 'system' else '@home'))

    def test_next_run_only_new_snapshots_incremental(self):
        self.snapshot(); first = self.batch()
        self.snapshot('2026-10-02_12-00-00', payload='next')
        result = self.batch()
        self.assertEqual(len(result['skipped']), 2)
        self.assertEqual(len(result['transferred']), 2)
        for r in result['transferred']:
            self.assertEqual(r['mode'], 'incremental')
            self.assertEqual(r['parent'], first['retained'][r['scope']]['id'])

    def test_confirmed_copies_skipped_after_local_prune(self):
        self.snapshot(); self.snapshot('2026-10-02_12-00-00'); result = self.batch()
        for r in result['transferred'][:2]:
            self.assertFalse((self.managed / r['scope'] / r['id']).exists())
        again = self.batch()
        self.assertEqual(again['transferred'], [])
        self.assertEqual(len(again['skipped']), 4)

    def test_inventory_frozen_during_run(self):
        self.snapshot()
        late = self.snapshot('2026-10-02_12-00-00')
        template = self.b.root / 'late'; late.rename(template)
        self.b.update(timeshift_top=str(self.top), add_snapshot=str(template))
        result = self.batch()
        self.assertEqual(len(result['transferred']), 2)
        self.assertTrue((self.store / '2026-10-02_12-00-00').exists())

    def test_multiple_new_snapshots_chain_in_one_batch(self):
        self.snapshot(); self.batch()
        self.snapshot('2026-10-02_12-00-00', payload='next')
        self.snapshot('2026-10-03_12-00-00', payload='newest')
        result = self.batch()
        self.assertEqual(len(result['transferred']), 4)
        for scope in ('system', 'home'):
            chain = [r for r in result['transferred'] if r['scope'] == scope]
            self.assertEqual(chain[1]['parent'], chain[0]['id'])

    def test_system_home_chains_independent(self):
        self.snapshot(home=False); first = self.batch()
        self.snapshot('2026-10-02_12-00-00', payload='next'); result = self.batch()
        by_scope = {r['scope']: r for r in result['transferred']}
        self.assertEqual(by_scope['home']['mode'], 'full')
        self.assertEqual(by_scope['system']['parent'], first['retained']['system']['id'])

    def test_same_name_new_origin_uuid_not_skipped(self):
        original = self.snapshot(); self.batch()
        meta = original / '@/.fixture-meta'
        data = json.loads(meta.read_text()); data['uuid'] = str(uuid.uuid4()); meta.write_text(json.dumps(data))
        result = self.batch()
        self.assertEqual(len(result['transferred']), 1)
        self.assertEqual(result['transferred'][0]['scope'], 'system')

    def test_missing_remote_old_snapshot_reimported(self):
        import shutil
        self.snapshot(); first = self.batch()
        old = first['retained']['home']
        shutil.rmtree(self.remote_root / 'mbp16/home' / old['id'])
        result = self.batch()
        self.assertEqual(len(result['transferred']), 1)
        self.assertNotEqual(result['transferred'][0]['id'], old['id'])
        self.assertEqual(result['transferred'][0]['mode'], 'full')

    def test_failure_mid_batch_preserves_progress_and_all_local_copies(self):
        self.snapshot(); self.snapshot('2026-10-02_12-00-00')
        self.b.update(timeshift_top=str(self.top), send_fail_at=3)
        with self.assertRaisesRegex(ValueError, 'stream failed'):
            self.batch()
        self.assertEqual(sum(r['status'] == 'success' for r in self.records()), 2)
        self.assertEqual(len(list(self.managed.glob('*/*'))), 3)
        self.b.update(timeshift_top=str(self.top))
        result = self.batch()
        self.assertTrue(all(r['status'] == 'success' for r in result['retained'].values()))

    def test_disconnect_after_publish_resumes_without_duplicate(self):
        self.snapshot(home=False)
        os.environ['FIXTURE_DISCONNECT_ONCE'] = str(self.b.root / 'disconnected')
        ssh = self.b.bin / 'ssh'
        cfg = self.b.root / 'receiver.conf'
        ssh.write_text('#!/usr/bin/env python3\nimport os,sys,subprocess,pathlib\nos.environ["SSH_ORIGINAL_COMMAND"]=sys.argv[-1]\np=subprocess.run(["bash",' + repr(str(ROOT / 'backup/unraid/wsbackup-receiver')) + ',' + repr(str(cfg)) + '])\nmark=pathlib.Path(os.environ["FIXTURE_DISCONNECT_ONCE"])\nif sys.argv[-1].startswith("receive ") and p.returncode==0 and not mark.exists():\n mark.touch();sys.exit(255)\nsys.exit(p.returncode)\n')
        with self.assertRaisesRegex(ValueError, 'stream failed'):
            self.batch()
        result = self.batch()
        self.assertEqual(len(list((self.remote_root / 'mbp16/system').glob('ts-*'))), 1)
        self.assertEqual(result['retained']['system']['status'], 'success')
