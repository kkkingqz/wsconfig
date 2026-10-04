import json
from pathlib import Path
import tempfile
import unittest
from recovery_fixture import FakePlatform, point, received, U, V
try:
    import recovery_platform as platform_module
    import recovery_transaction as transaction
except ImportError:
    platform_module = transaction = None


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(transaction, 'offline recovery preflight missing')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.top = Path(self.temp.name)
        self.platform = FakePlatform(self.top)
        self.selection = point()

    def preflight(self, home=True):
        selection = dict(self.selection, home=self.selection['home'] if home else None)
        return transaction.preflight(self.top, selection, received(self.top), self.platform)

    def test_correct_target_and_pair_are_accepted(self):
        target = self.platform.verify_target('/dev/fixture', U)
        self.assertEqual(target['uuid'], U)
        checked = self.preflight()
        self.assertEqual(checked['old']['system']['uuid'], self.platform.old_root['uuid'])
        self.assertEqual(checked['old']['home']['uuid'], self.platform.old_home['uuid'])

    def test_wrong_duplicate_or_active_filesystem_refused(self):
        with self.assertRaises(ValueError):
            self.platform.verify_target('/dev/fixture', V)
        self.platform.devices.append(dict(self.platform.devices[0], path='/dev/other'))
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.platform.verify_target('/dev/fixture', U)
        self.platform.devices.pop()
        for target in ('/', '/home', '/media/ubuntu/auto'):
            self.platform.mounts = [dict(uuid=U, target=target, source='/dev/fixture', fstype='btrfs')]
            with self.assertRaisesRegex(ValueError, 'mounted'):
                self.platform.verify_target('/dev/fixture', U)

    def test_swap_on_target_refused(self):
        self.platform.swaps += '/dev/fixture\tpartition\t100\t0\t-2\n'
        with self.assertRaisesRegex(ValueError, 'swap'):
            self.platform.verify_target('/dev/fixture', U)

    def test_missing_home_never_falls_back(self):
        self.assertEqual(self.preflight(home=False)['old']['home'], None)
        bad = point(home=False)
        target = self.platform.verify_target('/dev/fixture', U)
        with self.assertRaisesRegex(ValueError, 'HOME'):
            transaction.build_plan(bad, target, True)

    def test_wrong_received_uuid_or_writable_snapshot_refused(self):
        path = self.top / 'received/system/ts-system/.meta'
        original = path.read_text()
        for key, value in [('received_uuid', V), ('readonly', False)]:
            metadata = json.loads(original); metadata[key] = value
            path.write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                self.preflight()

    def test_fstab_uuid_and_missing_mount_refused_before_snapshot(self):
        path = self.top / 'received/system/ts-system/etc/fstab'
        original = path.read_text()
        for text in (original.replace(U, V), original.replace('@nix', '@missing')):
            path.write_text(text)
            with self.assertRaises(ValueError):
                self.preflight()
        self.assertFalse(any(a[:3] == ['btrfs', 'subvolume', 'snapshot'] for a in self.platform.calls))

    def test_missing_kernel_initrd_modules_refused(self):
        kernel = self.top / 'received/system/ts-system/boot/initrd.img-6.8-t2'
        kernel.unlink()
        with self.assertRaisesRegex(ValueError, 'initrd'):
            self.preflight()

    def test_absolute_boot_symlink_is_resolved_inside_target_tree(self):
        root = self.top / 'received/system/ts-system'
        kernel = root / 'boot/vmlinuz'; kernel.unlink()
        kernel.symlink_to('/boot/vmlinuz-6.8-t2')
        self.preflight()
        kernel.unlink(); kernel.symlink_to('../../../../outside')
        with self.assertRaises(ValueError):
            self.preflight()

    def test_unknown_boot_format_refuses(self):
        path = self.top / 'received/system/ts-system/boot/refind_linux.conf'
        path.write_text('include random.conf\n')
        with self.assertRaises(ValueError):
            self.preflight()

    def test_prepare_changes_only_writable_candidates(self):
        root = self.top / 'received/system/ts-system'
        fstab = root / 'etc/fstab'
        fstab.write_text(fstab.read_text().replace('subvol=@,', 'subvolid=999,')
                         .replace('subvol=@ ', 'subvolid=999 '))
        boot = root / 'boot/refind_linux.conf'
        original_boot = boot.read_text()
        checked = self.preflight()
        prepared = transaction.prepare_candidates(self.top, checked, self.platform)
        candidate = self.top / prepared['candidates']['system']['path']
        self.assertFalse(self.platform.inspect_snapshot(candidate)['readonly'])
        self.assertIn('noresume', (candidate / 'boot/refind_linux.conf').read_text())
        self.assertIn('subvol=@', (candidate / 'etc/fstab').read_text())
        self.assertEqual(boot.read_text(), original_boot)
        self.assertTrue(self.platform.info(root)['readonly'])
        self.assertEqual(self.platform.info(self.top / '@')['uuid'], self.platform.old_root['uuid'])

    def test_received_symlink_cannot_escape(self):
        original = self.top / 'received/system/ts-system'
        outside = self.top / 'outside'; original.rename(outside)
        original.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.preflight()

    def test_unknown_fstab_filesystem_and_root_layout_refused(self):
        path = self.top / 'received/system/ts-system/etc/fstab'
        original = path.read_text()
        for text in [original.replace('btrfs', 'ext4'), original.replace('subvol=@ ', 'subvol=@wrong ')]:
            path.write_text(text)
            with self.assertRaises(ValueError):
                self.preflight()

    def test_prepare_refuses_existing_candidate_path(self):
        checked = self.preflight()
        candidate = self.top / ('@restore-' + checked['id'])
        candidate.mkdir(); (candidate / 'important').write_text('unrelated')
        with self.assertRaises(ValueError):
            transaction.prepare_candidates(self.top, checked, self.platform)
        self.assertEqual((candidate / 'important').read_text(), 'unrelated')

    def test_boot_rootflags_numeric_and_home_fstab_numeric_become_paths(self):
        root = self.top / 'received/system/ts-system'
        boot = root / 'boot/refind_linux.conf'
        boot.write_text(boot.read_text().replace('subvol=@', 'subvolid=987'))
        fstab = root / 'etc/fstab'
        fstab.write_text(fstab.read_text().replace('subvol=@home', 'subvolid=988'))
        checked = self.preflight()
        self.assertIn('subvol=@home', checked['boot']['fstab'])
        self.assertIn('rootflags=subvol=@', checked['boot']['refind'])

    def test_missing_root_or_home_refuses(self):
        import shutil
        for name in ('@', '@home'):
            saved = self.top / (name + '-temporary')
            (self.top / name).rename(saved)
            with self.assertRaises((ValueError, OSError)):
                self.preflight()
            saved.rename(self.top / name)


if __name__ == '__main__':
    unittest.main()
