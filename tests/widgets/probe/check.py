#!/usr/bin/env python3
"""Exercise scoped floating window sizing without spawning IPC clients."""
import argparse
import json
import os
from pathlib import Path
import subprocess
parser = argparse.ArgumentParser()
parser.add_argument('--runtime', required=True)
parser.add_argument('--headless', action='store_true')
args = parser.parse_args()
env = dict(os.environ)
if args.headless:
    env.pop('WAYLAND_DISPLAY', None)
    env.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
process = subprocess.Popen([str(Path(args.runtime).resolve()), '-p', str(Path(__file__).with_name('shell.qml'))],
                           env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    output, _ = process.communicate(timeout=5)
    assert process.returncode == 0, output
    status = json.loads(next(line.split('PROBE_STATUS ',1)[1] for line in output.splitlines() if 'PROBE_STATUS ' in line))
    assert status['width']==420 and status['height']==580 and status['visible'], status
    assert status['dpr']>0 and status['pid']==process.pid, status
    print(json.dumps(status))
finally:
    if process.poll() is None: process.kill(); process.wait()
