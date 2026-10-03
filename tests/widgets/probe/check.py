#!/usr/bin/env python3
"""Exercise the real scoped runtime, IPC, and floating window sizing."""
import argparse
import json
import os
import select
from pathlib import Path
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    runtime = Path(args.runtime).resolve()
    assert runtime.is_file(), f"scoped runtime missing: {runtime}"
    entry = Path(__file__).with_name("shell.qml")
    env = os.environ.copy()
    if args.headless:
        env.pop("WAYLAND_DISPLAY", None)
        env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
    command = [str(runtime), "-p", str(entry)]
    with tempfile.TemporaryFile(mode="w+") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
        listener = None
        try:
            def call(method):
                return subprocess.run(command + ["ipc", "call", "--", "probe", method],
                                      env=env, capture_output=True, text=True, timeout=3)
            for _ in range(60):
                result = call("status")
                if result.returncode == 0:
                    break
                assert process.poll() is None, "probe exited"
                time.sleep(0.1)
            assert result.returncode == 0, result.stderr
            listener = subprocess.Popen(command + ["ipc", "listen", "--", "probe", "stateChanged"],
                                        env=env, stdout=subprocess.PIPE, stderr=log, text=True)
            time.sleep(0.15)
            result = call("show")
            assert result.returncode == 0
            time.sleep(0.4)
            result = call("status")
            assert result.returncode == 0, result.stderr
            status = json.loads(result.stdout.strip())
            assert status["width"] == 420 and status["height"] == 580, status
            assert status["dpr"] > 0 and status["pid"] == process.pid, status
            assert status["visible"] is True, status
            assert select.select([listener.stdout], [], [], 3)[0], "no IPC state signal"
            event = json.loads(listener.stdout.readline())
            assert event["visible"] is True, event
            assert call("hide").returncode == 0
            print(json.dumps(status))
        except Exception:
            log.seek(0)
            print(log.read())
            raise
        finally:
            if listener is not None:
                listener.terminate()
                listener.wait(timeout=3)
            log.seek(0)
            output = log.read()
            if process.poll() is not None or "Assertion" in output:
                print(output)
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
