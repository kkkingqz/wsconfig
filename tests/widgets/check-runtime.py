#!/usr/bin/env python3
"""Exercise production QML and real Gio transport without Quickshell clients."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from socket_client import Peer

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--runtime', required=True)
parser.add_argument('--manifest', required=True)
parser.add_argument('--wayland', action='store_true')
parser.add_argument('--idle-seconds', type=int, default=0)
args = parser.parse_args()
runtime = str(Path(args.runtime).resolve())

def counters(pid):
    text = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    switches = sum(int(line.split(':')[1]) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if 'ctxt_switches:' in line)
    return int(text[11])+int(text[12]), switches

with tempfile.TemporaryDirectory(prefix='widgets-runtime-') as tmp:
    directory = Path(tmp)
    qml = directory/'config'
    shutil.copytree(root/'widgets/quickshell', qml); qml.chmod(0o755)
    entrypoint = qml/'shell.qml'; entrypoint.chmod(0o644)
    if not args.idle_seconds:
        content = entrypoint.read_text().replace('Variants {', 'Variants {\n        id: inspectedHosts')
        entrypoint.write_text(content.rsplit('}', 1)[0]+'RuntimeInspector { hosts: inspectedHosts }\n}\n')
        shutil.copy(root/'tests/widgets/RuntimeInspector.qml', qml/'RuntimeInspector.qml')
    manifest = directory/'manifest.json'; shutil.copy(args.manifest, manifest)
    endpoint = directory/'control.sock'
    config = dict(schemaVersion=2, socketPath=str(endpoint), qsPath=runtime, manifestPath=str(manifest), adapter='gnome')
    env = dict(os.environ, WIDGETS_SOCKET=str(endpoint), WIDGETS_MANIFEST=str(manifest), WIDGETS_TEST_CONFIG=json.dumps(config))
    if not args.wayland:
        env.pop('WAYLAND_DISPLAY', None); env.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
    if args.idle_seconds: env['WIDGETS_IDLE_SECONDS'] = str(args.idle_seconds)
    runtime_log = directory/'runtime.log'; driver_log = directory/'driver.log'
    def start():
        with runtime_log.open('a') as log:
            return subprocess.Popen([runtime, '-p', str(qml)], env=env, stdout=log, stderr=log, umask=0o077)
    process = start(); driver = None
    try:
        deadline = time.monotonic()+3
        while (not endpoint.exists() or endpoint.stat().st_mode & 0o777 != 0o600) and time.monotonic()<deadline:
            assert process.poll() is None, runtime_log.read_text(); time.sleep(.02)
        peer = Peer(endpoint)
        assert not peer.call('show', id='example')['result']; peer.close()
        env['WIDGETS_TEST_PID'] = str(process.pid)
        with driver_log.open('w') as log:
            driver = subprocess.Popen(['gjs', '-m', str(root/'tests/widgets/runtime-client.js')], env=env, stdout=log, stderr=log)
        deadline = time.monotonic()+args.idle_seconds+15
        restarted = False; baseline = None
        while driver.poll() is None:
            assert process.poll() is None, 'runtime exited'
            assert time.monotonic()<deadline, 'integration timed out'
            output = driver_log.read_text()
            if 'RESTART_READY' in output and not restarted:
                process.kill(); process.wait(timeout=3); process = start(); restarted = True
            if args.idle_seconds and 'IDLE_READY' in output and baseline is None:
                time.sleep(.2); baseline = (time.monotonic(), counters(process.pid), counters(driver.pid))
            if baseline and time.monotonic()-baseline[0] >= args.idle_seconds-1:
                seconds=time.monotonic()-baseline[0]
                values = {'seconds':round(seconds, 2)}
                for label, pid, before in [('runtime',process.pid,baseline[1]),('adapter',driver.pid,baseline[2])]:
                    after=counters(pid)
                    values[label] = {'cpu_seconds':(after[0]-before[0])/os.sysconf('SC_CLK_TCK'),
                                     'context_switches_per_second':round((after[1]-before[1])/seconds,3)}
                    assert values[label]['context_switches_per_second']<1, values
                print('IDLE_MEASUREMENTS '+json.dumps(values), flush=True); baseline=None; break
            time.sleep(.03)
        driver.wait(timeout=3)
        assert driver.returncode==0, driver_log.read_text()
        assert 'TypeError' not in runtime_log.read_text(), runtime_log.read_text()
        peer=Peer(endpoint); state=peer.call('status')['result']; peer.close()
        assert not state['adapter']['connected'] and all(w['phase']=='closed' for w in state['widgets'].values()), state
        if not args.idle_seconds:
            assert restarted and 'RESTART_PASSED' in driver_log.read_text(), driver_log.read_text()
            samples = [json.loads(line.split('TEST_SURFACES ',1)[1]) for line in runtime_log.read_text().splitlines() if 'TEST_SURFACES ' in line]
            for entry in json.loads(manifest.read_text())['widgets']:
                if not entry.get('enabled',True): continue
                visible = [surface for sample in samples for surface in sample if surface['id']==entry['id'] and surface['visible'] and surface['mapped'] and surface['loaded']]
                assert visible, ('missing mapped surface',entry)
                surface=visible[-1]
                assert surface['width']==entry['width']+24 and surface['height']==entry['height']+24, surface
                if args.wayland: assert surface['dpr']==1.5, surface
                print('Actual surface: '+json.dumps(surface))
            print('Production socket, real Gio adapter, both animations, runtime restart and immediate EOF passed')
    except Exception:
        print(runtime_log.read_text()); print(driver_log.read_text() if driver_log.exists() else ''); raise
    finally:
        if driver and driver.poll() is None: driver.terminate(); driver.wait(timeout=3)
        process.terminate(); process.wait(timeout=3)
