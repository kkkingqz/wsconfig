"""Offline root/HOME recovery, with explicit identity and boot preflight."""
import json
import os
from pathlib import Path
import re
import shlex
import uuid

from recovery_catalog import validate_selection
from recovery_platform import safe_path, tree_path


def build_plan(selection, target, include_home):
    selection = validate_selection(selection)
    if include_home and selection['home'] is None:
        raise ValueError('selected snapshot does not contain HOME')
    if target['uuid'] != selection['source_fs_uuid']:
        raise ValueError('source and target filesystem UUID differ')
    if not include_home:
        selection['home'] = None
    return {'selection': selection, 'target': target,
            'preserved': ['@nix', '@vms', '@cache', '@tmp', '@log', '@swap', 'EFI'],
            'warning': 'Nix generations removed by GC may need rebuilding; no automatic reboot'}


def boot_preflight(top, root, fs_uuid):
    fstab_path = tree_path(root, 'etc/fstab')
    boot_path = tree_path(root, 'boot/refind_linux.conf')
    if not fstab_path.is_file() or not boot_path.is_file():
        raise ValueError('fstab/rEFInd configuration missing')
    lines = []; mountpoints = []; has_root = False
    for line in fstab_path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            lines.append(line); continue
        fields = line.split()
        if len(fields) != 6:
            raise ValueError('unsupported fstab format')
        source, destination, kind, options = fields[:4]
        if kind == 'btrfs':
            if source != 'UUID=' + fs_uuid:
                raise ValueError('fstab filesystem UUID mismatch')
            flags = options.split(',')
            names = [o.split('=', 1)[1] for o in flags if o.startswith('subvol=')]
            ids = [o for o in flags if o.startswith('subvolid=')]
            expected = {'/': '@', '/home': '@home'}.get(destination)
            if ids:
                if not expected or names or len(ids) != 1 or not ids[0][9:].isdigit():
                    raise ValueError('unsupported numeric fstab subvolume')
                flags = [('subvol=' + expected) if o.startswith('subvolid=') else o for o in flags]
                names = [expected]
            if len(names) != 1 or not re.fullmatch(r'/?@[A-Za-z0-9_-]*', names[0]):
                raise ValueError('unsupported fstab subvolume')
            name = names[0].lstrip('/')
            if expected and name != expected:
                raise ValueError('unexpected root/HOME subvolume')
            if not safe_path(top / name).is_dir():
                raise ValueError('fstab subvolume missing: ' + name)
            if destination == '/': has_root = True
            if not destination.startswith('/') or '..' in Path(destination).parts:
                raise ValueError('unsafe fstab mountpoint')
            mountpoints.append(destination)
            fields[3] = ','.join(flags)
            line = '\t'.join(fields)
        elif kind not in ('vfat', 'none', 'swap'):
            raise ValueError('unsupported fstab filesystem')
        lines.append(line)
    if not has_root:
        raise ValueError('fstab root mount missing')
    boot_lines = []; entries = 0
    for line in boot_path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            boot_lines.append(line); continue
        fields = shlex.split(line)
        if len(fields) not in (2, 3):
            raise ValueError('unsupported rEFInd Linux configuration')
        args = shlex.split(fields[1])
        if args.count('root=UUID=' + fs_uuid) != 1:
            raise ValueError('rEFInd root UUID mismatch')
        rootflags = [a for a in args if a.startswith('rootflags=')]
        if len(rootflags) != 1:
            raise ValueError('rEFInd rootflags missing')
        flags = rootflags[0].split('=', 1)[1].split(',')
        subvolumes = [f for f in flags if f.startswith(('subvol=', 'subvolid='))]
        if len(subvolumes) != 1 or not re.fullmatch(r'(subvol=/?@|subvolid=[0-9]+)', subvolumes[0]):
            raise ValueError('unsupported rEFInd root subvolume')
        flags = ['subvol=@' if f in subvolumes else f for f in flags]
        args = ['rootflags=' + ','.join(flags) if a == rootflags[0] else a for a in args]
        args = [a for a in args if not a.startswith(('resume=', 'resume_offset=')) and a != 'noresume'] + ['noresume']
        fields[1] = ' '.join(args)
        boot_lines.append(' '.join('"' + f.replace('\\', '\\\\').replace('"', '\\"') + '"' for f in fields))
        entries += 1
    if not entries:
        raise ValueError('rEFInd boot entries missing')
    kernel = tree_path(root, 'boot/vmlinuz')
    if not kernel.is_file() or not kernel.name.startswith('vmlinuz-'):
        raise ValueError('kernel missing or unsupported')
    version = kernel.name[len('vmlinuz-'):]
    initrd = tree_path(root, 'boot/initrd.img')
    if not initrd.is_file() or initrd.name != 'initrd.img-' + version:
        raise ValueError('matching initrd missing')
    if not tree_path(root, 'lib/modules/' + version).is_dir():
        raise ValueError('kernel modules missing')
    return {'fstab': '\n'.join(lines) + '\n', 'refind': '\n'.join(boot_lines) + '\n',
            'mountpoints': mountpoints, 'kernel': version}


