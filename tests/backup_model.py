"""In-process model of the backup helpers for the orchestration tests.

The batch, retention, recovery and restore tests check lib/backup.py and
lib/backup_timeshift.py: which helper is asked for what, in which order, and
what survives a failure. Through the real bash helpers that cost ~1700
processes per test, seconds each. HelperModel replaces the two process entry
points of lib/backup.py (run_result, stream) and answers the same argv on the
same file layout as backup_fixture (.fixture-meta, payload, counter files),
with the same fault switches (send_fail_at, delete_fail_at, add_snapshot,
remove_source_on_mount, pending_record_path, send_error, receive_error,
require_incremental).

The helpers themselves are tested on their own (TimeshiftBoundary,
test_backup_receiver, test_backup_source, test_backup_catalog, the helper
calls in RetentionTests), and RealHelpersContract runs a batch through the
real helpers and receiver: a change of their protocol must show up there and
then here.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import signal
from types import SimpleNamespace
import uuid
from unittest import mock


def run_main(env, args):
    """wsbackup ARGS in this process (so it talks to the model), with its
    exit code and messages as bin/wsbackup would give them."""
    import backup
    out, err, code = io.StringIO(), io.StringIO(), 0
    handler = signal.getsignal(signal.SIGTERM)
    try:
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            backup.main(list(args))
    except (ValueError, OSError) as e:
        err.write(f'wsbackup: {e}\n')
        code = 1
    finally:
        signal.signal(signal.SIGTERM, handler)
    return subprocess.CompletedProcess(args, code, out.getvalue(), err.getvalue())


class Die(Exception):
    """A helper's die(): exit 1 with 'wsbackup: MESSAGE' (exit 3: missing)."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def catalog_json(v):
    return ('{"schema_version":1,"host_id":"%s","source_fs_uuid":"%s","scope":"%s","id":"%s",'
            '"source_uuid":"%s","origin_uuid":"%s","timeshift_name":"%s","timestamp":%s}' % tuple(v))


