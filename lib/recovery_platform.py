"""Linux kernel boundary and durable files for offline recovery."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from recovery_catalog import UUID


def safe_path(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('unsafe recovery path')
    for entry in (path, *path.parents):
        if entry.is_symlink():
            raise ValueError('symlink recovery path: ' + str(entry))
    return path


def tree_path(root, relative):
    """Resolve snapshot symlinks with the snapshot as /, never the Live root."""
    root = safe_path(root)
    pending = str(relative).lstrip('/').split('/')
    parts = []; links = 0
    while pending:
        part = pending.pop(0)
        if part in ('', '.'):
            continue
        if part == '..':
            if not parts:
                raise ValueError('snapshot symlink escapes root')
            parts.pop(); continue
        candidate = root.joinpath(*parts, part)
        if candidate.is_symlink():
            links += 1
            if links > 40:
                raise ValueError('snapshot symlink loop')
            target = os.readlink(candidate)
            if target.startswith('/'):
                parts = []
            pending = target.split('/') + pending
        else:
            parts.append(part)
    return root.joinpath(*parts)


def flatten(entries):
    if not isinstance(entries, list):
        raise ValueError('invalid device/mount inventory')
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('invalid device/mount entry')
        yield entry
        if entry.get('children'):
            yield from flatten(entry['children'])


class RecoveryPlatform:
    def run(self, argv, input_data=None):
        result = subprocess.run(list(map(str, argv)), input=input_data,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            raise ValueError(f'{argv[0]} failed ({result.returncode}): ' +
                             result.stderr.decode(errors='replace')[:2000])
        return result.stdout

    def stat_device(self, device):
        return os.stat(device)

    def read_swaps(self):
        return Path('/proc/swaps').read_text()

    def discover_targets(self):
        data = json.loads(self.run(['lsblk', '--json', '--bytes', '--output',
                                   'PATH,FSTYPE,UUID,MODEL,SIZE,MOUNTPOINTS']))
        targets = []
        for item in flatten(data['blockdevices']):
            if item.get('fstype') != 'btrfs':
                continue
            if (not isinstance(item.get('uuid'), str) or not UUID.fullmatch(item['uuid']) or
                    not isinstance(item.get('path'), str) or not item['path'].startswith('/dev/') or
                    type(item.get('size')) is not int or item['size'] <= 0):
                raise ValueError('invalid Btrfs device inventory')
            targets.append({'device': item['path'], 'uuid': item['uuid'],
                            'model': item.get('model') or '(model unavailable)',
                            'size_bytes': item['size'], 'available_bytes': None,
                            'current_mounts': [], 'active_swap': [], 'subvolumes': []})
        return targets

    def verify_target(self, device, expected_uuid, allowed_mount=None):
        if not UUID.fullmatch(expected_uuid):
            raise ValueError('invalid target filesystem UUID')
        matching = [t for t in self.discover_targets() if t['uuid'] == expected_uuid]
        if len(matching) != 1:
            raise ValueError('missing or ambiguous target filesystem')
        target = matching[0]
        if device != target['device'] or not stat.S_ISBLK(self.stat_device(device).st_mode):
            raise ValueError('target is not the selected block device')
        actual = self.run(['blkid', '-s', 'UUID', '-o', 'value', device]).decode().strip()
        if actual != expected_uuid:
            raise ValueError('target filesystem UUID changed')
        data = json.loads(self.run(['findmnt', '--json', '--output', 'SOURCE,TARGET,FSTYPE,UUID']))
        mounts = list(flatten(data.get('filesystems', [])))
        for item in mounts:
            source = str(item.get('source', '')).split('[')[0]
            same = item.get('uuid') == expected_uuid or source == device
            if same and item.get('target') != str(allowed_mount):
                raise ValueError('target filesystem is already mounted: ' + str(item.get('target')))
        for line in self.read_swaps().splitlines()[1:]:
            fields = line.split()
            if not fields:
                continue
            name = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[0])
            if name == device or os.path.realpath(name) == os.path.realpath(device):
                raise ValueError('active swap on target')
            if not name.startswith('/dev/'):
                for item in mounts:
                    mount = item.get('target')
                    if (item.get('uuid') == expected_uuid and isinstance(mount, str) and
                            (name == mount or name.startswith(mount.rstrip('/') + '/'))):
                        raise ValueError('active swap file on target')
        return target

    @contextmanager
    def open_target(self, device, expected_uuid):
        self.verify_target(device, expected_uuid)
        lock_path = Path('/run') / ('ws-recovery-' + expected_uuid + '.lock')
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        mounted = False; top = None
        try:
            if os.fstat(fd).st_uid != os.geteuid():
                raise ValueError('recovery lock has wrong owner')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            top = Path(tempfile.mkdtemp(prefix='ws-recovery-', dir='/run'))
            self.run(['mount', '-o', 'subvolid=5', device, top]); mounted = True
            target = self.verify_target(device, expected_uuid, top)
            usage = os.statvfs(top)
            target['available_bytes'] = usage.f_bavail * usage.f_frsize
            self.target_device = device; self.target_uuid = expected_uuid; self.target_top = top
            yield top, target
        finally:
            try:
                if mounted:
                    self.run(['umount', top])
                if top is not None:
                    top.rmdir()
            finally:
                os.close(fd)
                for attribute in ('target_device', 'target_uuid', 'target_top'):
                    if hasattr(self, attribute): delattr(self, attribute)

    def assert_offline(self, top):
        if hasattr(self, 'target_device'):
            self.verify_target(self.target_device, self.target_uuid, top)

    def inspect_snapshot(self, path):
        path = safe_path(path)
        if not path.is_dir():
            raise ValueError('snapshot missing: ' + str(path))
        text = self.run(['btrfs', 'subvolume', 'show', path]).decode()
        fields = {}
        for line in text.splitlines():
            if ':' in line:
                key, value = line.strip().split(':', 1)
                fields[key] = value.strip()
        readonly = self.run(['btrfs', 'property', 'get', '-ts', path, 'ro']).strip()
        if readonly not in (b'ro=true', b'ro=false'):
            raise ValueError('invalid readonly property')
        result = {'uuid': fields.get('UUID'), 'parent_uuid': fields.get('Parent UUID'),
                  'received_uuid': fields.get('Received UUID'),
                  'subvolume_id': int(fields.get('Subvolume ID', '0')),
                  'readonly': readonly == b'ro=true'}
        for key in ('parent_uuid', 'received_uuid'):
            if result[key] == '-': result[key] = None
            if result[key] is not None and (not isinstance(result[key], str) or not UUID.fullmatch(result[key])):
                raise ValueError('invalid snapshot UUID')
        if not isinstance(result['uuid'], str) or not UUID.fullmatch(result['uuid']) or result['subvolume_id'] <= 0:
            raise ValueError('invalid Btrfs snapshot identity')
        return result

    def sync_filesystem(self, top):
        self.run(['btrfs', 'filesystem', 'sync', top])

    def rename(self, source, destination):
        source = safe_path(source); destination = safe_path(destination)
        if source.parent != destination.parent or destination.exists():
            raise ValueError('unsafe or occupied recovery rename destination')
        source.rename(destination)

    def save_json(self, path, value):
        path = safe_path(path)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        safe_path(path)
        if path.parent.stat().st_uid != os.geteuid() or path.parent.stat().st_mode & 0o022:
            raise ValueError('unsafe recovery journal directory')
        fd, name = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
        try:
            with os.fdopen(fd, 'w') as output:
                json.dump(value, output, sort_keys=True, indent=2)
                output.flush(); os.fsync(output.fileno())
            os.replace(name, path)
            for parent in (path.parent, *path.parent.parents):
                directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory)
                finally: os.close(directory)
        finally:
            if os.path.exists(name): os.unlink(name)
