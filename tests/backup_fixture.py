"""External Btrfs/libvirt boundary only; files and process exits remain real."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

U = '11111111-1111-1111-1111-111111111111'

PROGRAM = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, uuid, shutil
name = pathlib.Path(sys.argv[0]).name
a = sys.argv[1:]
c = json.loads(pathlib.Path(os.environ['BACKUP_FIXTURE']).read_text())
if name == 'findmnt':
    field = a[a.index('-nro') + 1] if '-nro' in a else 'TARGET'
    print({'FSTYPE': c.get('fstype', 'btrfs'), 'UUID': c.get('uuid'),
           'OPTIONS': 'rw,subvol=/@home' if a[-1] == '/home' else 'rw,subvol=/@vms',
           'TARGET': a[-1], 'FSROOT': '/'}[field])
elif name == 'blkid':
    print('/dev/fixture')
elif name == 'mount':
    if c.get('remove_source_on_mount'):
        counter = pathlib.Path(os.environ['BACKUP_FIXTURE']).with_suffix('.mount-count')
        count = int(counter.read_text()) + 1 if counter.exists() else 1
        counter.write_text(str(count))
        if count == c['remove_source_on_mount']: shutil.rmtree(c['remove_source'])
    shutil.copytree(c['timeshift_top'], a[-1], dirs_exist_ok=True)
elif name == 'umount':
    for entry in pathlib.Path(a[-1]).iterdir():
        if entry.is_dir(): shutil.rmtree(entry)
        else: entry.unlink()
elif name == 'virsh':
    if c.get('virsh_error'): sys.exit(1)
    print(c.get('active_vm', ''), end='')
elif name == 'btrfs':
    if a == ['--version']:
        print('btrfs-progs v6.17'); sys.exit(0)
    if a[0] == 'receive' and c.get('receive_delay'):
        import time; time.sleep(c['receive_delay'])
    op = a[:2]
    p = pathlib.Path(a[-1])
    if op == ['subvolume', 'list']:
        print(c.get('nested', ''), end='')
    elif op == ['subvolume', 'show']:
        m = json.loads((p / '.fixture-meta').read_text()) if (p / '.fixture-meta').exists() else {'uuid': c['uuid'], 'received_uuid': '-'}
        print('UUID: ' + m['uuid'] + '\nReceived UUID: ' + m.get('received_uuid', '-') + '\nParent UUID: ' + m.get('parent_uuid', '-'))
    elif a[:2] == ['property', 'get']:
        p = pathlib.Path(a[-2])
        m = json.loads((p / '.fixture-meta').read_text())
        print('ro=' + ('true' if m.get('ro', True) else 'false'))
    elif op == ['subvolume', 'snapshot']:
        p.mkdir()
        src = pathlib.Path(a[-2])
        parent_uuid = json.loads((src / '.fixture-meta').read_text())['uuid'] if (src / '.fixture-meta').exists() else '-'
        (p / '.fixture-meta').write_text(json.dumps({'uuid': str(uuid.uuid4()), 'received_uuid': '-', 'ro': True, 'parent_uuid': parent_uuid}))
        payload = (src / 'payload').read_text() if (src / 'payload').exists() else c.get('payload', 'preserved data')
        (p / 'payload').write_text(payload)
    elif op == ['subvolume', 'create']:
        p.mkdir()
    elif op == ['subvolume', 'delete']:
        counter = pathlib.Path(os.environ['BACKUP_FIXTURE']).with_suffix('.delete-count')
        count = int(counter.read_text()) + 1 if counter.exists() else 1
        counter.write_text(str(count))
        if count == c.get('delete_fail_at'): sys.exit(1)
        shutil.rmtree(p)
    elif op == ['filesystem', 'sync']:
        pass
    elif a[0] == 'send':
        if c.get('add_snapshot'):
            dest = pathlib.Path(c['timeshift_top']) / 'timeshift-btrfs/snapshots/2026-10-02_12-00-00'
            if not dest.exists(): shutil.copytree(c['add_snapshot'], dest)
        if c.get('send_fail_at'):
            counter = pathlib.Path(os.environ['BACKUP_FIXTURE']).with_suffix('.send-count')
            count = int(counter.read_text()) + 1 if counter.exists() else 1
            counter.write_text(str(count))
            if count == c['send_fail_at']: sys.exit(1)
        if c.get('pending_record_path'):
            record = json.loads(pathlib.Path(c['pending_record_path']).read_text())
            if record['status'] != 'pending': sys.exit(1)
        if c.get('send_error'): sys.exit(1)
        m = json.loads((p / '.fixture-meta').read_text())
        # Linux send_subvol_begin preserves received_uuid when re-sending.
        stream_uuid = m.get('received_uuid')
        if not stream_uuid or stream_uuid == '-': stream_uuid = m['uuid']
        packet = {'name': p.name, 'uuid': stream_uuid}
        if '-p' in a:
            parent = pathlib.Path(a[a.index('-p') + 1])
            pm = json.loads((parent / '.fixture-meta').read_text())
            if not pm['ro']: sys.exit(1)
            packet['parent_uuid'] = pm['uuid']
            packet['changes'] = {}
            if (p / 'payload').read_text() != (parent / 'payload').read_text():
                packet['changes']['payload'] = (p / 'payload').read_text()
        else:
            if c.get('require_incremental'): sys.exit(1)
            packet['payload'] = (p / 'payload').read_text()
        print(json.dumps(packet))
    elif a[0] == 'receive':
        if c.get('receive_error'): sys.exit(1)
        m = json.load(sys.stdin)
        parent_uuid = m.get('parent_uuid')
        payload = m.get('payload')
        if parent_uuid:
            # Resolve the previously received readonly parent, then apply the
            # synthetic delta. A wrong/missing parent makes receive fail.
            matches = []
            for meta in p.parent.glob('*/.fixture-meta'):
                pm = json.loads(meta.read_text())
                if pm.get('received_uuid') == parent_uuid and pm.get('ro'):
                    matches.append(meta.parent)
            if len(matches) != 1: sys.exit(1)
            payload = (matches[0] / 'payload').read_text()
            payload = m['changes'].get('payload', payload)
        dest = p / m['name']; dest.mkdir()
        (dest / '.fixture-meta').write_text(json.dumps({'uuid': str(uuid.uuid4()), 'received_uuid': m['uuid'], 'ro': True, 'stream_parent': parent_uuid}))
        (dest / 'payload').write_text(payload)
    else:
        print('unexpected btrfs args: ' + repr(a), file=sys.stderr); sys.exit(1)
else:
    print('unexpected fixture command', file=sys.stderr); sys.exit(1)
'''


class Boundary:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.config = self.root / 'fixture.json'
        self.update()
        for name in ('btrfs', 'findmnt', 'virsh', 'blkid', 'mount', 'umount'):
            f = self.bin / name
            f.write_text(PROGRAM)
            f.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        BACKUP_FIXTURE=str(self.config))

    def update(self, **changes):
        self.config.write_text(json.dumps({'uuid': U, **changes}))

    def close(self):
        self.temp.cleanup()
