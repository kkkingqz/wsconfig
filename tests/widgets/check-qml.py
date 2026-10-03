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
    result = subprocess.run([sys.argv[1], "-p", str(config)], env=env, timeout=15)
    if result.returncode:
        sys.exit(result.returncode)
    env["WIDGETS_IPC_TEST"] = "1"
    command = [sys.argv[1], "-p", str(config)]
    with tempfile.TemporaryFile(mode="w+") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
        listener = None
        try:
            def call(target, method, *args):
                return subprocess.run(command + ["ipc", "call", "--", target, method, *args], env=env,
                                      capture_output=True, text=True, timeout=3)
            for _ in range(40):
                result = call("widgets", "status")
                if result.returncode == 0:
                    break
                assert process.poll() is None, "runtime exited"
                time.sleep(0.05)
            state = json.loads(result.stdout)
            assert state["protocolVersion"] == 1 and state["pid"] == process.pid
            assert call("widgets", "show", "unknown").stdout.strip() == "false"
            listener = subprocess.Popen(command + ["ipc", "listen", "--", "widgets", "stateChanged"],
                                        env=env, stdout=subprocess.PIPE, stderr=log, text=True)
            time.sleep(0.1)
            assert call("widgets", "show", "example").stdout.strip() == "true"
            assert select.select([listener.stdout], [], [], 3)[0], "missing state signal"
            assert json.loads(listener.stdout.readline())["widgets"]["example"]["phase"] == "preparing"
            assert call("widgetAdapter", "placed", "example", "1").stdout.strip() == "true"
            assert call("widgets", "hide", "example").stdout.strip() == "true"
            print("Typed IPC calls, state snapshot and signal passed")
        except Exception:
            log.seek(0)
            print(log.read())
            raise
        finally:
            if listener:
                listener.terminate()
                listener.wait(timeout=3)
            process.terminate()
            process.wait(timeout=3)
