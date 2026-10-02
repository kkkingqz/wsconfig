"""External Btrfs/libvirt boundary only; files and process exits remain real."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

U = '11111111-1111-1111-1111-111111111111'

PROGRAM = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
a = sys.argv[1:]
c = json.loads(pathlib.Path(os.environ['BACKUP_FIXTURE']).read_text())
if name == 'findmnt':
    field = a[a.index('-nro') + 1] if '-nro' in a else 'TARGET'
    print({'FSTYPE': c.get('fstype', 'btrfs'), 'UUID': c.get('uuid'),
           'OPTIONS': 'rw,subvol=/@home' if a[-1] == '/home' else 'rw,subvol=/@vms',
           'TARGET': a[-1]}[field])
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
        print('UUID: ' + m['uuid'] + '\nReceived UUID: ' + m.get('received_uuid', '-'))
    elif a[:2] == ['property', 'get']:
        p = pathlib.Path(a[-2])
        m = json.loads((p / '.fixture-meta').read_text())
        print('ro=' + ('true' if m.get('ro', True) else 'false'))
    elif op == ['subvolume', 'snapshot']:
        p.mkdir()
        (p / '.fixture-meta').write_text(json.dumps({'uuid': c['uuid'], 'received_uuid': '-', 'ro': True}))
        (p / 'payload').write_text('preserved data')
    elif op == ['subvolume', 'create']:
        p.mkdir()
    elif a[0] == 'send':
        if c.get('send_error'): sys.exit(1)
        m = json.loads((p / '.fixture-meta').read_text())
        # Linux send_subvol_begin preserves received_uuid when re-sending.
        stream_uuid = m.get('received_uuid')
        if not stream_uuid or stream_uuid == '-': stream_uuid = m['uuid']
        print(json.dumps({'name': p.name, 'uuid': stream_uuid, 'payload': (p / 'payload').read_text()}))
    elif a[0] == 'receive':
        if c.get('receive_error'): sys.exit(1)
        m = json.load(sys.stdin)
        dest = p / m['name']; dest.mkdir()
        (dest / '.fixture-meta').write_text(json.dumps({'uuid': '22222222-2222-2222-2222-222222222222', 'received_uuid': m['uuid'], 'ro': True}))
        (dest / 'payload').write_text(m['payload'])
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
        for name in ('btrfs', 'findmnt', 'virsh'):
            f = self.bin / name
            f.write_text(PROGRAM)
            f.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        BACKUP_FIXTURE=str(self.config))

    def update(self, **changes):
        self.config.write_text(json.dumps({'uuid': U, **changes}))

    def close(self):
        self.temp.cleanup()
