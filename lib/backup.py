"""Native Btrfs backup coordinator. No shell sourcing and no implicit target."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import uuid as uuidlib

SOURCES = {'home': '/home', 'vms': '/var/lib/vms'}
LIVE_PATHS = [*SOURCES.values(), '/var/lib/libvirt', '/etc/libvirt']
FIELDS = {'schema_version', 'ssh_host', 'remote_host_id', 'source_fs_uuid',
          'receiver_fs_uuid', 'source_snapshot_root', 'remote_root'}
REQUIRED = FIELDS - {'schema_version'}
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
UUID = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z')
REPO = Path(__file__).resolve().parents[1]


def safe_path(value):
    if not isinstance(value, str) or not value.startswith('/'):
        raise ValueError('path must be absolute')
    if (value.endswith('/') or any(p in {'.', '..'} for p in value.split('/')) or
            '//' in value or not re.fullmatch(r'/[A-Za-z0-9_./-]+', value)):
        raise ValueError('unsafe path')
    return Path(value)


def load_config(path):
    if not path.exists():
        return {'schema_version': 1}
    c = json.loads(path.read_text())
    if not isinstance(c, dict) or set(c) - FIELDS:
        raise ValueError('unknown configuration fields')
    if type(c.get('schema_version')) is not int or c.get('schema_version') != 1:
        raise ValueError('schema_version must be 1')
    for k, value in c.items():
        if k == 'schema_version':
            continue
        if not isinstance(value, str) or not value:
            raise ValueError(f'{k} must be a nonempty string; omit unset fields')
        if k in {'ssh_host', 'remote_host_id'} and not TOKEN.fullmatch(value):
            raise ValueError(f'{k} must be a safe SSH alias/host ID')
        if k.endswith('_uuid') and not UUID.fullmatch(value):
            raise ValueError(f'{k} must be a filesystem UUID')
        if k in {'source_snapshot_root', 'remote_root'}:
            safe_path(value)
    if 'source_snapshot_root' in c:
        p = safe_path(c['source_snapshot_root'])
        for source in SOURCES.values():
            if p == Path(source) or Path(source) in p.parents:
                raise ValueError('source_snapshot_root must be outside backup sources')
    return c


def build_plan(config, scope):
    if scope not in {*SOURCES, 'all'}:
        raise ValueError('scope must be home, vms or all')
    missing = sorted(REQUIRED - set(config))
    return {'configured': not missing, 'missing': missing,
            'sources': SOURCES.copy() if scope == 'all' else {scope: SOURCES[scope]},
            'transport': 'btrfs-send-over-ssh', 'protocol': 1,
            'exclusions': [], 'nested_subvolumes': 'checked before snapshot',
            'vm_policy': 'refuse running VMs', 'automatic_prune': False}


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'workstation/backup.json'


def state_path():
    return Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'workstation/backup'


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def operation(state, name):
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(state / 'lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('backup busy') from None
        id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuidlib.uuid4().hex[:12]
        path = state / 'operations' / (id + '.json')
        record = {'operation': name, 'started': now(), 'status': 'running', 'phase': 'preflight'}
        def stage(phase):
            record['phase'] = phase
            write_json(path, record)
        stage('preflight')
        try:
            yield id, stage
        except BaseException as e:
            record.update(status='failed', finished=now(), error=str(e)[:2000])
            raise
        else:
            record.update(status='success', finished=now())
        finally:
            write_json(path, record)


def stop_process(p, private_session=True):
    if p.poll() is None:
        try:
            if private_session:
                os.killpg(p.pid, signal.SIGTERM)
            else:
                p.terminate()
        except ProcessLookupError:
            p.wait()
            return
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if private_session:
                    os.killpg(p.pid, signal.SIGKILL)
                else:
                    p.kill()
            except ProcessLookupError:
                pass
            p.wait()


def authorize(args):
    if args[0] != 'sudo':
        return args
    # Keep the controlling tty and display the prompt before redirecting any
    # streams. -n prevents credentials being requested through Btrfs stdin.
    result = subprocess.run(['sudo', '-v'])
    if result.returncode:
        raise ValueError('sudo authorization failed; run backup from a terminal')
    return ['sudo', '-n', *args[1:]]


def run_result(args):
    args = authorize(args)
    private_session = args[0] != 'sudo'
    p = subprocess.Popen(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         start_new_session=private_session)
    try:
        stdout, stderr = p.communicate()
        return subprocess.CompletedProcess(args, p.returncode, stdout, stderr)
    finally:
        stop_process(p, private_session)


def command(args):
    p = run_result(args)
    if p.returncode:
        raise ValueError(f'command failed ({p.returncode}): {p.stderr.strip()[:2000]}')
    return p.stdout


def ssh_command(c, words):
    # OpenSSH joins remote arguments for a shell. Our protocol uses tokens only.
    if any(not TOKEN.fullmatch(w) for w in words):
        raise ValueError('unsafe remote command token')
    return ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=yes', c['ssh_host'], shlex.join(words)]


def remote(c, words, missing=False):
    p = run_result(ssh_command(c, words))
    if missing and p.returncode == 3:
        return None
    if p.returncode:
        raise ValueError(f'receiver failed ({p.returncode}): {p.stderr.strip()[:2000]}')
    result = json.loads(p.stdout)
    if not isinstance(result, dict):
        raise ValueError('receiver returned invalid metadata')
    return result


def probe(c):
    result = remote(c, ['probe', c['remote_host_id']])
    if (result.get('protocol_version') != 1 or
            result.get('filesystem_uuid') != c['receiver_fs_uuid'] or
            result.get('root') != c['remote_root'] or
            result.get('host_id') != c['remote_host_id']):
        raise ValueError('receiver configuration does not match local config')
    return result


def source_command(c, action, scope, id, *extra):
    return ['sudo', '/bin/bash', str(REPO / 'backup/wsbackup-source'),
            '--uuid', c['source_fs_uuid'], '--root', c['source_snapshot_root'],
            action, scope, id, *extra]


def source(c, action, scope, id, *extra):
    return json.loads(command(source_command(c, action, scope, id, *extra)))


def validate_snapshot(meta, expected, received):
    field = 'received_uuid' if received else 'uuid'
    if meta.get('ro') is not True or meta.get(field) != expected:
        raise ValueError('snapshot UUID/readonly verification failed')


def stream(sender, receiver):
    # Authorize both ends before starting either process or consuming data.
    sender = authorize(sender)
    receiver = authorize(receiver)
    sender_session = sender[0] != 'sudo'
    receiver_session = receiver[0] != 'sudo'
    # File-backed stderr avoids a deadlock if either child prints many errors.
    with tempfile.TemporaryFile() as se, tempfile.TemporaryFile() as re_, tempfile.TemporaryFile() as out:
        a = subprocess.Popen(sender, stdout=subprocess.PIPE, stderr=se, start_new_session=sender_session)
        b = None
        try:
            b = subprocess.Popen(receiver, stdin=a.stdout, stdout=out, stderr=re_, start_new_session=receiver_session)
            a.stdout.close()
            br = b.wait()
            ar = a.wait()
            if ar or br:
                se.seek(0); re_.seek(0)
                error = (se.read(2000) + re_.read(2000)).decode(errors='replace')
                raise ValueError(f'stream failed (send={ar}, receive={br}): {error.strip()}')
            out.seek(0)
            return out.read().decode()
        finally:
            if a.stdout and not a.stdout.closed:
                a.stdout.close()
            for p, private_session in ((b, receiver_session), (a, sender_session)):
                if p is not None:
                    stop_process(p, private_session)


def send(c, scope, state):
    result = {}
    with operation(state, 'send ' + scope) as (id, stage):
        stage('receiver probe'); probe(c)
        last = read_json(state / 'last-success.json', {})
        for name in (SOURCES if scope == 'all' else [scope]):
            stage(name + ': parent check')
            parent = last.get(name)
            parent_id = None
            if parent and parent.get('identity') == identity(c):
                local = source(c, 'inspect', name, parent['id'])
                validate_snapshot(local, parent['source_uuid'], False)
                other = remote(c, ['inspect', c['remote_host_id'], name, parent['id']], missing=True)
                if other is not None:
                    validate_snapshot(other, parent['source_uuid'], True)
                    parent_id = parent['id']
            stage(name + ': source snapshot')
            meta = source(c, 'snapshot', name, id)
            if not UUID.fullmatch(meta.get('uuid', '')) or meta.get('ro') is not True:
                raise ValueError('source snapshot invalid')
            stage(name + ': transfer')
            sender = source_command(c, 'send', name, id, *([parent_id] if parent_id else []))
            stream(sender, ssh_command(c, ['receive', c['remote_host_id'], name, id, meta['uuid']]))
            stage(name + ': receiver verification')
            other = remote(c, ['inspect', c['remote_host_id'], name, id])
            validate_snapshot(other, meta['uuid'], True)
            record = {'id': id, 'source_uuid': meta['uuid'], 'identity': identity(c),
                      'scope': name, 'finished': now(), 'mode': 'incremental' if parent_id else 'full',
                      'parent': parent_id}
            write_json(state / 'snapshots' / name / (id + '.json'), record)
            last[name] = record
            write_json(state / 'last-success.json', last)
            result[name] = record
    return result


def restore_test(c, scope, id, target, paths, state):
    if not TOKEN.fullmatch(id):
        raise ValueError('invalid snapshot ID')
    target = safe_path(str(target))
    if not target.is_dir() or target.is_symlink() or any(target.iterdir()):
        raise ValueError('restore target must be an existing empty directory')
    for source_dir in LIVE_PATHS:
        if target == Path(source_dir) or Path(source_dir) in target.parents:
            raise ValueError('restore target must be outside live sources')
    if not paths:
        raise ValueError('at least one --verify relative file is required')
    for rel in paths:
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', rel) or rel.startswith('/') or '..' in rel.split('/'):
            raise ValueError('unsafe verification path')
    record = read_json(state / 'snapshots' / scope / (id + '.json'), None)
    if not record or record.get('identity') != identity(c):
        raise ValueError('snapshot has no successful record for this configuration')
    with operation(state, 'restore-test ' + scope) as (_, stage):
        stage('receiver probe'); probe(c)
        remote_meta = remote(c, ['inspect', c['remote_host_id'], scope, id])
        validate_snapshot(remote_meta, record['source_uuid'], True)
        if not UUID.fullmatch(remote_meta.get('uuid', '')):
            raise ValueError('receiver snapshot UUID invalid')
        validate_snapshot(source(c, 'inspect', scope, id), record['source_uuid'], False)
        helper = ['sudo', '/bin/bash', str(REPO / 'backup/wsbackup-restore'),
                  '--uuid', c['source_fs_uuid'], '--target', str(target)]
        stage('restore receive')
        stream(ssh_command(c, ['send', c['remote_host_id'], scope, id]),
               helper + ['receive', id, record['source_uuid']])
        stage('file checksums')
        for rel in paths:
            original = command(source_command(c, 'hash', scope, id, rel)).split()[0]
            restored = command(helper + ['hash', id, rel]).split()[0]
            if original != restored:
                raise ValueError('restored checksum mismatch: ' + rel)
        result = {'scope': scope, 'id': id, 'target': str(target), 'verified_files': paths,
                  'finished': now(), 'vm_boot_verified': False}
        write_json(state / 'restore-tests' / (scope + '-' + id + '.json'), result)
    return result


def main(argv=None):
    def terminated(signum, frame):
        raise InterruptedError('terminated; see operation record')
    signal.signal(signal.SIGTERM, terminated)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan')
    p.add_argument('scope', choices=[*SOURCES, 'all'], nargs='?', default='all')
    sub.add_parser('status')
    p = sub.add_parser('check')
    p.add_argument('--remote', action='store_true')
    p = sub.add_parser('send')
    p.add_argument('scope', choices=[*SOURCES, 'all'])
    p = sub.add_parser('restore-test')
    p.add_argument('scope', choices=list(SOURCES))
    p.add_argument('id')
    p.add_argument('target', type=Path)
    p.add_argument('--verify', action='append', required=True, metavar='RELATIVE_FILE')
    args = parser.parse_args(argv)
    c = load_config(config_path())
    plan = build_plan(c, getattr(args, 'scope', 'all'))
    if args.command == 'plan':
        print(json.dumps(plan, indent=2))
    elif args.command == 'status':
        print(json.dumps({'configured': plan['configured'], 'missing': plan['missing'],
                          'state_directory': str(state_path()),
                          'last_success': read_json(state_path() / 'last-success.json', {}),
                          'restore_tests': [read_json(p, {}) for p in sorted((state_path() / 'restore-tests').glob('*.json'))]}, indent=2))
    else:
        if plan['missing']:
            raise ValueError('configuration incomplete: ' + ', '.join(plan['missing']))
        if args.command == 'check':
            result = probe(c) if args.remote else plan
            print(json.dumps(result, indent=2))
        elif args.command == 'send':
            print(json.dumps(send(c, args.scope, state_path()), indent=2))
        else:
            print(json.dumps(restore_test(c, args.scope, args.id, args.target, args.verify, state_path()), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as e:
        print(f'wsbackup: {e}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('wsbackup: interrupted; see operation record', file=sys.stderr)
        sys.exit(130)
