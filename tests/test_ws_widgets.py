import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import socket
import threading
import unittest

REPO = Path(__file__).resolve().parents[1]

class WidgetCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.jsonl'
        script = f'#!{sys.executable}\n' + '''import json, os, sys
from pathlib import Path
with open(os.environ['WS_TEST_LOG'], 'a') as f: f.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
name = Path(sys.argv[0]).name
if name == 'systemctl':
    print(os.environ['WS_TEST_PID'] if 'show' in sys.argv else 'active')
elif name == 'gnome-extensions': print('State: ACTIVE')
else: sys.exit(99) # invoking Quickshell from CLI is always a failure
'''
        for name in ['qs-widgets', 'systemctl', 'gnome-extensions']:
            path = self.bin / name; path.write_text(script); path.chmod(0o755)
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps({'schemaVersion':1, 'widgets':[]}))
        self.config = self.root / 'runtime.json'
        self.config.write_text(json.dumps({'schemaVersion':2, 'qsPath':str(self.bin / 'qs-widgets'), 'socketPath':str(self.root/'control.sock'), 'manifestPath':str(self.manifest), 'adapter':'gnome'}))
        qml = self.root / '.config/quickshell/workstation-widgets'; qml.mkdir(parents=True)
        (qml / 'shell.qml').write_text('fixture')
        self.env = dict(os.environ, PATH=str(self.bin)+':'+os.environ['PATH'], HOME=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / '.config'), WSCONFIG=str(REPO),
                        WS_WIDGETS_RUNTIME=str(self.config), WS_TEST_LOG=str(self.log), WS_TEST_PID=str(os.getpid()),
                        XDG_CURRENT_DESKTOP='ubuntu:GNOME', WAYLAND_DISPLAY='wayland-test')
        self.requests = []
        self.mode = 'normal'
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(str(self.root/'control.sock'))
        os.chmod(self.root/'control.sock', 0o600)
        self.server.listen(); self.server.settimeout(.1)
        self.done = threading.Event()
        def serve():
            while not self.done.is_set():
                try: connection, _ = self.server.accept()
                except socket.timeout: continue
                except OSError: return
                with connection:
                    connection.settimeout(2)
                    try:
                        reader = connection.makefile('rb')
                        hello = json.loads(reader.readline())
                        if hello.get('protocolVersion') != 2 or hello.get('role') != 'cli': continue
                        if self.mode == 'disconnect': continue
                        def send(frame): connection.sendall((json.dumps({'protocolVersion':2, **frame})+'\n').encode())
                        send({'type':'hello', 'pid':os.getpid(), 'instanceId':'test'})
                        request = json.loads(reader.readline()); self.requests.append(request)
                        result = {'protocolVersion':2, 'pid':os.getpid(), 'instanceId':'test', 'revision':1,
                                  'selectedId':None, 'widgets':{}, 'adapter':{'connected':True}}
                        if request['method'] != 'status': result = request['args'].get('id') != 'unknown'
                        send({'type':'reply', 'seq':request['seq']+(1 if self.mode=='wrong-seq' else 0), 'ok':True, 'result':result})
                    except (OSError, ValueError): pass
        self.thread = threading.Thread(target=serve, daemon=True); self.thread.start()
        def cleanup_server(): self.done.set(); self.server.close(); self.thread.join(3)
        self.addCleanup(cleanup_server)
    def run_cli(self, *args):
        return subprocess.run([str(REPO / 'bin/ws-widgets'), *args], env=self.env, text=True, capture_output=True)
    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
    def test_status_is_read_only(self):
        result = self.run_cli('status'); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any('start' in c or 'restart' in c for c in self.calls()))
    def test_check_json_is_read_only(self):
        result = self.run_cli('check', '--json'); data = json.loads(result.stdout)
        self.assertEqual(data['failures'], 0, result.stderr)
        self.assertFalse(any('start' in c or 'restart' in c for c in self.calls()))
    def test_argument_array(self):
        result = self.run_cli('show', 'id with spaces; literal')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.requests[-1]['args'], {'id':'id with spaces; literal'})
        self.assertFalse(any(c[0]=='qs-widgets' for c in self.calls()))
    def test_unknown_id_rejected(self):
        self.assertNotEqual(self.run_cli('show', 'unknown').returncode, 0)
    def test_failed_ipc(self):
        self.mode = 'disconnect'
        self.assertNotEqual(self.run_cli('show', 'example').returncode, 0)
    def test_insecure_socket_rejected(self):
        os.chmod(self.root/'control.sock', 0o666)
        result=self.run_cli('status'); self.assertNotEqual(result.returncode, 0)
        self.assertIn('permissions',result.stderr)
        self.assertEqual(self.requests, [])
    def test_wrong_reply_rejected(self):
        self.mode='wrong-seq'
        self.assertNotEqual(self.run_cli('show','example').returncode, 0)
    def test_bad_command(self):
        self.assertEqual(self.run_cli('what').returncode, 64)
        self.assertEqual(self.calls(), [])
    def test_session_guard(self):
        for desktop, display in [('Hyprland', 'wayland-test'), ('GNOME', '')]:
            self.env.update(XDG_CURRENT_DESKTOP=desktop, WAYLAND_DISPLAY=display)
            self.assertNotEqual(self.run_cli('start').returncode, 0)
        self.assertEqual(self.calls(), [])

if __name__ == '__main__': unittest.main()
