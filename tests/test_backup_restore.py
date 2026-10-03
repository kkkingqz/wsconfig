from pathlib import Path
import subprocess
import unittest
from backup_fixture import Boundary, U

ROOT = Path(__file__).resolve().parents[1]


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.b = Boundary()
        self.addCleanup(self.b.close)

    def restore(self, target):
        return subprocess.run(['bash', str(ROOT / 'backup/wsbackup-restore'),
                               '--uuid', U, '--target', target, 'receive', 'test-id', U],
                              env=self.b.env, text=True, input='', capture_output=True)

    def test_noncanonical_live_paths_refused_before_filesystem_access(self):
        for target in ('/var/./lib/vms/empty-dir', '/var//lib/vms/empty-dir'):
            with self.subTest(target=target):
                p = self.restore(target)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn('unsafe path', p.stderr)

    def test_live_libvirt_bind_destinations_refused(self):
        for target in ('/var/lib/libvirt/images/empty-dir', '/etc/libvirt/empty-dir'):
            with self.subTest(target=target):
                p = self.restore(target)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn('outside live sources', p.stderr)

    def test_wrong_filesystem_refused_before_receive(self):
        target = self.b.root / 'restore'
        target.mkdir()
        self.b.update(uuid='22222222-2222-2222-2222-222222222222')
        p = self.restore(str(target))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('wrong filesystem UUID', p.stderr)
        self.assertEqual(list(target.iterdir()), [])
