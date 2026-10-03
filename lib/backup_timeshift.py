"""Timeshift batch synchronization; original snapshots are never modified."""
from pathlib import Path
import json
import uuid
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


def inspect_copy(c, scope, id):
    p = api.run_result(api.source_command(c, 'inspect', scope, id))
    if p.returncode == 3:
        return None
    if p.returncode:
        raise ValueError('local copy inspection failed: ' + p.stderr.strip())
    return json.loads(p.stdout)


def send_copy(c, scope, copy_id, copy_uuid, parent):
    api.validate_snapshot(api.source(c, 'inspect', scope, copy_id), copy_uuid, False)
    parent_id = None
    reason = 'no common parent'
    if parent:
        local = inspect_copy(c, scope, parent['id'])
        if local is not None:
            api.validate_snapshot(local, parent['source_uuid'], False)
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


def record_path(state, record):
    return state / 'timeshift/records' / (record['id'] + '.json')


def save_record(state, record):
    api.write_json(record_path(state, record), record)


def read_records(c, state):
    records = []
    for path in sorted((state / 'timeshift/records').glob('*.json')):
        r = api.read_json(path, {})
        if not isinstance(r, dict):
            raise ValueError('invalid Timeshift journal')
        if r.get('identity') != api.identity(c):
            continue
        if (r.get('owner') != 'timeshift' or r.get('scope') not in {'system', 'home'} or
                not api.TOKEN.fullmatch(str(r.get('id', ''))) or path.stem != r['id'] or
                not api.UUID.fullmatch(str(r.get('origin_uuid', ''))) or
                r.get('status') not in {'importing', 'pending', 'success', 'superseded'}):
            raise ValueError('invalid Timeshift journal record')
        records.append(r)
    return records


def new_record(c, state, row, previous=None):
    r = {k: row[k] for k in ('scope', 'timeshift_name', 'timestamp', 'origin_uuid')}
    r.update(id='ts-' + uuid.uuid4().hex, owner='timeshift', identity=api.identity(c),
             status='importing', source_uuid=None, local_present=False)
    if previous:
        r.update(retry_of=previous['id'], clone_uuid=previous['source_uuid'])
    save_record(state, r)
    if previous:
        previous['status'] = 'superseded'
        save_record(state, previous)
    return r


def import_record(c, state, r):
    existing = inspect_copy(c, r['scope'], r['id'])
    expected_parent = r.get('clone_uuid', r['origin_uuid'])
    if existing is None:
        if r.get('retry_of'):
            args = ('clone', r['scope'], r['id'], r['retry_of'], r['clone_uuid'])
        else:
            args = ('import', r['scope'], r['id'], r['timeshift_name'], r['origin_uuid'])
        existing = json.loads(api.command(helper_command(c, *args)))
    if (existing.get('ro') is not True or existing.get('parent_uuid') != expected_parent or
            not api.UUID.fullmatch(str(existing.get('uuid', '')))):
        raise ValueError('imported copy origin/UUID verification failed')
    r.update(status='pending', source_uuid=existing['uuid'], local_present=True)
    save_record(state, r)


def select_retained(c, records):
    retained = {}
    for r in sorted(records, key=lambda r: (r['timestamp'], r['timeshift_name'], r.get('finished', ''))):
        if r['status'] != 'success':
            continue
        local = inspect_copy(c, r['scope'], r['id'])
        if local is not None:
            api.validate_snapshot(local, r['source_uuid'], False)
            retained[r['scope']] = r
    return retained


def run_batch(c, state):
    with api.operation(state, 'Timeshift batch') as (_, stage):
        stage('receiver probe')
        probe = api.probe(c)
        if not {'system', 'home'} <= set(probe.get('scopes', [])):
            raise ValueError('receiver needs Timeshift system/home support')
        stage('Timeshift inventory')
        inventory = json.loads(api.command(helper_command(c, 'inventory')))
        api.write_json(state / 'timeshift/inventory.json', inventory)
        records = read_records(c, state)
        parents = select_retained(c, records)
        result = dict(inventory, transferred=[], skipped=[], retained=parents)
        superseded = {r['retry_of'] for r in records if r.get('retry_of')}

        def finish(r):
            stage(r['scope'] + ': import/confirm ' + r['id'])
            if r['status'] == 'importing':
                import_record(c, state, r)
            r = transfer_record(c, state, r, parents.get(r['scope']))
            parents[r['scope']] = r
            api.write_json(state / 'timeshift/parents.json', parents)
            result['transferred'].append(r)
            return r

        # Resume frozen copies even if their Timeshift source disappeared.
        for r in sorted(records, key=lambda r: (r['timestamp'], r['timeshift_name'], r['scope'])):
            if r['status'] not in {'importing', 'pending'} or r['id'] in superseded:
                continue
            if r['status'] == 'pending' and not confirm_pending(c, r):
                local = inspect_copy(c, r['scope'], r['id'])
                if local is None:
                    raise ValueError('pending local copy missing; cannot preserve frozen source')
                api.validate_snapshot(local, r['source_uuid'], False)
                r = new_record(c, state, r, r)
                records.append(r)
            finish(r)

        for row in inventory['snapshots']:
            matches = [r for r in records if r['status'] == 'success' and
                       r['scope'] == row['scope'] and r['origin_uuid'] == row['origin_uuid']]
            confirmed = next((r for r in reversed(matches) if confirm_pending(c, r)), None)
            if confirmed:
                result['skipped'].append(confirmed)
                continue
            r = new_record(c, state, row)
            records.append(r)
            finish(r)
        result['retained'] = select_retained(c, records)
        api.write_json(state / 'timeshift/parents.json', result['retained'])
        # Task4 adds cleanup here only after this entire successful traversal.
        api.write_json(state / 'timeshift/last-batch.json', result)
        return result
