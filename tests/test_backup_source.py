import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from backup_fixture import Boundary

ROOT = Path(__file__).resolve().parents[1]
U = '11111111-1111-1111-1111-111111111111'


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.b = Boundary()
        self.addCleanup(self.b.close)
        self.snapshots = self.b.root / 'snapshots'
        self.snapshots.mkdir()

    def source(self, action='snapshot', scope='home', id='test-id'):
        return subprocess.run(['bash', str(self.b.source), '--uuid', U,
                               '--root', str(self.snapshots), action, scope, id],
                              env=self.b.env, text=True, capture_output=True)

    def test_wrong_filesystem_refuses_without_snapshot(self):
        self.b.update(uuid='22222222-2222-2222-2222-222222222222')
        p = self.source()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('wrong filesystem UUID', p.stderr)
        self.assertEqual(list(self.snapshots.iterdir()), [])

    def test_nested_subvolume_refuses_without_snapshot(self):
        self.b.update(nested='ID 400 gen 20 top level 256 path @home/nested')
        p = self.source()
        self.assertIn('nested subvolumes', p.stderr)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(list(self.snapshots.iterdir()), [])

    def test_running_vm_refuses_before_snapshot(self):
        self.b.update(active_vm='running-guest\n')
        p = self.source(scope='vms')
        self.assertIn('running VMs', p.stderr)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(list(self.snapshots.iterdir()), [])

    def test_libvirt_error_is_not_treated_as_empty_list(self):
        self.b.update(virsh_error=True)
        p = self.source(scope='vms')
        self.assertIn('cannot query libvirt', p.stderr)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(list(self.snapshots.iterdir()), [])

    def test_success_creates_read_only_snapshot_and_inspects_uuid(self):
        p = self.source()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.snapshots / 'home/test-id/payload').exists())
        q = self.source('inspect')
        self.assertEqual(q.returncode, 0, q.stderr)
        import json
        import uuid
        self.assertNotEqual(json.loads(q.stdout)['uuid'], U)
        uuid.UUID(json.loads(q.stdout)['uuid'])
        self.assertTrue(json.loads(q.stdout)['ro'])

    def test_path_in_home_refused_before_snapshot(self):
        p = subprocess.run(['bash', str(ROOT / 'backup/wsbackup-source'), '--uuid', U,
                            '--root', '/home/backup', 'snapshot', 'home', 'safe-id'],
                           text=True, capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('outside sources', p.stderr)

    def test_traversal_id_refused(self):
        p = subprocess.run(['bash', str(ROOT / 'backup/wsbackup-source'), '--uuid', U,
                            '--root', '/var/lib/workstation-backup', 'inspect', 'home', '../escape'],
                           text=True, capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('invalid ID', p.stderr)


if __name__ == '__main__':
    unittest.main()
