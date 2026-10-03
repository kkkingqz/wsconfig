#!/usr/bin/env python3
"""Exercise production composition and the real GNOME IPC transport."""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--runtime', required=True)
parser.add_argument('--manifest', required=True)
parser.add_argument('--wayland', action='store_true')
args = parser.parse_args()
runtime = str(Path(args.runtime).resolve())
with tempfile.TemporaryDirectory(prefix='widgets-runtime-') as tmp:
    config_root = Path(tmp) / 'config'
    qml = config_root / 'quickshell/workstation-widgets'
    shutil.copytree(root / 'widgets/quickshell', qml)
    manifest = Path(tmp) / 'manifest.json'
    shutil.copy(args.manifest, manifest)
    config = dict(schemaVersion=1, qsPath=runtime, configName='workstation-widgets', manifestPath=str(manifest), adapter='gnome')
    env = dict(os.environ, XDG_CONFIG_HOME=str(config_root), WIDGETS_MANIFEST=str(manifest), WIDGETS_TEST_CONFIG=json.dumps(config))
    if not args.wayland:
        env.pop('WAYLAND_DISPLAY', None)
        env.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
    with tempfile.TemporaryFile(mode='w+') as log:
        process = subprocess.Popen([runtime, '-c', config['configName']], env=env, stdout=log, stderr=log)
        driver = None
        try:
            driver = subprocess.Popen(['gjs', '-m', str(root / 'tests/widgets/runtime-client.js')], env=env)
            deadline = time.monotonic() + 15
            frames = {}
            while driver.poll() is None:
                assert process.poll() is None, 'production runtime exited'
                assert time.monotonic() < deadline, 'runtime integration timeout'
                if args.wayland:
                    result = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.gnome.Shell', '--object-path', '/org/gnome/Shell/Extensions/WindowControl', '--method', 'org.gnome.Shell.Extensions.WindowControl.ListDetailed'], text=True, capture_output=True, timeout=3)
                    if result.returncode == 0:
                        for window in json.loads(ast.literal_eval(result.stdout)[0]):
                            if window['pid'] == process.pid and window['title'].startswith('workstation-widgets:'):
                                frames[window['title'].split(':')[1]] = window['frame_rect']
                time.sleep(.04)
            assert driver.returncode == 0, 'GJS integration failed'
            if args.wayland:
                for entry in json.loads(manifest.read_text())['widgets']:
                    if entry.get('enabled', True):
                        frame = frames[entry['id']]
                        assert frame['width'] == entry['width'] + 24 and frame['height'] == entry['height'] + 24, frame
                print('Wayland surface frames: ' + json.dumps(frames))
        except Exception:
            log.seek(0); print(log.read()); raise
        finally:
            if driver and driver.poll() is None:
                driver.terminate(); driver.wait(timeout=3)
            process.terminate(); process.wait(timeout=3)
