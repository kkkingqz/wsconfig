"""Timeshift batch synchronization; original snapshots are never modified."""
from pathlib import Path
import json
import uuid
import backup as api
from recovery_catalog import validate_record


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
    return api.inspect_copy(c, scope, id)


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


def catalog_record(c, record):
    return validate_record({key: record[key] for key in
                            ('scope', 'id', 'source_uuid', 'origin_uuid',
                             'timeshift_name', 'timestamp')} |
                           {'schema_version': 1, 'host_id': c['remote_host_id'],
                            'source_fs_uuid': c['source_fs_uuid']})


def publish_catalog(c, state, records):
    result = {'published': [], 'missing': []}
    for record in records:
        if record['status'] != 'success':
            continue
        if not confirm_pending(c, record):
            record.update(catalog_published=False)
            save_record(state, record)
            result['missing'].append(record['id'])
            continue
        expected = catalog_record(c, record)
        record.update(catalog_published=False)
        save_record(state, record)
        words = ['catalog-put', c['remote_host_id'], record['scope'], record['id'],
                 record['source_uuid'], record['origin_uuid'], c['source_fs_uuid'],
                 str(record['timestamp']), record['timeshift_name']]
        acknowledged = validate_record(api.remote(c, words))
        if acknowledged != expected:
            raise ValueError('catalog acknowledgement identity mismatch')
        record.update(catalog_published=True)
        save_record(state, record)
        result['published'].append(record['id'])
    return result


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
                r.get('status') not in {'importing', 'pending', 'success', 'superseded', 'abandoned'}):
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
    if previous and previous['status'] != 'success':
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


def cleanup_copies(c, state, retained):
    result = {'deleted': [], 'skipped': [], 'error': None}
    output = state / 'timeshift/cleanup.json'
    try:
        records = read_records(c, state)
        # Discovery is only an exclusion guard, never authority to delete.
        known = set()
        for path in [*(state / 'timeshift/records').glob('*.json'),
                     *(state / 'snapshots').glob('*/*.json')]:
            r = api.read_json(path, {})
            if isinstance(r, dict):
                known.add((r.get('scope'), r.get('id')))
        physical = json.loads(api.command(helper_command(c, 'list')))
        if any((r['scope'], r['id']) not in known for r in physical):
            raise ValueError('unknown managed copy; cleanup refused')
        for scope, parent in retained.items():
            local = inspect_copy(c, scope, parent['id'])
            if local is None or not confirm_pending(c, parent):
                raise ValueError('retained parent missing locally or remotely')
            api.validate_snapshot(local, parent['source_uuid'], False)
        candidates = []
        for r in records:
            parent = retained.get(r['scope'])
            if parent and r['id'] == parent['id']:
                result['skipped'].append(r['id']); continue
            local = inspect_copy(c, r['scope'], r['id'])
            if local is None:
                r['local_present'] = False; save_record(state, r); continue
            if not parent:
                raise ValueError('retained parent missing for cleanup')
            api.validate_snapshot(local, r['source_uuid'], False)
            candidates.append(r)
        # Preflight every candidate before the first destructive operation.
        api.write_json(state / 'timeshift/parents.json', retained)
        for r in candidates:
            parent = retained[r['scope']]
            api.command(helper_command(c, 'delete', r['scope'], r['id'], r['source_uuid'],
                                       parent['id'], parent['source_uuid']))
            r['local_present'] = False
            save_record(state, r)
            result['deleted'].append(r['id'])
            api.write_json(output, result)
    except BaseException as error:
        result['error'] = str(error)
        api.write_json(output, result)
        raise
    api.write_json(output, result)
    return result


def run_batch(c, state):
    with api.operation(state, 'Timeshift batch') as (_, stage):
        stage('receiver probe')
        probe = api.probe(c)
        if not {'system', 'home'} <= set(probe.get('scopes', [])):
            raise ValueError('receiver needs Timeshift system/home support')
        if 'recovery-catalog-v1' not in probe.get('capabilities', []):
            raise ValueError('receiver needs recovery catalog support; update receiver and catalog.bash')
        stage('Timeshift inventory')
        inventory = json.loads(api.command(helper_command(c, 'inventory')))
        api.write_json(state / 'timeshift/inventory.json', inventory)
        records = read_records(c, state)
        parents = select_retained(c, records)
        result = dict(inventory, transferred=[], skipped=[], abandoned=[], retained=parents)
        superseded = {r['retry_of'] for r in records if r.get('retry_of')}
        available = {(r['scope'], r['timeshift_name'], r['origin_uuid']) for r in inventory['snapshots']}

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
            if (r['status'] == 'importing' and not r.get('retry_of') and
                    (r['scope'], r['timeshift_name'], r['origin_uuid']) not in available and
                    inspect_copy(c, r['scope'], r['id']) is None):
                # Nothing was frozen; preserve the failed attempt as history,
                # rather than indefinitely blocking every later inventory.
                r.update(status='abandoned', local_present=False, finished=api.now(),
                         error='source disappeared or is no longer importable before copy creation')
                save_record(state, r)
                result['abandoned'].append(r)
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
            frozen = None
            for old in reversed(matches):
                local = inspect_copy(c, old['scope'], old['id'])
                if local is not None:
                    api.validate_snapshot(local, old['source_uuid'], False)
                    frozen = old
                    break
            # Preserve first-import contents of writable Timeshift snapshots
            # whenever a verified frozen copy survives the remote loss.
            r = new_record(c, state, row, frozen)
            records.append(r)
            finish(r)
        result['retained'] = select_retained(c, records)
        api.write_json(state / 'timeshift/parents.json', result['retained'])
        stage('publish recovery catalog')
        result['catalog'] = publish_catalog(c, state, read_records(c, state))
        stage('cleanup verified local copies')
        result['cleanup'] = cleanup_copies(c, state, result['retained'])
        current = {r['id']: r for r in read_records(c, state)}
        for r in [*result['transferred'], *result['skipped'], *result['retained'].values()]:
            r['local_present'] = current[r['id']]['local_present']
        api.write_json(state / 'timeshift/last-batch.json', result)
        return result
