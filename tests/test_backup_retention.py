import json
from pathlib import Path
import shutil
import unittest
from test_backup_timeshift import TransferFixture


class RetentionTests(TransferFixture, unittest.TestCase):
    def batch(self):
        from backup_timeshift import run_batch
        return run_batch(self.c, self.state)

    def test_success_keeps_one_copy_per_scope(self):
        from backup_timeshift import cleanup_copies
        self.snapshot(); self.snapshot('2026-10-02_12-00-00')
        result = self.batch()
        self.assertEqual(len(list(self.managed.glob('*/*'))), 2)
        self.assertEqual(len(result['cleanup']['deleted']), 2)
        self.assertEqual(len(list((self.state / 'timeshift/records').glob('*.json'))), 4)

    def test_failed_batch_never_calls_delete(self):
        from backup_timeshift import cleanup_copies
        self.snapshot(); self.snapshot('2026-10-02_12-00-00')
        self.b.update(timeshift_top=str(self.top), send_fail_at=3)
        with self.assertRaisesRegex(ValueError, 'stream failed'):
            self.batch()
        self.assertFalse(self.b.config.with_suffix('.delete-count').exists())
        self.assertEqual(len(list(self.managed.glob('*/*'))), 3)

    def test_interrupted_cleanup_resumes_without_parent_loss(self):
        from backup_timeshift import cleanup_copies
        self.snapshot(); self.snapshot('2026-10-02_12-00-00')
        self.b.update(timeshift_top=str(self.top), delete_fail_at=2)
        with self.assertRaisesRegex(ValueError, 'command failed'):
            self.batch()
        retained = json.loads((self.state / 'timeshift/parents.json').read_text())
        for scope, r in retained.items():
            self.assertTrue((self.managed / scope / r['id']).exists())
        self.b.update(timeshift_top=str(self.top))
        result = self.batch()
        self.assertEqual(result['transferred'], [])
        self.assertEqual(len(list(self.managed.glob('*/*'))), 2)
        self.assertEqual({k: v['id'] for k, v in retained.items()}, {k: v['id'] for k, v in result['retained'].items()})

    def test_unchanged_batch_finishes_cleanup(self):
        from backup_timeshift import cleanup_copies
        self.snapshot(); first = self.batch(); again = self.batch()
        self.assertEqual(again['transferred'], [])
        self.assertEqual(again['cleanup']['deleted'], [])
        self.assertEqual(len(list(self.managed.glob('*/*'))), 2)

    def test_delete_refuses_retained_id(self):
        from backup_timeshift import cleanup_copies
        u = self.copy()
        p = self.helper('delete', 'system', 'copy1', u, 'copy1', u)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('retained', p.stderr)
        self.assertTrue((self.managed / 'system/copy1').exists())

    def test_unknown_writable_or_changed_uuid_never_deleted(self):
        from backup_timeshift import cleanup_copies
        u = self.copy()
        clone = self.helper('clone', 'system', 'copy2', 'copy1', u)
        retained_uuid = json.loads(clone.stdout)['uuid']
        meta = self.managed / 'system/copy1/.fixture-meta'
        initial = json.loads(meta.read_text())
        for change in ({'ro': False}, {'uuid': '22222222-2222-2222-2222-222222222222'}):
            meta.write_text(json.dumps(dict(initial, **change)))
            p = self.helper('delete', 'system', 'copy1', u, 'copy2', retained_uuid)
            self.assertNotEqual(p.returncode, 0)
            self.assertTrue(meta.exists())
        meta.write_text(json.dumps(initial))
        with self.assertRaisesRegex(ValueError, 'unknown'):
            cleanup_copies(self.c, self.state, {})
        self.assertTrue(meta.exists())

    def test_timeshift_and_remote_snapshots_untouched(self):
        from backup_timeshift import cleanup_copies
        self.snapshot(); self.snapshot('2026-10-02_12-00-00')
        self.batch()
        self.assertEqual(len(list(self.store.glob('*/@'))), 2)
        self.assertTrue(all(not json.loads(p.read_text())['ro'] for p in self.store.glob('*/@/.fixture-meta')))
        self.assertEqual(len(list(self.remote_root.glob('mbp16/*/ts-*'))), 4)

    def test_parent_remote_disappears_before_cleanup_refuses(self):
        from backup_timeshift import cleanup_copies
        self.snapshot(); result = self.batch()
        r = result['retained']['home']
        shutil.rmtree(self.remote_root / 'mbp16/home' / r['id'])
        with self.assertRaisesRegex(ValueError, 'retained'):
            cleanup_copies(self.c, self.state, result['retained'])
        self.assertTrue((self.managed / 'home' / r['id']).exists())

    def test_pruned_old_remote_snapshot_is_reimported(self):
        self.snapshot(); self.snapshot('2026-10-02_12-00-00')
        first = self.batch()
        old = first['transferred'][0]
        self.assertFalse((self.managed / old['scope'] / old['id']).exists())
        shutil.rmtree(self.remote_root / 'mbp16' / old['scope'] / old['id'])
        again = self.batch()
        self.assertEqual(len(again['transferred']), 1)
        new = again['transferred'][0]
        self.assertNotEqual(new['id'], old['id'])
        self.assertEqual(new['origin_uuid'], old['origin_uuid'])
        self.assertEqual(again['retained'][old['scope']]['id'], first['retained'][old['scope']]['id'])
