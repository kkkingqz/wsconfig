"""Offline root/HOME recovery, with explicit identity and boot preflight."""
import json
import os
from pathlib import Path
import re
import shlex
import uuid

from recovery_catalog import validate_selection, UUID
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


def preflight(top, selection, received, platform, expected_received=None):
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
        if not copy['readonly'] or copy['received_uuid'] != (expected_received or {}).get(scope, selection[scope]['source_uuid']):
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
    prepared = json.loads(json.dumps(checked))
    if not journal_path(top, prepared['id']).exists():
        prepared = create_transaction(top, prepared, platform)
    validate_transaction(prepared)
    candidates = prepared.setdefault('candidates', {})
    for scope in SCOPES:
        if scope not in checked['received']: continue
        copy = checked['received'][scope]
        name = ('@restore-' if scope == 'system' else '@home-restore-') + checked['id']
        path = safe_path(top / name)
        source = safe_path(top / copy['path'])
        actual = platform.inspect_snapshot(source)
        if actual['uuid'] != copy['uuid'] or not actual['readonly']:
            raise ValueError('received baseline changed')
        intent = {'action': 'snapshot', 'scope': scope, 'source_uuid': actual['uuid'], 'path': name}
        if path.exists():
            if scope not in candidates and prepared.get('intent') != intent:
                raise ValueError('candidate path already exists')
        else:
            prepared.update(phase='preparing', intent=intent)
            save_transaction(top, prepared, platform)
            platform.run(['btrfs', 'subvolume', 'snapshot', source, path])
            platform.sync_filesystem(top)
        candidate = platform.inspect_snapshot(path)
        if candidate['readonly'] or candidate['parent_uuid'] != actual['uuid']:
            raise ValueError('candidate identity mismatch')
        if scope in candidates and candidate['uuid'] != candidates[scope]['uuid']:
            raise ValueError('candidate UUID changed')
        candidates[scope] = {'path': name, **candidate}
        prepared['candidates'] = candidates
        if prepared.get('intent') == intent:
            prepared.pop('intent', None)
        save_transaction(top, prepared, platform)
    root = top / candidates['system']['path']
    for relative, text in [('etc/fstab', checked['boot']['fstab']),
                           ('boot/refind_linux.conf', checked['boot']['refind'])]:
        path = tree_path(root, relative)
        backup = path.with_name(path.name + '.before-ws-recovery-' + checked['id'])
        original = tree_path(top / checked['received']['system']['path'], relative).read_bytes()
        safe_path(backup)
        if backup.exists():
            if backup.read_bytes() != original:
                raise ValueError('boot backup identity mismatch')
        else:
            backup.write_bytes(original)
        path.write_text(text)
    for mountpoint in checked['boot']['mountpoints']:
        tree_path(root, mountpoint).mkdir(parents=True, exist_ok=True)
    platform.sync_filesystem(top)
    prepared.update(candidates=candidates, phase='prepared')
    save_transaction(top, prepared, platform)
    return prepared


SCOPES = {'system': '@', 'home': '@home'}
ID_PATTERN = re.compile(r'restore-[0-9a-f]{32}\Z')


def journal_path(top, transaction_id):
    if not isinstance(transaction_id, str) or not ID_PATTERN.fullmatch(transaction_id):
        raise ValueError('invalid recovery transaction ID')
    return safe_path(Path(top) / 'ws-recovery/transactions' / (transaction_id + '.json'))


def relative_path(value):
    if (not isinstance(value, str) or not value or value.startswith('/') or
            '..' in Path(value).parts or not re.fullmatch(r'[A-Za-z0-9_@./-]+', value)):
        raise ValueError('unsafe transaction path')
    return value


