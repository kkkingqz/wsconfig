"""Real recovery files; only block-device, mount and Btrfs kernel calls are fake."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
try:
    from recovery_platform import RecoveryPlatform
except ImportError:
    RecoveryPlatform = object

U = '11111111-1111-1111-1111-111111111111'
V = '22222222-2222-2222-2222-222222222222'


def point(home=True):
    def record(scope, copy_uuid):
        return dict(schema_version=1, host_id='mbp16', source_fs_uuid=U,
                    scope=scope, id='ts-' + scope, source_uuid=copy_uuid, origin_uuid=copy_uuid,
                    timeshift_name='2026-10-03_10-00-00', timestamp=1791018000)
    return dict(schema_version=1, host_id='mbp16', source_fs_uuid=U,
                timeshift_name='2026-10-03_10-00-00', timestamp=1791018000,
                system=record('system', U), home=record('home', V) if home else None)


class FakePlatform(RecoveryPlatform):
    def __init__(self, top):
        self.top = Path(top)
        self.calls = []
        self.mounts = []
        self.swaps = 'Filename\tType\tSize\tUsed\tPriority\n'
        self.devices = [dict(path='/dev/fixture', fstype='btrfs', uuid=U,
                             model='Fixture SSD', size=107374182400, mountpoints=[None])]
        self.seed(self.top / '@')
        self.seed(self.top / '@home')
        self.seed(self.top / '@nix')
        self.seed(self.top / 'received/system/ts-system', received_uuid=U, readonly=True)
        self.seed(self.top / 'received/home/ts-home', received_uuid=V, readonly=True)
        self.old_root = self.info(self.top / '@')
        self.old_home = self.info(self.top / '@home')
        self.default = self.old_root['subvolume_id']
        self.boot(self.top / '@')
        self.boot(self.top / 'received/system/ts-system')
        (self.top / '@home/current-data').write_text('current HOME')
        (self.top / 'received/home/ts-home/current-data').write_text('historical HOME')

    def seed(self, path, received_uuid=None, readonly=False):
        path.mkdir(parents=True, exist_ok=True)
        metadata = dict(uuid=str(uuid.uuid4()), parent_uuid=None, received_uuid=received_uuid,
                        readonly=readonly, subvolume_id=len(self.calls) + len(list(self.top.rglob('.meta'))) + 256)
        (path / '.meta').write_text(json.dumps(metadata))

    def boot(self, root):
        (root / 'etc').mkdir(exist_ok=True)
        (root / 'etc/fstab').write_text(f'UUID={U} / btrfs subvol=@ 0 0\n'
                                      f'UUID={U} /home btrfs subvol=@home 0 0\n'
                                      f'UUID={U} /nix btrfs subvol=@nix 0 0\n')
        boot = root / 'boot'; boot.mkdir()
        (boot / 'vmlinuz-6.8-t2').write_text('kernel')
        (boot / 'initrd.img-6.8-t2').write_text('initrd')
        (boot / 'vmlinuz').symlink_to('vmlinuz-6.8-t2')
        (boot / 'initrd.img').symlink_to('initrd.img-6.8-t2')
        (boot / 'refind_linux.conf').write_text(
            f'"Ubuntu" "root=UUID={U} rootflags=subvol=@ rw resume=UUID={U} resume_offset=1"\n')
        (root / 'lib/modules/6.8-t2').mkdir(parents=True)

    def info(self, path):
        return json.loads((Path(path) / '.meta').read_text())

    def stat_device(self, device):
        return os.stat_result((stat.S_IFBLK | 0o600, 0, 0, 1, 0, 0, 0, 0, 0, 0))

    def read_swaps(self):
        return self.swaps

    def run(self, argv, input_data=None):
        self.calls.append(list(map(str, argv)))
        a = list(map(str, argv))
        if a[0] == 'lsblk':
            return json.dumps({'blockdevices': self.devices}).encode()
        if a[0] == 'findmnt':
            return json.dumps({'filesystems': self.mounts}).encode()
        if a[0] == 'blkid':
            return (U if '-s' in a else '/dev/fixture').encode()
        if a[:3] == ['btrfs', 'subvolume', 'show']:
            m = self.info(a[-1])
            return (f'UUID: {m["uuid"]}\nParent UUID: {m["parent_uuid"] or "-"}\n'
                    f'Received UUID: {m["received_uuid"] or "-"}\nSubvolume ID: {m["subvolume_id"]}\n').encode()
        if a[:3] == ['btrfs', 'property', 'get']:
            return ('ro=' + ('true' if self.info(a[-2])['readonly'] else 'false')).encode()
        if a[:3] == ['btrfs', 'subvolume', 'snapshot']:
            source, destination = map(Path, a[-2:])
            shutil.copytree(source, destination, symlinks=True)
            m = self.info(source)
            m.update(parent_uuid=m['uuid'], uuid=str(uuid.uuid4()),
                     readonly='-r' in a, received_uuid=None,
                     subvolume_id=1000 + len(self.calls))
            (destination / '.meta').write_text(json.dumps(m))
            return b''
        if a[:3] == ['btrfs', 'subvolume', 'get-default']:
            return f'ID {self.default} gen 1 top level 5 path @'.encode()
        if a[:3] == ['btrfs', 'subvolume', 'set-default']:
            self.default = int(a[3]); return b''
        if a[:3] == ['btrfs', 'filesystem', 'sync']:
            return b''
        raise AssertionError('unexpected kernel command: ' + repr(a))


def received(top):
    return {'system': str(Path(top) / 'received/system/ts-system'),
            'home': str(Path(top) / 'received/home/ts-home')}
