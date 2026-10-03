"""Timeshift batch synchronization; original snapshots are never modified."""
from pathlib import Path
import backup as api


def helper_command(c, action, *args):
    return ['sudo', '/bin/bash', str(api.REPO / 'backup/wsbackup-timeshift'),
            '--uuid', c['source_fs_uuid'], '--root', c['source_snapshot_root'], action, *args]


def confirm_pending(c, record):
    other = api.remote(c, ['inspect', c['remote_host_id'], record['scope'], record['id']], missing=True)
    if other is None:
        return False
    api.validate_snapshot(other, record['source_uuid'], True)
    return True


def send_copy(c, scope, copy_id, copy_uuid, parent):
    api.validate_snapshot(api.source(c, 'inspect', scope, copy_id), copy_uuid, False)
    parent_id = None
    reason = 'no common parent'
    if parent:
        local_path = Path(c['source_snapshot_root']) / scope / parent['id']
        if local_path.exists():
            api.validate_snapshot(api.source(c, 'inspect', scope, parent['id']), parent['source_uuid'], False)
            if confirm_pending(c, parent):
                parent_id = parent['id']
            else:
                reason = 'remote parent missing'
        else:
            reason = 'local parent missing'
    sender = api.source_command(c, 'send', scope, copy_id, *([parent_id] if parent_id else []))
    api.stream(sender, api.ssh_command(c, ['receive', c['remote_host_id'], scope, copy_id, copy_uuid]))
    record = {'scope': scope, 'id': copy_id, 'source_uuid': copy_uuid,
              'identity': api.identity(c), 'parent': parent_id,
              'mode': 'incremental' if parent_id else 'full', 'full_reason': None if parent_id else reason}
    if not confirm_pending(c, record):
        raise ValueError('received snapshot missing after stream')
    return record


def transfer_record(c, state, record, parent):
    path = state / 'timeshift/records' / (record['id'] + '.json')
    record.update(status='pending', local_present=True)
    api.write_json(path, record)
    if confirm_pending(c, record):
        result = {'mode': record.get('mode', 'reconciled'), 'parent': record.get('parent')}
    else:
        result = send_copy(c, record['scope'], record['id'], record['source_uuid'], parent)
    record.update(result, status='success', finished=api.now())
    api.write_json(path, record)
    return record