def validate_transaction(tx):
    if not isinstance(tx, dict) or tx.get('schema_version') != 1 or type(tx.get('schema_version')) is not int:
        raise ValueError('invalid recovery transaction schema')
    if not isinstance(tx.get('id'), str) or not ID_PATTERN.fullmatch(tx['id']):
        raise ValueError('invalid recovery transaction ID')
    selection = validate_selection(tx['selection'])
    phases = {'selected', 'received', 'preparing', 'prepared', 'switching',
              'root-saved', 'root-installed', 'home-saved', 'home-installed',
              'boot-selected', 'complete', 'rolled-back', 'rollback',
              'rollback-root-saved', 'rollback-root-installed',
              'rollback-home-saved', 'rollback-home-installed', 'rollback-boot-selected'}
    if tx.get('phase') not in phases:
        raise ValueError('invalid transaction phase')
    if type(tx.get('original_default')) is not int or tx['original_default'] <= 0:
        raise ValueError('invalid original default subvolume')
    for scope, live in SCOPES.items():
        enabled = scope == 'system' or selection['home'] is not None
        if not enabled:
            if tx.get('old', {}).get(scope) is not None:
                raise ValueError('unexpected HOME transaction')
            continue
        old = tx.get('old', {}).get(scope)
        if not isinstance(old, dict) or not UUID.fullmatch(str(old.get('uuid', ''))):
            raise ValueError('invalid original snapshot identity')
        for key in ('backups', 'restored', 'candidates'):
            entry = tx.get(key, {}).get(scope)
            if entry is None:
                if key == 'backups': raise ValueError('missing backup identity')
                continue
            prefix = {'backups': live + 'before-', 'restored': live + 'after-',
                      'candidates': '@restore-' if scope == 'system' else '@home-restore-'}[key]
            if entry.get('path') != prefix + tx['id']:
                raise ValueError('unexpected transaction path')
            if not UUID.fullmatch(str(entry.get('uuid', ''))):
                raise ValueError('invalid transaction snapshot UUID')
            if key == 'backups' and entry['uuid'] != old['uuid']:
                raise ValueError('backup UUID does not match original')
        if scope in tx.get('received', {}):
            relative_path(tx['received'][scope]['path'])
    direction = tx.get('direction')
    if direction is not None:
        if direction not in ('switch', 'rollback'):
            raise ValueError('invalid transaction direction')
        if direction == 'switch':
            expected = switch_operations(tx)
            if tx.get('operations') != expected:
                raise ValueError('unexpected switching operations')
        else:
            expected = []
            for scope, live in SCOPES.items():
                if tx['old'].get(scope) is None: continue
                label = 'root' if scope == 'system' else 'home'
                candidate = tx.get('candidates', {}).get(scope)
                if candidate:
                    expected.append({'action': 'rename', 'from': live, 'to': live + 'after-' + tx['id'],
                                     'uuid': candidate['uuid'], 'phase': 'rollback-' + label + '-saved'})
                expected.append({'action': 'rename', 'from': tx['backups'][scope]['path'], 'to': live,
                                 'uuid': tx['old'][scope]['uuid'], 'phase': 'rollback-' + label + '-installed'})
            expected.append({'action': 'default', 'id': tx['original_default'], 'phase': 'rollback-boot-selected'})
            operations = tx.get('operations')
            if not isinstance(operations, list) or not operations or operations[-1] != expected[-1]:
                raise ValueError('invalid rollback operations')
            cursor = 0
            for operation in operations:
                while cursor < len(expected) and expected[cursor] != operation: cursor += 1
                if cursor == len(expected): raise ValueError('unexpected rollback operation')
                cursor += 1
        if 'intent' in tx and tx['intent'] not in tx['operations']:
            raise ValueError('unexpected transaction intent')
    elif 'operations' in tx:
        raise ValueError('operations without direction')
    elif 'intent' in tx:
        intent = tx['intent']; scope = intent.get('scope')
        copy = tx.get('received', {}).get(scope)
        prefix = '@restore-' if scope == 'system' else '@home-restore-'
        if not copy or intent != {'action': 'snapshot', 'scope': scope, 'source_uuid': copy['uuid'], 'path': prefix + tx['id']}:
            raise ValueError('unexpected snapshot intent')
    return tx


def save_transaction(top, tx, platform):
    validate_transaction(tx)
    platform.save_json(journal_path(top, tx['id']), tx)


def load_transaction(top, transaction_id):
    path = journal_path(top, transaction_id)
    metadata = path.stat()
    if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022 or metadata.st_size > 1048576:
        raise ValueError('unsafe recovery transaction file')
    from recovery_catalog import _unique_fields
    tx = json.loads(path.read_text(), object_pairs_hook=_unique_fields)
    if tx.get('id') != transaction_id:
        raise ValueError('transaction filename identity mismatch')
    return validate_transaction(tx)


def default_id(top, platform):
    fields = platform.run(['btrfs', 'subvolume', 'get-default', top]).decode().split()
    if len(fields) < 2 or fields[0] != 'ID' or not fields[1].isdigit():
        raise ValueError('invalid current default subvolume')
    return int(fields[1])


