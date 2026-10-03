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


if __name__ == '__main__':
    unittest.main()
