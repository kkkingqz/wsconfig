import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from backup_fixture import Boundary, U

ROOT = Path(__file__).resolve().parents[1]


class TimeshiftBoundary(unittest.TestCase):
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