class HelperModel:
    def __init__(self, boundary, receiver_conf):
        self.b = boundary
        conf = dict(line.split('=', 1) for line in Path(receiver_conf).read_text().split())
        self.receiver_root = Path(conf['ROOT'])
        self.receiver_uuid = conf['FS_UUID']
        self.host_id = conf['HOST_ID']
        self.calls = []
        # The next successful receive is reported as a dropped SSH
        # connection (exit 255): the snapshot is published, the sender
        # does not know it.
        self.disconnect_after_receive = False

    def install(self, test):
        import backup
        for name, fn in (('run_result', self.run_result), ('stream', self.stream)):
            p = mock.patch.object(backup, name, fn)
            p.start()
            test.addCleanup(p.stop)

    # -- lib/backup.py entry points -------------------------------------

    def run_result(self, args):
        try:
            out = self.dispatch(list(args))
        except Die as e:
            return subprocess.CompletedProcess(args, e.code, '', f'wsbackup: {e}\n')
        return subprocess.CompletedProcess(args, 0, out, '')

    def stream(self, sender, receiver):
        try:
            packet = self.dispatch(list(sender))
        except Die as e:
            raise ValueError(f'stream failed (send={e.code}, receive=1): wsbackup: {e}') from None
        try:
            out = self.dispatch(list(receiver), packet)
        except Die as e:
            raise ValueError(f'stream failed (send=0, receive={e.code}): wsbackup: {e}') from None
        if self.disconnect_after_receive and receiver[0] == 'ssh':
            self.disconnect_after_receive = False
            raise ValueError('stream failed (send=0, receive=255): connection closed')
        return out

    def dispatch(self, args, packet=None):
        self.calls.append(args)
        if args[0] == 'ssh':
            return self.receiver(shlex.split(args[-1]), packet)
        assert args[:2] == ['sudo', '/bin/bash'], args
        script, rest = Path(args[2]).name, args[3:]
        if script == 'wsbackup-restore':
            assert rest[0] == '--uuid' and rest[2] == '--target', args
            self.filesystem_check(rest[1])
            return self.restore(Path(rest[3]), *rest[4:7], packet)
        assert rest[0] == '--uuid' and rest[2] == '--root', args
        self.filesystem_check(rest[1])
        root, action, a = Path(rest[3]), rest[4], rest[5:]
        if script == 'wsbackup-timeshift':
            return self.timeshift(root, action, a)
        if script == 'wsbackup-source':
            return self.source(root, action, a)
        raise AssertionError(args)

    # -- the fake Btrfs of backup_fixture -------------------------------

    def config(self):
        return json.loads(self.b.config.read_text())

    def count(self, name):
        path = self.b.config.with_suffix(f'.{name}-count')
        n = int(path.read_text()) + 1 if path.exists() else 1
        path.write_text(str(n))
        return n

    def filesystem_check(self, expected):
        if self.config().get('uuid') != expected:
            raise Die('wrong filesystem UUID')

    def show_uuid(self, path):
        meta = Path(path) / '.fixture-meta'
        return json.loads(meta.read_text())['uuid'] if meta.exists() else self.config()['uuid']

    def inspect(self, path):
        """inspect_snapshot + snapshot_json of btrfs-common.bash."""
        meta = Path(path) / '.fixture-meta'
        if not meta.exists():
            raise Die('snapshot is not read-only')
        m = json.loads(meta.read_text())
        if not m.get('ro', True):
            raise Die('snapshot is not read-only')
        received, parent = m.get('received_uuid', '-'), m.get('parent_uuid', '-')
        return {'uuid': m['uuid'], 'received_uuid': '' if received == '-' else received,
                'parent_uuid': '' if parent == '-' else parent, 'ro': True}

    def snapshot(self, src, dest):
        src, dest = Path(src), Path(dest)
        dest.mkdir()
        meta = src / '.fixture-meta'
        parent = json.loads(meta.read_text())['uuid'] if meta.exists() else '-'
        (dest / '.fixture-meta').write_text(json.dumps(
            {'uuid': str(uuid.uuid4()), 'received_uuid': '-', 'ro': True, 'parent_uuid': parent}))
        payload = (src / 'payload').read_text() if (src / 'payload').exists() \
            else self.config().get('payload', 'preserved data')
        (dest / 'payload').write_text(payload)
        return json.dumps(self.inspect(dest)) + '\n'

    def send(self, path, parent=None):
        """btrfs send: the packet backup_fixture streams."""
        c = self.config()
        self.inspect(path)
        if parent is not None:
            self.inspect(parent)
        if c.get('add_snapshot'):
            dest = Path(c['timeshift_top']) / 'timeshift-btrfs/snapshots/2026-10-02_12-00-00'
            if not dest.exists():
                shutil.copytree(c['add_snapshot'], dest)
        if c.get('send_fail_at') and self.count('send') == c['send_fail_at']:
            raise Die('btrfs send failed')
        if c.get('pending_record_path'):
            if json.loads(Path(c['pending_record_path']).read_text())['status'] != 'pending':
                raise Die('record not pending before stream')
        if c.get('send_error'):
            raise Die('btrfs send failed')
        m = json.loads((path / '.fixture-meta').read_text())
        stream_uuid = m.get('received_uuid')
        if not stream_uuid or stream_uuid == '-':
            stream_uuid = m['uuid']
        packet = {'name': path.name, 'uuid': stream_uuid}
        if parent is not None:
            pm = json.loads((parent / '.fixture-meta').read_text())
            packet.update(parent_uuid=pm['uuid'], changes={})
            if (path / 'payload').read_text() != (parent / 'payload').read_text():
                packet['changes']['payload'] = (path / 'payload').read_text()
        else:
            if c.get('require_incremental'):
                raise Die('full send refused')
            packet['payload'] = (path / 'payload').read_text()
        return packet

    def receive(self, into, m):
        """btrfs receive INTO from packet M, as backup_fixture."""
        if self.config().get('receive_error'):
            raise Die('btrfs receive failed')
        assert isinstance(m, dict), 'receive needs a stream'
        payload = m.get('payload')
        parent_uuid = m.get('parent_uuid')
        if parent_uuid:
            matches = []
            for meta in into.parent.glob('*/.fixture-meta'):
                pm = json.loads(meta.read_text())
                if pm.get('received_uuid') == parent_uuid and pm.get('ro'):
                    matches.append(meta.parent)
            if len(matches) != 1:
                raise Die('btrfs receive: parent not found')
            payload = m['changes'].get('payload', (matches[0] / 'payload').read_text())
        dest = into / m['name']
        dest.mkdir()
        (dest / '.fixture-meta').write_text(json.dumps(
            {'uuid': str(uuid.uuid4()), 'received_uuid': m['uuid'], 'ro': True, 'stream_parent': parent_uuid}))
        (dest / 'payload').write_text(payload)

    def hash(self, snapshot, rel):
        self.inspect(snapshot)
        f = snapshot / rel
        if not f.is_file():
            raise Die('verification file missing')
        return f'{hashlib.sha256(f.read_bytes()).hexdigest()}  {f}\n'

    # -- backup/wsbackup-timeshift --------------------------------------

    def mount(self):
        c = self.config()
        if c.get('remove_source_on_mount') and self.count('mount') == c['remove_source_on_mount']:
            shutil.rmtree(c['remove_source'])
        return Path(c['timeshift_top']) / 'timeshift-btrfs/snapshots'

    def inventory(self, store):
        import timeshift_inventory as ti

        def run(args, **kwargs):
            out = str(self.config().get('uuid')) if args[0] == 'findmnt' else 'UUID: ' + self.show_uuid(args[-1])
            return subprocess.CompletedProcess(args, 0, out + '\n', '')

        with mock.patch.object(ti, 'subprocess', SimpleNamespace(
                run=run, CalledProcessError=subprocess.CalledProcessError)):
            return ti.read_inventory(store)

    def timeshift(self, root, action, a):
        if action == 'list':
            return json.dumps([{'scope': s, 'id': p.name} for s in ('system', 'home')
                               for p in sorted((root / s).glob('*'))]) + '\n'
        if action == 'delete':
            scope, id, expected, retained, retained_uuid = a
            if id == retained:
                raise Die('cannot delete retained copy')
            if self.inspect(root / scope / retained)['uuid'] != retained_uuid:
                raise Die('retained UUID mismatch')
            dest = root / scope / id
            if not dest.exists():
                return '{"deleted":false}\n'
            if self.inspect(dest)['uuid'] != expected:
                raise Die('copy UUID mismatch')
            if self.count('delete') == self.config().get('delete_fail_at'):
                raise Die('btrfs subvolume delete failed')
            shutil.rmtree(dest)
            return '{"deleted":true}\n'
        if action == 'clone':
            scope, id, old, expected = a
            if self.inspect(root / scope / old)['uuid'] != expected:
                raise Die('clone source UUID mismatch')
            if (root / scope / id).exists():
                raise Die('copy already exists')
            return self.snapshot(root / scope / old, root / scope / id)
        store = self.mount()
        if action == 'inventory':
            return json.dumps(self.inventory(store)) + '\n'
        assert action == 'import', action
        scope, id, name, expected = a
        rows = [r for r in self.inventory(store)['snapshots']
                if r['scope'] == scope and r['timeshift_name'] == name]
        if len(rows) != 1 or rows[0]['origin_uuid'] != expected:
            raise Die('Timeshift source missing or origin UUID changed')
        if (root / scope / id).exists():
            raise Die('copy already exists')
        (root / scope).mkdir(mode=0o700, parents=True, exist_ok=True)
        return self.snapshot(store / name / ('@' if scope == 'system' else '@home'), root / scope / id)

    # -- backup/wsbackup-source -----------------------------------------

    def source(self, root, action, a):
        if action == 'list':
            copies = []
            for scope in ('system', 'home', 'vms'):
                for p in sorted((root / scope).glob('*')):
                    m = json.loads((p / '.fixture-meta').read_text())
                    copies.append({'scope': scope, 'id': p.name, 'uuid': m['uuid'],
                                   'ro': bool(m.get('ro', True)), 'created': ''})
            return json.dumps(copies) + '\n'
        scope, id, extra = a[0], a[1], a[2:]
        dest = root / scope / id
        if action == 'inspect':
            if not dest.exists():
                raise Die('snapshot missing', 3)
            return json.dumps(self.inspect(dest)) + '\n'
        if action == 'hash':
            return self.hash(dest, extra[0])
        if action == 'send':
            return self.send(dest, root / scope / extra[0] if extra else None)
        assert action == 'snapshot' and scope != 'system', a
        c = self.config()
        if c.get('nested'):
            raise Die('nested subvolumes require an explicit backup decision')
        if scope == 'vms' and (c.get('virsh_error') or c.get('active_vm', '').strip()):
            raise Die('running VMs; shut them down before backup')
        (root / scope).mkdir(parents=True, exist_ok=True)
        if dest.exists():
            raise Die('snapshot already exists')
        return self.snapshot(self.b.home if scope == 'home' else self.b.vms, dest)

    # -- backup/unraid/wsbackup-receiver --------------------------------

    def receiver(self, words, packet):
        action, host = words[0], words[1]
        if host != self.host_id:
            raise Die('host not permitted')
        root = self.receiver_root
        self.filesystem_check(self.receiver_uuid)
        if action == 'probe':
            return json.dumps({'protocol_version': 1, 'capabilities': ['recovery-catalog-v1'],
                               'scopes': ['system', 'home', 'vms'], 'btrfs_progs_version': 'btrfs-progs v6.17',
                               'filesystem_uuid': self.receiver_uuid, 'host_id': host,
                               'root': str(root), 'available_bytes': 1 << 40}) + '\n'
        if action == 'catalog-put':
            v = [host, words[6], words[2], words[3], words[4], words[5], words[8], words[7]]
            destination = root / host / v[2] / v[3]
            if not destination.is_dir():
                raise Die('catalog snapshot missing')
            if self.inspect(destination)['received_uuid'] != v[4]:
                raise Die('catalog received UUID mismatch')
            directory = root / host / '.catalog' / v[2]
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            f = directory / f'{v[3]}.json'
            encoded = catalog_json(v)
            if f.exists():
                if f.read_text().strip() != encoded:
                    raise Die('catalog record conflict')
            else:
                f.write_text(encoded + '\n')
            return encoded + '\n'
        scope, id = words[2], words[3]
        directory = root / host / scope
        dest = directory / id
        if action in ('inspect', 'send'):
            if not dest.is_dir():
                raise Die('snapshot missing', 3)
            meta = self.inspect(dest)
            if not meta['received_uuid']:
                raise Die('not a received snapshot')
            return json.dumps(meta) + '\n' if action == 'inspect' else self.send(dest)
        assert action == 'receive', words
        if dest.exists():
            raise Die('snapshot already exists')
        stage = directory / f'.partial-{id}'
        if stage.exists():
            raise Die('partial receive already exists; inspect it manually')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        stage.mkdir(mode=0o700)
        self.receive(stage, packet)
        if [p.name for p in stage.iterdir()] != [id]:
            raise Die('unexpected received entries')
        meta = self.inspect(stage / id)
        if meta['received_uuid'] != words[4]:
            raise Die('received UUID mismatch')
        (stage / id).rename(dest)
        stage.rmdir()
        return json.dumps(meta) + '\n'

    # -- backup/wsbackup-restore ----------------------------------------

    def restore(self, target, action, id, extra, packet):
        if action == 'hash':
            return self.hash(target / id, extra)
        assert action == 'receive', action
        if any(target.iterdir()):
            raise Die('restore target is not empty')
        self.receive(target, packet)
        if [p.name for p in target.iterdir()] != [id]:
            raise Die('unexpected received entries')
        meta = self.inspect(target / id)
        if meta['received_uuid'] != extra:
            raise Die('received UUID mismatch')
        return json.dumps(meta) + '\n'