def create_transaction(top, plan, platform):
    top = safe_path(top); platform.assert_offline(top)
    selection = validate_selection(plan['selection'])
    tx_id = plan.get('id', 'restore-' + uuid.uuid4().hex)
    if journal_path(top, tx_id).exists():
        raise ValueError('recovery transaction already exists')
    old = {scope: platform.inspect_snapshot(top / live)
           for scope, live in SCOPES.items() if scope == 'system' or selection['home'] is not None}
    old.setdefault('home', None)
    tx = {'schema_version': 1, 'id': tx_id, 'selection': selection, 'old': old,
          'original_default': default_id(top, platform), 'phase': 'selected',
          'backups': {scope: {'path': live + 'before-' + tx_id, **old[scope]}
                      for scope, live in SCOPES.items() if old[scope] is not None}}
    if 'received' in plan:
        tx.update(received=plan['received'], boot=plan['boot'], phase='received')
    if 'target' in plan: tx['target'] = plan['target']
    for entry in tx['backups'].values():
        if safe_path(top / entry['path']).exists():
            raise ValueError('backup path occupied')
    state = safe_path(top / 'ws-recovery')
    state.mkdir(mode=0o700, exist_ok=True)
    if state.stat().st_uid != os.geteuid() or state.stat().st_mode & 0o022:
        raise ValueError('unsafe recovery state directory')
    save_transaction(top, tx, platform)
    return tx


def observe_transaction(top, tx, platform):
    top = safe_path(top); validate_transaction(tx); platform.assert_offline(top)
    locations = {}
    for scope, live in SCOPES.items():
        old = tx['old'].get(scope)
        if old is None: continue
        candidate = tx.get('candidates', {}).get(scope)
        allowed = {old['uuid']}
        if candidate: allowed.add(candidate['uuid'])
        paths = [live, tx['backups'][scope]['path'],
                 ('@restore-' if scope == 'system' else '@home-restore-') + tx['id'],
                 live + 'after-' + tx['id']]
        found = {}
        for name in paths:
            path = safe_path(top / name)
            if not path.exists(): continue
            metadata = platform.inspect_snapshot(path)
            if metadata['uuid'] not in allowed:
                intent = tx.get('intent', {})
                orphan = (candidate is None and intent.get('action') == 'snapshot' and
                          intent.get('scope') == scope and intent.get('path') == name and
                          metadata['parent_uuid'] == intent.get('source_uuid') and not metadata['readonly'])
                if not orphan: raise ValueError('foreign recovery subvolume: ' + name)
                found['unpublished_candidate'] = name
                continue
            if metadata['uuid'] in found:
                raise ValueError('duplicate snapshot UUID in transaction paths')
            found[metadata['uuid']] = name
        if old['uuid'] not in found:
            raise ValueError('original snapshot disappeared')
        if candidate and candidate['uuid'] not in found:
            raise ValueError('candidate snapshot disappeared')
        locations[scope] = found
    current_default = default_id(top, platform)
    if tx['phase'] == 'complete':
        for scope, live in SCOPES.items():
            if scope in locations and locations[scope].get(tx['candidates'][scope]['uuid']) != live:
                raise ValueError('completed journal contradicts filesystem')
        if current_default != tx['candidates']['system']['subvolume_id']:
            raise ValueError('completed journal default changed')
    if tx['phase'] == 'rolled-back':
        for scope, live in SCOPES.items():
            if scope in locations and locations[scope].get(tx['old'][scope]['uuid']) != live:
                raise ValueError('rollback journal contradicts filesystem')
        if current_default != tx['original_default']:
            raise ValueError('rollback default changed')
    return {'phase': tx['phase'], 'locations': locations, 'default': current_default}


def switch_operations(tx):
    operations = []
    for scope, live in SCOPES.items():
        if tx['old'].get(scope) is None: continue
        label = 'root' if scope == 'system' else 'home'
        operations.extend([
            {'action': 'rename', 'from': live, 'to': tx['backups'][scope]['path'],
             'uuid': tx['old'][scope]['uuid'], 'phase': label + '-saved'},
            {'action': 'rename', 'from': tx['candidates'][scope]['path'], 'to': live,
             'uuid': tx['candidates'][scope]['uuid'], 'phase': label + '-installed'}])
    operations.append({'action': 'default', 'id': tx['candidates']['system']['subvolume_id'], 'phase': 'boot-selected'})
    return operations