def preflight(top, selection, received, platform):
    top = safe_path(top); selection = validate_selection(selection)
    platform.assert_offline(top)
    old = {}; copies = {}
    for scope, name in [('system', '@'), ('home', '@home')]:
        if scope == 'home' and selection['home'] is None:
            old['home'] = None; continue
        old[scope] = platform.inspect_snapshot(top / name)
        if old[scope]['readonly']:
            raise ValueError('current root/HOME must be writable')
        path = safe_path(received[scope])
        if top not in path.parents:
            raise ValueError('received snapshot outside target')
        copy = platform.inspect_snapshot(path)
        if not copy['readonly'] or copy['received_uuid'] != selection[scope]['source_uuid']:
            raise ValueError('received snapshot identity/readonly mismatch')
        copies[scope] = {'path': str(path.relative_to(top)), **copy}
    boot = boot_preflight(top, top / copies['system']['path'], selection['source_fs_uuid'])
    default = platform.run(['btrfs', 'subvolume', 'get-default', top]).decode().split()
    if len(default) < 2 or default[0] != 'ID' or not default[1].isdigit():
        raise ValueError('invalid original default subvolume')
    return {'schema_version': 1, 'id': 'restore-' + uuid.uuid4().hex,
            'selection': selection, 'old': old, 'received': copies,
            'boot': boot, 'original_default': int(default[1]), 'phase': 'received'}


def prepare_candidates(top, checked, platform):
    top = safe_path(top); platform.assert_offline(top)
    prepared = json.loads(json.dumps(checked)); candidates = {}
    for scope, copy in checked['received'].items():
        name = ('@restore-' if scope == 'system' else '@home-restore-') + checked['id']
        path = safe_path(top / name)
        if path.exists():
            raise ValueError('candidate path already exists')
        source = safe_path(top / copy['path'])
        actual = platform.inspect_snapshot(source)
        if actual['uuid'] != copy['uuid'] or not actual['readonly']:
            raise ValueError('received baseline changed')
        platform.run(['btrfs', 'subvolume', 'snapshot', source, path])
        candidate = platform.inspect_snapshot(path)
        if candidate['readonly'] or candidate['parent_uuid'] != actual['uuid']:
            raise ValueError('candidate identity mismatch')
        candidates[scope] = {'path': name, **candidate}
    root = top / candidates['system']['path']
    for relative, text in [('etc/fstab', checked['boot']['fstab']),
                           ('boot/refind_linux.conf', checked['boot']['refind'])]:
        path = tree_path(root, relative)
        backup = path.with_name(path.name + '.before-ws-recovery')
        if backup.exists() or backup.is_symlink():
            raise ValueError('boot backup path already exists')
        backup.write_bytes(path.read_bytes())
        path.write_text(text)
    for mountpoint in checked['boot']['mountpoints']:
        tree_path(root, mountpoint).mkdir(parents=True, exist_ok=True)
    platform.sync_filesystem(top)
    prepared.update(candidates=candidates, phase='prepared')
    return prepared
