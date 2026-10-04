#!/usr/bin/env python3
"""Run QML composition tests within Quickshell's configuration root."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import json
import select
import time

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="widgets-qml-") as temporary:
    config = Path(temporary) / "config"
    shutil.copytree(root / "widgets/quickshell", config)
    config.chmod(0o755)
    (config / "shell.qml").unlink(missing_ok=True)
    shutil.copy(root / "tests/widgets/qml/shell.qml", config / "shell.qml")
    if (root / "tests/widgets/qml/broken").exists():
        shutil.copytree(root / "tests/widgets/qml/broken", config / "broken")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
    env.pop("WAYLAND_DISPLAY", None)
    env["WIDGETS_SOCKET"] = str(Path(temporary)/"control.sock")
    result = subprocess.run([sys.argv[1], "-p", str(config)], env=env, timeout=15)
    if result.returncode:
        sys.exit(result.returncode)
    env["WIDGETS_IPC_TEST"] = "1"
    from socket_client import Peer
    endpoint = Path(temporary)/"control.sock"
    env["WIDGETS_SOCKET"] = str(endpoint)
    command = [sys.argv[1], "-p", str(config)]
    with tempfile.TemporaryFile(mode="w+") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log, umask=0o077)
        peers = []
        def cli(method, **args):
            peer = Peer(endpoint); peers.append(peer)
            assert peer.greeting['type'] == 'hello'
            result = peer.call(method, **args); peer.close(); peers.remove(peer)
            return result
        try:
            deadline = time.monotonic()+3
            while (not endpoint.exists() or endpoint.stat().st_mode & 0o777 != 0o600) and time.monotonic()<deadline:
                assert process.poll() is None, "runtime exited"
                time.sleep(.02)
            assert endpoint.exists(), "missing runtime socket"
            assert not cli('show', id='example')['result'], 'no adapter must reject opening'
            adapter = Peer(endpoint, 'adapter'); peers.append(adapter)
            state = adapter.greeting['state']
            assert state['protocolVersion'] == 2 and state['pid'] == process.pid and state['adapter']['connected']
            assert not cli('show', id='unknown')['result']
            assert cli('show', id='example')['result']
            assert adapter.read()['state']['widgets']['example']['phase'] == 'preparing'
            assert not cli('placed', id='example', requestId=1)['ok'], 'role violation'
            assert adapter.call('placed', id='example', requestId=1)['result']
            replacement = Peer(endpoint, 'adapter'); peers.append(replacement)
            assert replacement.greeting['state']['widgets']['example']['phase'] == 'opening'
            adapter.close(); peers.remove(adapter)
            assert cli('status')['result']['adapter']['connected'], 'old EOF affected replacement'
            replacement.close(); peers.remove(replacement)
            time.sleep(.05)
            state = cli('status')['result']
            assert not state['adapter']['connected'] and state['widgets']['example']['phase'] == 'closed'
            adapter = Peer(endpoint, 'adapter'); peers.append(adapter)
            assert cli('show', id='example')['result']
            time.sleep(2.1)
            state = cli('status')['result']
            assert state['widgets']['example']['phase'] == 'closed' and 'timed out' in state['lastError']['reason']
            assert cli('show', id='example')['result']
            state = cli('status')['result']
            reason = 'Пример ошибки'
            frame = json.dumps({'protocolVersion':2, 'type':'command', 'seq':99, 'method':'placementFailed',
                                'args':{'id':'example', 'requestId':state['widgets']['example']['requestId'], 'reason':reason}}, ensure_ascii=False).encode()+b'\n'
            split = frame.index('П'.encode())+1
            adapter.socket.sendall(frame[:split]); time.sleep(.05); adapter.socket.sendall(frame[split:])
            while adapter.read().get('seq') != 99: pass
            assert cli('status')['result']['lastError']['reason'] == reason, 'fragmented UTF-8 corrupted'
            adapter.close(); peers.remove(adapter); time.sleep(.05)
            import socket
            follow = ''.join(json.dumps(frame)+'\n' for frame in [
                {'protocolVersion':2,'type':'hello','role':'adapter'},
                {'protocolVersion':2,'type':'command','seq':1,'method':'toggle','args':{'id':'example'}},
                {'protocolVersion':2,'type':'command','seq':2,'method':'placed','args':{'id':'example','requestId':state['widgets']['example']['requestId']+2}}])
            for bad in ['broken JSON', json.dumps({'protocolVersion':2,'type':'hello','role':'invalid'}), 'x'*65537]:
                with socket.socket(socket.AF_UNIX) as rejected:
                    rejected.connect(str(endpoint)); rejected.sendall((bad+'\n'+follow).encode()); time.sleep(.05)
                time.sleep(.05)
                result=cli('status')['result']
                assert not result['adapter']['connected'], 'rejected peer became ghost adapter'
                assert all(w['phase']=='closed' for w in result['widgets'].values()), 'rejected peer dispatched command'
            print("Socket snapshots, CLI, takeover, EOF, deadlines, UTF-8 and permanent rejection passed")
        except Exception:
            log.seek(0); print(log.read()); raise
        finally:
            for peer in peers: peer.close()
            process.terminate(); process.wait(timeout=3)
