#!/usr/bin/env python3
"""Read-only widget owner diagnostics, consumed by check.bash."""
import json
import os
from pathlib import Path
import subprocess
from widgets_cli import load_config, ipc, in_session, UNIT

def report(level, text): print(f'{level}\t{text}')
def run(args): return subprocess.run(args, capture_output=True, text=True, timeout=3)
def check():
    try:
        config = load_config()
        assert os.access(config['qsPath'], os.X_OK), 'scoped runtime missing or not executable'
        manifest = json.loads(Path(config['manifestPath']).read_text())
        assert manifest['schemaVersion'] == 1 and isinstance(manifest['widgets'], list), 'invalid manifest'
        root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
        qml = root / 'quickshell/workstation-widgets'
        assert (qml / 'shell.qml').is_file(), 'QML entrypoint missing'
        ids = [e['id'] for e in manifest['widgets']]
        assert len(ids) == len(set(ids)), 'duplicate widget IDs'
        for entry in manifest['widgets']:
            path = Path(entry['component'])
            assert not path.is_absolute() and '..' not in path.parts, 'unsafe component path'
            assert (qml / path).is_file(), f'missing component: {entry["id"]}'
        report('pass', 'runtime, manifest and QML components are delivered')
    except Exception as error:
        report('fail', f'widget files: {error} (ws switch)'); return
    if not in_session():
        report('warn', 'GNOME Wayland session unavailable; window/adapter checks were not performed'); return
    service = run(['systemctl', '--user', 'is-active', UNIT])
    report('pass' if service.returncode == 0 else 'fail', f'service: {service.stdout.strip()}')
    extension = run(['gnome-extensions', 'info', 'workstation-widgets@local'])
    active = extension.returncode == 0 and any(line.strip().split(':', 1)[-1].strip() == 'ACTIVE' for line in extension.stdout.splitlines())
    report('pass' if active else 'warn', 'GNOME adapter ACTIVE' if active else 'GNOME adapter unavailable; ws apply extensions and log out/in')
    result = ipc(config, 'status')
    try:
        assert result.returncode == 0, result.stderr.strip() or 'no IPC response'
        state = json.loads(result.stdout)
        assert state['protocolVersion'] == 1 and isinstance(state['instanceId'], str), 'invalid protocol'
        assert isinstance(state['pid'], int) and state['pid'] > 0, 'invalid PID'
        pid = run(['systemctl', '--user', 'show', '--property=MainPID', '--value', UNIT])
        assert int(pid.stdout.strip()) == state['pid'], 'service and IPC PIDs differ'
        assert set(state['widgets']) == {e['id'] for e in manifest['widgets'] if e.get('enabled', True)}, 'runtime registry differs from manifest'
        report('pass', f'IPC protocol and runtime instance agree (PID {state["pid"]})')
        for widget_id, widget in state['widgets'].items():
            if not widget['available']: report('fail', f'QML component unavailable: {widget_id}')
        report('pass' if state['adapter']['ready'] else 'warn', 'adapter lease ready' if state['adapter']['ready'] else 'adapter lease unavailable; window checks pending')
        if state.get('lastError'): report('warn', f'last runtime error: {state["lastError"]}')
    except Exception as error: report('fail', f'IPC: {error}')

try: check()
except Exception as error: report('fail', f'widget check: {error}')
