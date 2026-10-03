#!/usr/bin/env python3
"""Commands for the single managed widget runtime. IPC never starts a process."""
import json
import os
from pathlib import Path
import subprocess
import sys

UNIT = 'workstation-widgets.service'

def config_path():
    root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return Path(os.environ.get('WS_WIDGETS_RUNTIME', str(root / 'workstation/widgets/runtime.json')))

def load_config():
    value = json.loads(config_path().read_text())
    if (value.get('schemaVersion') != 1 or value.get('adapter') != 'gnome'
            or value.get('configName') != 'workstation-widgets'
            or not Path(value['qsPath']).is_absolute() or not Path(value['manifestPath']).is_absolute()):
        raise ValueError('invalid widget runtime config')
    return value

def ipc(config, method, *args):
    return subprocess.run([config['qsPath'], '-c', config['configName'], 'ipc', 'call', '--',
                           'widgets', method, *args], text=True, capture_output=True, timeout=3)

def in_session():
    return 'GNOME' in os.environ.get('XDG_CURRENT_DESKTOP', '').split(':') and bool(os.environ.get('WAYLAND_DISPLAY'))

def main(args):
    command = args.pop(0) if args else 'status'
    if command in ('help', '--help', '-h'):
        print('Usage: ws-widgets start|stop|restart|status|check [--json]|toggle ID|show ID|hide ID|hide-all')
        return 0
    if command == 'check':
        repo = Path(os.environ.get('WSCONFIG', str(Path(__file__).resolve().parents[1])))
        os.execv(str(repo / 'bin/ws-widgets-check'), ['ws-widgets-check', *args])
    if command not in ('start', 'stop', 'restart', 'status', 'toggle', 'show', 'hide', 'hide-all'):
        print(f'ws-widgets: unknown command: {command}', file=sys.stderr)
        return 64
    if len(args) != (1 if command in ('toggle', 'show', 'hide') else 0):
        print('ws-widgets: incorrect arguments (see --help)', file=sys.stderr)
        return 64
    if command in ('start', 'restart') and not in_session():
        print('ws-widgets: start requires a GNOME Wayland session', file=sys.stderr)
        return 78
    if command in ('start', 'stop', 'restart'):
        return subprocess.run(['systemctl', '--user', command, UNIT]).returncode
    config = load_config()
    if command == 'status':
        service = subprocess.run(['systemctl', '--user', 'is-active', UNIT], text=True, capture_output=True, timeout=3)
        print(f'Service: {service.stdout.strip()}')
        result = ipc(config, 'status')
        if result.returncode == 0:
            print(json.dumps(json.loads(result.stdout), ensure_ascii=False, indent=2))
        else:
            print(result.stderr.strip(), file=sys.stderr)
        return result.returncode or service.returncode
    result = ipc(config, 'hideAll' if command == 'hide-all' else command, *args)
    if result.returncode:
        print(result.stderr.strip() or 'ws-widgets: IPC failed', file=sys.stderr)
        return result.returncode
    if command != 'hide-all' and result.stdout.strip() != 'true':
        print('ws-widgets: unknown, disabled or unavailable widget', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    try: sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(f'ws-widgets: {error}', file=sys.stderr)
        sys.exit(1)
