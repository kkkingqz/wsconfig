"""NAS recovery metadata is required before pruning local Timeshift copies."""
import json
from pathlib import Path
import unittest
import sys
from unittest.mock import patch

from test_backup_timeshift import TransferFixture
from backup_fixture import U
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import backup
import backup_timeshift as batch


class BackupCatalog(TransferFixture, unittest.TestCase):
    def successful_remote_record(self):
        record = dict(id='ts-old', scope='system', owner='timeshift',
                      source_uuid=U, origin_uuid='22222222-2222-2222-2222-222222222222',
                      identity=backup.identity(self.c), status='success', local_present=False,
                      timeshift_name='2026-10-01_12-00-00', timestamp=1790856000)
        remote = self.remote_root / 'mbp16/system/ts-old'
        for path in (self.remote_root / 'mbp16', self.remote_root / 'mbp16/system', remote):
            path.mkdir(mode=0o700)
        (remote / '.fixture-meta').write_text(json.dumps(dict(uuid=record['origin_uuid'],
                                                              received_uuid=U, ro=True)))
        (remote / 'payload').write_text('old snapshot without local source')
        batch.save_record(self.state, record)
        return record

    def test_backfill_without_local_or_timeshift_source(self):
        record = self.successful_remote_record()
        self.assertTrue(hasattr(batch, 'publish_catalog'), 'catalog publication missing')
        result = batch.publish_catalog(self.c, self.state, [record])
        self.assertEqual(result['published'], ['ts-old'])
        metadata = self.remote_root / 'mbp16/.catalog/system/ts-old.json'
        self.assertEqual(json.loads(metadata.read_text())['source_fs_uuid'], U)
        journal = json.loads(batch.record_path(self.state, record).read_text())
        self.assertTrue(journal['catalog_published'])
        self.assertFalse(journal['local_present'])

    def test_empty_inventory_still_backfills_available_history(self):
        self.successful_remote_record()
        result = batch.run_batch(self.c, self.state)
        self.assertEqual(result.get('catalog', {}).get('published'), ['ts-old'])
        self.assertEqual(result['transferred'], [])

    def test_missing_remote_is_never_published(self):
        import shutil
        record = self.successful_remote_record()
        shutil.rmtree(self.remote_root / 'mbp16/system/ts-old')
        self.assertTrue(hasattr(batch, 'publish_catalog'), 'catalog publication missing')
        result = batch.publish_catalog(self.c, self.state, [record])
        self.assertEqual(result['missing'], ['ts-old'])
        self.assertFalse((self.remote_root / 'mbp16/.catalog').exists())

    def test_old_receiver_refuses_before_inventory(self):
        with patch.object(backup, 'probe', return_value={'scopes': ['system', 'home']}), \
                patch.object(backup, 'command', side_effect=AssertionError('inventory executed')):
            with self.assertRaisesRegex(ValueError, 'catalog'):
                batch.run_batch(self.c, self.state)

    def test_publication_failure_forbids_cleanup(self):
        self.successful_remote_record()
        with patch.object(batch, 'publish_catalog', create=True, side_effect=ValueError('catalog failure')), \
                patch.object(batch, 'cleanup_copies', side_effect=AssertionError('cleanup executed')):
            with self.assertRaisesRegex(ValueError, 'catalog failure'):
                batch.run_batch(self.c, self.state)

    def test_wrong_acknowledgement_is_not_published(self):
        record = self.successful_remote_record()
        self.assertTrue(hasattr(batch, 'publish_catalog'), 'catalog publication missing')
        original = backup.remote

        def altered(c, words, **kwargs):
            result = original(c, words, **kwargs)
            if words[0] == 'catalog-put':
                result['timestamp'] += 1
            return result

        with patch.object(backup, 'remote', side_effect=altered):
            with self.assertRaisesRegex(ValueError, 'acknowledgement'):
                batch.publish_catalog(self.c, self.state, [record])
        saved = json.loads(batch.record_path(self.state, record).read_text())
        self.assertFalse(saved.get('catalog_published', False))

    def test_repeated_put_recovers_after_disconnected_ack(self):
        record = self.successful_remote_record()
        self.assertTrue(hasattr(batch, 'publish_catalog'), 'catalog publication missing')
        original = backup.remote

        def disconnected(c, words, **kwargs):
            result = original(c, words, **kwargs)
            if words[0] == 'catalog-put':
                raise OSError('disconnected after put')
            return result

        with patch.object(backup, 'remote', side_effect=disconnected):
            with self.assertRaises(OSError):
                batch.publish_catalog(self.c, self.state, [record])
        self.b.update(timeshift_top=str(self.top), send_error=True)
        self.assertEqual(batch.publish_catalog(self.c, self.state, [record])['published'], ['ts-old'])

    def test_journal_failure_does_not_report_metadata_success(self):
        record = self.successful_remote_record()
        self.assertTrue(hasattr(batch, 'publish_catalog'), 'catalog publication missing')
        with patch.object(batch, 'save_record', side_effect=OSError('journal fsync failed')):
            with self.assertRaises(OSError):
                batch.publish_catalog(self.c, self.state, [record])
        self.assertFalse(json.loads(batch.record_path(self.state, record).read_text()).get('catalog_published', False))


if __name__ == '__main__':
    unittest.main()
