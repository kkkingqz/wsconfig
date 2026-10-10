from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))

import btrfs_layout  # noqa: E402

UUID = '0cfd2add-849f-47b9-865d-2ac821ca529c'

# The fstab curtin wrote on mbp16 (/etc/fstab.pre-btrfs-layout), with a swap
# file as the installer may make one.
INSTALLER = f'''# /etc/fstab: static file system information.
# / was on /dev/nvme0n1p3 during curtin installation
/dev/disk/by-uuid/{UUID} / btrfs defaults 0 1
# /boot/efi was on /dev/nvme0n1p1 during curtin installation
/dev/disk/by-uuid/5F66-17ED /boot/efi vfat defaults 0 1
/dev/disk/by-uuid/c63d7ee6-94d8-4fc4-8de6-0091c2000394 /mnt/apple apfs defaults 0 1
/swap.img none swap sw 0 0
'''

STUB = f'''search.fs_uuid {UUID} root hd0,gpt4
set prefix=($root)'/boot/grub'
configfile $prefix/grub.cfg
'''


def cli(*args, stdin=''):
    return subprocess.run([sys.executable, str(ROOT / 'lib/btrfs_layout.py'), *args],
                          input=stdin, capture_output=True, text=True)


class FstabTests(unittest.TestCase):
    def test_root_line_becomes_the_layout(self):
        lines = btrfs_layout.fstab(INSTALLER, UUID).splitlines()
        mounts = [l.split() for l in lines if l and not l.startswith('#')]
        self.assertEqual([m[1] for m in mounts],
                         ['/', '/home', '/var/cache', '/tmp', '/var/log', '/boot/efi', '/mnt/apple'])
        self.assertEqual(mounts[0], [f'UUID={UUID}', '/', 'btrfs',
                                     'subvol=@,noatime,compress=zstd:1', '0', '0'])
        self.assertEqual(mounts[4][3], 'subvol=@log,noatime,compress=zstd:1')
        self.assertTrue(all(len(m) == 6 for m in mounts))

    def test_swap_file_dropped_partition_kept(self):
        text = INSTALLER + 'UUID=1111-2222 none swap sw 0 0\n'
        out = btrfs_layout.fstab(text, UUID)
        self.assertNotIn('/swap.img', out)
        self.assertIn('UUID=1111-2222 none swap', out)
        self.assertEqual(btrfs_layout.swapfiles(text), ['/swap.img'])

    def test_tmpfs_tmp_gives_way_to_its_subvolume(self):
        out = btrfs_layout.fstab(INSTALLER + 'tmpfs /tmp tmpfs defaults 0 0\n', UUID)
        self.assertEqual([l.split()[1] for l in out.splitlines()
                          if l and not l.startswith('#')].count('/tmp'), 1)

    def test_unknown_layouts_are_refused(self):
        for text in (INSTALLER.replace(UUID, 'ffffffff-0000-0000-0000-000000000000'),
                     INSTALLER + f'UUID={UUID} /home btrfs subvol=@home 0 0\n',
                     INSTALLER + 'UUID=abcd /var/log ext4 defaults 0 2\n',
                     '/dev/disk/by-uuid/5F66-17ED /boot/efi vfat defaults 0 1\n',
                     INSTALLER.replace(' / btrfs', ' / ext4')):
            with self.assertRaises(ValueError):
                btrfs_layout.fstab(text, UUID)


class StubTests(unittest.TestCase):
    def test_prefix_moves_into_the_root_subvolume(self):
        out = btrfs_layout.stub(STUB, UUID)
        self.assertIn("set prefix=($root)'/@/boot/grub'\n", out)
        self.assertIn(f'search.fs_uuid {UUID} root', out)
        self.assertIn('configfile $prefix/grub.cfg', out)
        self.assertEqual(btrfs_layout.prefix(out, UUID), '/@/boot/grub')
        self.assertEqual(btrfs_layout.stub(out, UUID), out)

    def test_stub_of_another_root_or_prefix_is_refused(self):
        with self.assertRaises(ValueError):
            btrfs_layout.prefix(STUB, 'ffffffff-0000-0000-0000-000000000000')
        with self.assertRaises(ValueError):
            btrfs_layout.stub(STUB.replace("'/boot/grub'", "'/grub'"), UUID)
        with self.assertRaises(ValueError):
            btrfs_layout.prefix(f'search.fs_uuid {UUID} root\nnormal\n', UUID)


class CliTests(unittest.TestCase):
    def test_commands(self):
        result = cli('fstab', UUID, stdin=INSTALLER)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, btrfs_layout.fstab(INSTALLER, UUID))
        self.assertEqual(cli('swapfiles', stdin=INSTALLER).stdout, '/swap.img\n')
        self.assertEqual(cli('prefix', UUID, stdin=STUB).stdout, '/boot/grub\n')
        self.assertEqual(cli('stub', UUID, stdin=STUB).stdout, btrfs_layout.stub(STUB, UUID))

    def test_errors_exit_1_and_usage_64(self):
        result = cli('prefix', 'ffffffff-0000-0000-0000-000000000000', stdin=STUB)
        self.assertEqual(result.returncode, 1)
        self.assertIn('btrfs_layout: not a GRUB stub', result.stderr)
        self.assertEqual(cli('nothing').returncode, 64)


if __name__ == '__main__':
    unittest.main()