def rollback_operations(tx, observation):
    operations = []; restored = {}
    for scope, live in SCOPES.items():
        if tx['old'].get(scope) is None: continue
        label = 'root' if scope == 'system' else 'home'
        candidate = tx.get('candidates', {}).get(scope)
        locations = observation['locations'][scope]
        if candidate and locations.get(candidate['uuid']) == live:
            restored[scope] = {'path': live + 'after-' + tx['id'], **candidate}
            restored[scope]['path'] = live + 'after-' + tx['id']
            operations.append({'action': 'rename', 'from': live, 'to': restored[scope]['path'],
                               'uuid': candidate['uuid'], 'phase': 'rollback-' + label + '-saved'})
        if locations.get(tx['old'][scope]['uuid']) != live:
            operations.append({'action': 'rename', 'from': tx['backups'][scope]['path'], 'to': live,
                               'uuid': tx['old'][scope]['uuid'], 'phase': 'rollback-' + label + '-installed'})
    operations.append({'action': 'default', 'id': tx['original_default'], 'phase': 'rollback-boot-selected'})
    return operations, restored


def execute_operations(top, tx, platform):
    for operation in tx['operations']:
        platform.assert_offline(top)
        observation = observe_transaction(top, tx, platform)
        if operation['action'] == 'rename':
            source = safe_path(top / relative_path(operation['from']))
            destination = safe_path(top / relative_path(operation['to']))
            if destination.exists() and platform.inspect_snapshot(destination)['uuid'] == operation['uuid']:
                continue
            if not source.exists() or platform.inspect_snapshot(source)['uuid'] != operation['uuid'] or destination.exists():
                raise ValueError('rename UUID/path precondition failed')
            tx.update(phase=operation['phase'], intent=operation)
            save_transaction(top, tx, platform)
            platform.rename(source, destination)
        else:
            if observation['default'] == operation['id']: continue
            allowed = {tx['original_default']}
            if tx.get('candidates', {}).get('system'):
                allowed.add(tx['candidates']['system']['subvolume_id'])
            if observation['default'] not in allowed:
                raise ValueError('unexpected default subvolume')
            tx.update(phase=operation['phase'], intent=operation)
            save_transaction(top, tx, platform)
            platform.run(['btrfs', 'subvolume', 'set-default', str(operation['id']), top])
        platform.sync_filesystem(top)
        tx.pop('intent', None)
        save_transaction(top, tx, platform)
    tx['phase'] = 'rolled-back' if tx['direction'] == 'rollback' else 'complete'
    observe_transaction(top, tx, platform)
    platform.sync_filesystem(top)
    save_transaction(top, tx, platform)
    return tx


def switch_transaction(top, tx, platform, confirmed):
    if confirmed is not True: raise ValueError('explicit switching confirmation required')
    observe_transaction(top, tx, platform)
    if tx['phase'] == 'complete': return tx
    if tx['phase'] != 'prepared':
        raise ValueError('transaction not prepared; use resume')
    tx.update(direction='switch', operations=switch_operations(tx), phase='switching')
    save_transaction(top, tx, platform)
    return execute_operations(top, tx, platform)


def resume_transaction(top, tx, platform, confirmed):
    observe_transaction(top, tx, platform)
    if tx['phase'] in ('complete', 'rolled-back'): return tx
    if confirmed is not True: raise ValueError('explicit resume confirmation required')
    if tx.get('direction'):
        return execute_operations(top, tx, platform)
    if 'received' not in tx:
        raise ValueError('receive is incomplete; reconnect to NAS first')
    prepared = prepare_candidates(top, tx, platform)
    return switch_transaction(top, prepared, platform, confirmed)


def rollback_transaction(top, tx, platform, confirmed):
    observation = observe_transaction(top, tx, platform)
    if tx['phase'] == 'rolled-back': return tx
    if confirmed is not True: raise ValueError('explicit rollback confirmation required')
    if tx.get('direction') == 'rollback':
        return execute_operations(top, tx, platform)
    operations, restored = rollback_operations(tx, observation)
    tx.pop('intent', None)
    tx.update(direction='rollback', operations=operations, restored=restored, phase='rollback')
    save_transaction(top, tx, platform)
    return execute_operations(top, tx, platform)
