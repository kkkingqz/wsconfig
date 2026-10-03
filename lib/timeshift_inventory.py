"""Validate the Timeshift 25.12 Btrfs control files and actual subvolumes."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

NAME = re.compile(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\Z')
UUID = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z')


def no_links(path):
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('symlink in Timeshift path')


def origin_uuid(path):
    no_links(path)
    show = subprocess.run(['btrfs', 'subvolume', 'show', str(path)],
                          capture_output=True, text=True, check=True).stdout
    match = re.search(r'^\s*UUID:\s*(\S+)\s*$', show, re.M)
    if not match or not UUID.fullmatch(match[1]):
        raise ValueError('invalid origin UUID')
    return match[1]


def read_inventory(root):
    no_links(root)
    result = {'snapshots': [], 'missing_home': [], 'excluded': []}
    if not root.exists():
        return result
    for directory in sorted(root.iterdir()):
        try:
            no_links(directory)
            if not NAME.fullmatch(directory.name) or not directory.is_dir():
                raise ValueError('invalid Timeshift directory')
            no_links(directory / 'info.json')
            meta = json.loads((directory / 'info.json').read_text())
            if (not isinstance(meta, dict) or meta.get('type') != 'btrfs' or
                    str(meta.get('live', False)).lower() != 'false' or
                    not UUID.fullmatch(str(meta.get('sys-uuid', ''))) or
                    (directory / 'delete').exists()):
                raise ValueError('incomplete or deleting snapshot')
            created = meta.get('created')
            if not isinstance(created, str) or not created.isdigit() or int(created) <= 0:
                raise ValueError('invalid snapshot creation time')
            subvolumes = meta.get('subvolumes')
            if not isinstance(subvolumes, dict) or '@' not in subvolumes:
                raise ValueError('missing root subvolume metadata')
            rows = []
            for subvol, scope in (('@', 'system'), ('@home', 'home')):
                src = directory / subvol
                if subvol not in subvolumes:
                    if src.exists():
                        raise ValueError('subvolume metadata missing')
                    continue
                fields = subvolumes[subvol]
                if (not isinstance(fields, list) or len(fields) != 5 or fields[0] != subvol or
                        not UUID.fullmatch(str(fields[4]))):
                    raise ValueError('invalid subvolume metadata')
                if not src.is_dir():
                    raise ValueError('declared subvolume missing')
                no_links(src)
                fs = subprocess.run(['findmnt', '-nro', 'UUID', '-T', str(src)],
                                    check=True, text=True, capture_output=True).stdout.strip()
                if fs != fields[4]:
                    raise ValueError('Timeshift source filesystem mismatch')
                rows.append({'timeshift_name': directory.name, 'timestamp': int(created),
                             'scope': scope, 'origin_uuid': origin_uuid(src)})
            result['snapshots'].extend(rows)
            if not any(r['scope'] == 'home' for r in rows):
                result['missing_home'].append(directory.name)
        except (OSError, ValueError, subprocess.CalledProcessError) as e:
            result['excluded'].append({'timeshift_name': directory.name, 'reason': str(e)[:500]})
    result['snapshots'].sort(key=lambda r: (r['timestamp'], r['timeshift_name'], r['scope']))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    p.add_argument('--select', nargs=3, metavar=('SCOPE', 'NAME', 'UUID'))
    a = p.parse_args()
    try:
        result = read_inventory(a.root)
        if a.select:
            scope, name, expected = a.select
            matches = [r for r in result['snapshots'] if r['scope'] == scope and r['timeshift_name'] == name]
            if len(matches) != 1 or matches[0]['origin_uuid'] != expected:
                raise ValueError('Timeshift source missing or origin UUID changed')
            result = matches[0]
        print(json.dumps(result))
    except (ValueError, OSError) as e:
        print('wsbackup: ' + str(e), file=sys.stderr)
        sys.exit(1)
