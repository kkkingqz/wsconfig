import json
import shutil
import unittest
from test_backup_timeshift import TransferFixture


class RecoveryTests(TransferFixture, unittest.TestCase):
    def test_remote_loss_recovers_surviving_frozen_content(self):
        from backup_timeshift import run_batch
        original = self.snapshot(home=False, payload='frozen')
        first = run_batch(self.c, self.state)
        old = first['retained']['system']
        (original / '@/payload').write_text('edited-after-import')
        shutil.rmtree(self.remote_root / 'mbp16/system' / old['id'])
        result = run_batch(self.c, self.state)
        new = result['retained']['system']
        self.assertNotEqual(new['id'], old['id'])
        self.assertEqual((self.remote_root / 'mbp16/system' / new['id'] / 'payload').read_text(), 'frozen@')
        self.assertEqual((self.managed / 'system' / new['id'] / 'payload').read_text(), 'frozen@')
        history = json.loads((self.state / 'timeshift/records' / (old['id'] + '.json')).read_text())
        self.assertEqual(history['status'], 'success')

    def test_missing_unimported_source_does_not_block_next_inventory(self):
        import backup_timeshift as ts
        original = self.snapshot(home=False)
        self.b.update(timeshift_top=str(self.top), remove_source_on_mount=2,
                      remove_source=str(original))
        with self.assertRaisesRegex(ValueError, 'command failed'):
            ts.run_batch(self.c, self.state)
        records = list((self.state / 'timeshift/records').glob('*.json'))
        self.assertEqual(json.loads(records[0].read_text())['status'], 'importing')
        self.assertFalse(list(self.managed.glob('*/*')))
        self.snapshot('2026-10-02_12-00-00', home=False, payload='healthy')
        result = ts.run_batch(self.c, self.state)
        self.assertEqual(len(result['transferred']), 1)
        retained = result['retained']['system']
        self.assertEqual((self.remote_root / 'mbp16/system' / retained['id'] / 'payload').read_text(), 'healthy@')
        old = json.loads(records[0].read_text())
        self.assertEqual(old['status'], 'abandoned')
        self.assertIn('source disappeared', old['error'])
