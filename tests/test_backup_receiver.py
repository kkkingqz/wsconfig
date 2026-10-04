import json
from pathlib import Path
import subprocess
import unittest
import fcntl
from backup_fixture import Boundary, U

ROOT = Path(__file__).resolve().parents[1]


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.b = Boundary()
        self.addCleanup(self.b.close)
        self.destination = self.b.root / 'destination'
        self.destination.mkdir(mode=0o700)
        self.config = self.b.root / 'receiver.conf'
        self.config.write_text(f'ROOT={self.destination}\nFS_UUID={U}\nHOST_ID=mbp16\n')
        self.config.chmod(0o600)

    def receiver(self, command, data=''):
        env = dict(self.b.env, SSH_ORIGINAL_COMMAND=command)
        return subprocess.run(['bash', str(ROOT / 'backup/unraid/wsbackup-receiver'), str(self.config)],
                              env=env, input=data, text=True, capture_output=True)

    def test_injection_rejected_without_side_effect(self):
        p = self.receiver('probe mbp16; touch /tmp/evil')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('invalid command', p.stderr)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_symlink_destination_refused(self):
        link = self.b.root / 'link'
        link.symlink_to(self.destination)
        self.config.write_text(f'ROOT={link}\nFS_UUID={U}\nHOST_ID=mbp16\n')
        p = self.receiver('probe mbp16')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('symlink', p.stderr)

    def test_receive_validates_and_publishes_snapshot(self):
        data = json.dumps({'name': 'test-id', 'uuid': U, 'payload': 'preserved data'})
        p = self.receiver(f'receive mbp16 home test-id {U}', data)
        self.assertEqual(p.returncode, 0, p.stderr)
        final = self.destination / 'mbp16/home/test-id'
        self.assertEqual((final / 'payload').read_text(), 'preserved data')
        q = self.receiver('inspect mbp16 home test-id')
        self.assertEqual(json.loads(q.stdout)['received_uuid'], U)

    def test_uuid_mismatch_never_publishes(self):
        data = json.dumps({'name': 'test-id', 'uuid': U, 'payload': 'preserved data'})
        wrong = '22222222-2222-2222-2222-222222222222'
        p = self.receiver(f'receive mbp16 home test-id {wrong}', data)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('received UUID mismatch', p.stderr)
        self.assertFalse((self.destination / 'mbp16/home/test-id').exists())
        self.assertTrue((self.destination / 'mbp16/home/.partial-test-id').exists())

    def test_duplicate_snapshot_preserves_original(self):
        data = json.dumps({'name': 'test-id', 'uuid': U, 'payload': 'original'})
        first = self.receiver(f'receive mbp16 home test-id {U}', data)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.receiver(f'receive mbp16 home test-id {U}', data.replace('original', 'changed'))
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual((self.destination / 'mbp16/home/test-id/payload').read_text(), 'original')

    def test_busy_receiver_does_not_start_receive(self):
        with (self.destination / '.receiver.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            p = self.receiver(f'receive mbp16 home test-id {U}')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('receiver busy', p.stderr)
        self.assertFalse((self.destination / 'mbp16').exists())

    def test_wrong_filesystem_rejected(self):
        self.b.update(uuid='22222222-2222-2222-2222-222222222222')
        p = self.receiver('probe mbp16')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('wrong filesystem UUID', p.stderr)

    def catalog_command(self, **changes):
        values = dict(scope='system', id='ts-test', source_uuid=U,
                      origin_uuid='22222222-2222-2222-2222-222222222222',
                      source_fs_uuid=U, timestamp='1791018000', name='2026-10-03_10-00-00')
        values.update(changes)
        return 'catalog-put mbp16 ' + ' '.join(values.values())

    def received_for_catalog(self):
        p = self.receiver(f'receive mbp16 system ts-test {U}',
                          json.dumps({'name': 'ts-test', 'uuid': U, 'payload': 'preserved data'}))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_catalog_put_list_and_idempotent_acknowledgement(self):
        self.received_for_catalog()
        first = self.receiver(self.catalog_command())
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)['timeshift_name'], '2026-10-03_10-00-00')
        second = self.receiver(self.catalog_command())
        self.assertEqual(second.returncode, 0, second.stderr)
        listing = self.receiver('catalog-list mbp16')
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(json.loads(listing.stdout)['id'], 'ts-test')

    def test_catalog_conflicting_record_preserves_first(self):
        self.received_for_catalog()
        first = self.receiver(self.catalog_command())
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.receiver(self.catalog_command(timestamp='1791018001'))
        self.assertNotEqual(second.returncode, 0)
        self.assertIn('conflict', second.stderr)
        self.assertEqual(self.receiver('catalog-list mbp16').stdout, first.stdout)

    def test_catalog_missing_wrong_or_writable_snapshot_refused(self):
        missing = self.receiver(self.catalog_command())
        self.assertNotEqual(missing.returncode, 0)
        self.received_for_catalog()
        wrong = self.receiver(self.catalog_command(source_uuid='33333333-3333-3333-3333-333333333333'))
        self.assertNotEqual(wrong.returncode, 0)
        meta = self.destination / 'mbp16/system/ts-test/.fixture-meta'
        data = json.loads(meta.read_text()); data['ro'] = False; meta.write_text(json.dumps(data))
        writable = self.receiver(self.catalog_command())
        self.assertNotEqual(writable.returncode, 0)
        self.assertFalse((self.destination / 'mbp16/.catalog/system/ts-test.json').exists())

    def test_catalog_missing_remote_snapshot_is_excluded(self):
        import shutil
        self.received_for_catalog()
        put = self.receiver(self.catalog_command())
        self.assertEqual(put.returncode, 0, put.stderr)
        shutil.rmtree(self.destination / 'mbp16/system/ts-test')
        listing = self.receiver('catalog-list mbp16')
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(listing.stdout, '')
        self.assertIn('missing', listing.stderr)

    def test_catalog_corrupt_symlink_and_writable_record_refused(self):
        self.received_for_catalog()
        put = self.receiver(self.catalog_command())
        self.assertEqual(put.returncode, 0, put.stderr)
        path = self.destination / 'mbp16/.catalog/system/ts-test.json'
        path.write_text('{"schema_version":1}')
        self.assertNotEqual(self.receiver('catalog-list mbp16').returncode, 0)
        path.unlink(); path.symlink_to(self.config)
        self.assertNotEqual(self.receiver('catalog-list mbp16').returncode, 0)
        path.unlink()
        self.assertEqual(self.receiver(self.catalog_command()).returncode, 0)
        path.chmod(0o666)
        self.assertNotEqual(self.receiver('catalog-list mbp16').returncode, 0)

    def test_catalog_unsafe_arguments_are_refused_without_metadata(self):
        for changes in [dict(name='../evil'), dict(timestamp='01'),
                        dict(scope='vms'), dict(name='2026-02-30_10-00-00')]:
            with self.subTest(changes=changes):
                p = self.receiver(self.catalog_command(**changes))
                self.assertNotEqual(p.returncode, 0)
        self.assertFalse((self.destination / 'mbp16/.catalog').exists())

    def test_catalog_directory_symlink_and_permissions_refused(self):
        self.received_for_catalog()
        directory = self.destination / 'mbp16/.catalog'
        directory.symlink_to(self.b.root)
        self.assertNotEqual(self.receiver(self.catalog_command()).returncode, 0)
        directory.unlink(); directory.mkdir(mode=0o777); directory.chmod(0o777)
        self.assertNotEqual(self.receiver(self.catalog_command()).returncode, 0)

    def test_catalog_record_wrong_owner_refused(self):
        self.received_for_catalog()
        self.assertEqual(self.receiver(self.catalog_command()).returncode, 0)
        path = self.destination / 'mbp16/.catalog/system/ts-test.json'
        # Substitute only the stat ownership boundary: retain real files,
        # receiver execution and all other stat responses.
        fake = self.b.bin / 'stat'
        fake.write_text('#!/usr/bin/env python3\nimport os,sys\n'
                        'if sys.argv[1:3]==["-c","%u"] and sys.argv[-1]==os.environ["WRONG_OWNER"]:\n'
                        ' print(os.geteuid()+1)\n'
                        'else: os.execv("/usr/bin/stat",["stat",*sys.argv[1:]])\n')
        fake.chmod(0o755)
        self.b.env['WRONG_OWNER'] = str(path)
        rejected = self.receiver('catalog-list mbp16')
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('owner', rejected.stderr)

    def test_catalog_rechecks_uuid_during_list(self):
        self.received_for_catalog()
        self.assertEqual(self.receiver(self.catalog_command()).returncode, 0)
        meta = self.destination / 'mbp16/system/ts-test/.fixture-meta'
        data = json.loads(meta.read_text())
        data['received_uuid'] = '33333333-3333-3333-3333-333333333333'
        meta.write_text(json.dumps(data))
        listing = self.receiver('catalog-list mbp16')
        self.assertNotEqual(listing.returncode, 0)
        self.assertIn('UUID', listing.stderr)


if __name__ == '__main__':
    unittest.main()
