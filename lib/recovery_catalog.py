"""Validated recovery points, independent of local backup state or commands."""
from datetime import datetime
import json
import re

TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
UUID = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z')
NAME = re.compile(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\Z', re.ASCII)
FIELDS = {'schema_version', 'host_id', 'source_fs_uuid', 'scope', 'id',
          'source_uuid', 'origin_uuid', 'timeshift_name', 'timestamp'}
SELECTION_FIELDS = {'schema_version', 'host_id', 'source_fs_uuid',
                    'timeshift_name', 'timestamp', 'system', 'home'}
MAX_RECORD_BYTES = 2048
MAX_RECORDS = 10000


def validate_record(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('invalid recovery catalog record fields')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('unsupported recovery catalog schema')
    if (type(value['timestamp']) is not int or
            not 0 < value['timestamp'] < 10_000_000_000):
        raise ValueError('invalid Timeshift timestamp')
    for key in ('host_id', 'id'):
        if not isinstance(value[key], str) or not TOKEN.fullmatch(value[key]):
            raise ValueError('unsafe recovery catalog ' + key)
    for key in ('source_fs_uuid', 'source_uuid', 'origin_uuid'):
        if not isinstance(value[key], str) or not UUID.fullmatch(value[key]):
            raise ValueError('invalid recovery catalog ' + key)
    if value['scope'] not in ('system', 'home'):
        raise ValueError('invalid recovery catalog scope')
    name = value['timeshift_name']
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError('invalid Timeshift name')
    try:
        datetime.strptime(name, '%Y-%m-%d_%H-%M-%S')
    except ValueError as error:
        raise ValueError('invalid Timeshift date') from error
    return dict(value)


def parse_catalog(text):
    if not isinstance(text, str):
        raise ValueError('catalog must contain JSON Lines text')
    if len(text.encode('utf-8')) > MAX_RECORDS * (MAX_RECORD_BYTES + 1):
        raise ValueError('recovery catalog too large')
    lines = text.splitlines()
    if len(lines) > MAX_RECORDS:
        raise ValueError('too many recovery catalog records')
    records = []
    for line in lines:
        if not line or len(line.encode('utf-8')) > MAX_RECORD_BYTES:
            raise ValueError('invalid recovery catalog record size')
        try:
            value = json.loads(line, object_pairs_hook=_unique_fields)
        except (ValueError, TypeError) as error:
            raise ValueError('invalid recovery catalog JSON') from error
        records.append(validate_record(value))
    return records


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate recovery catalog field')
        result[key] = value
    return result


def _point(record):
    return tuple(record[key] for key in
                 ('host_id', 'source_fs_uuid', 'timeshift_name', 'timestamp'))


def build_selections(records):
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ValueError('too many or invalid recovery catalog records')
    groups = {}
    identities = {}
    for value in records:
        record = validate_record(value)
        identity = (record['host_id'], record['scope'], record['id'])
        if identity in identities and record != identities[identity]:
            raise ValueError('conflicting recovery catalog ID')
        identities[identity] = record
        scope = groups.setdefault(_point(record), {}).setdefault(record['scope'], [])
        if scope and any(other['origin_uuid'] != record['origin_uuid'] for other in scope):
            raise ValueError('ambiguous recovery point: ' + record['timeshift_name'])
        scope.append(record)
    points = []
    for (host, fs_uuid, name, timestamp), scopes in groups.items():
        if 'system' not in scopes:
            continue
        selected = {scope: max(copies, key=lambda copy: copy['id'])
                    for scope, copies in scopes.items()}
        points.append({'schema_version': 1, 'host_id': host, 'source_fs_uuid': fs_uuid,
                       'timeshift_name': name, 'timestamp': timestamp,
                       'system': selected['system'], 'home': selected.get('home')})
    return sorted(points, key=lambda p: (p['timestamp'], p['timeshift_name'],
                                        p['host_id'], p['source_fs_uuid']))


def validate_selection(value):
    if not isinstance(value, dict) or set(value) != SELECTION_FIELDS:
        raise ValueError('invalid recovery selection fields')
    system = validate_record(value['system'])
    if system['scope'] != 'system':
        raise ValueError('recovery requires system snapshot')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('invalid recovery selection schema')
    if type(value['timestamp']) is not int:
        raise ValueError('invalid recovery selection timestamp')
    if any(value[key] != system[key] for key in
           ('host_id', 'source_fs_uuid', 'timeshift_name', 'timestamp')):
        raise ValueError('recovery selection identity mismatch')
    home = value['home']
    if home is not None:
        home = validate_record(home)
        if home['scope'] != 'home' or _point(home) != _point(system):
            raise ValueError('HOME belongs to another recovery point')
    return {**value, 'system': system, 'home': home}
