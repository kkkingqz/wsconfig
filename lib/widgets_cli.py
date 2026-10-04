#!/usr/bin/env python3
"""Commands for the single managed widget runtime. IPC never starts a process."""
import json
import os
from pathlib import Path
import subprocess
import socket
import stat
import struct
import time
import sys

UNIT = 'workstation-widgets.service'

def config_path():
    root = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    return Path(os.environ.get('WS_WIDGETS_RUNTIME', str(root / 'workstation/widgets/runtime.json')))

def load_config():
    value = json.loads(config_path().read_text())
    if (value.get('schemaVersion') != 2 or value.get('adapter') != 'gnome'
            or not Path(value['qsPath']).is_absolute() or not Path(value['manifestPath']).is_absolute()):
        raise ValueError('invalid widget runtime config')
    socket_path(value)
    return value

def socket_path(config):
    path = config['socketPath']
    prefix = '$XDG_RUNTIME_DIR/'
    if path.startswith(prefix):
        path = os.path.join(os.environ['XDG_RUNTIME_DIR'], path[len(prefix):])
    if not Path(path).is_absolute():
        raise ValueError('invalid widget socket path')
    return Path(path)

def ipc(config, method, *args):
    try:
        path = socket_path(config)
        # Owner read/write required; any group or other bit is rejected.
        for item, kind in [(path.parent, stat.S_ISDIR), (path, stat.S_ISSOCK)]:
            info = item.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if info.st_uid != os.getuid() or mode & 0o077 or (mode & 0o600) != 0o600 or not kind(info.st_mode):
                raise ValueError('widget socket ownership or permissions invalid')
        deadline = time.monotonic() + 3
        with socket.socket(socket.AF_UNIX) as peer:
            peer.settimeout(3)
            peer.connect(str(path))
            pid, uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid(): raise ValueError('widget server UID differs')
            buffer = bytearray()
            def read():
                while b'\n' not in buffer:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0: raise TimeoutError('widget socket timed out')
                    peer.settimeout(remaining)
                    data = peer.recv(8192)
                    if not data: raise ValueError('widget socket closed before reply')
                    buffer.extend(data)
                    if len(buffer) > 65536: raise ValueError('widget frame too large')
                line, _, tail = buffer.partition(b'\n'); buffer[:] = tail
                frame = json.loads(line)
                if not isinstance(frame, dict) or frame.get('protocolVersion') != 2:
                    raise ValueError('invalid widget protocol')
                return frame
            def send(frame): peer.sendall((json.dumps({'protocolVersion':2, **frame})+'\n').encode())
            send({'type':'hello', 'role':'cli'})
            hello = read()
            if hello.get('type') != 'hello' or hello.get('pid') != pid:
                raise ValueError('invalid widget server identity')
            send({'type':'command', 'seq':1, 'method':method, 'args':{'id':args[0]} if args else {}})
            reply = read()
            if reply.get('type') != 'reply' or reply.get('seq') != 1 or not isinstance(reply.get('ok'), bool):
                raise ValueError('invalid widget reply')
            if not reply['ok']: raise ValueError(reply.get('error', 'widget command rejected'))
            result = reply['result']
            if method == 'status' and (not isinstance(result, dict) or result.get('pid') != pid or result.get('protocolVersion') != 2):
                raise ValueError('invalid widget status')
            if method != 'status' and not isinstance(result, bool): raise ValueError('invalid widget command result')
            return subprocess.CompletedProcess(method, 0, json.dumps(result), '')
    except (OSError, ValueError, KeyError, TypeError) as error:
        return subprocess.CompletedProcess(method, 1, '', str(error))

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
