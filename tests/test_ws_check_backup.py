"""ws check backup on a container host (ws help plan-wsgnomebox): no local
backup to check, the data are directories of the server."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]


class CheckBackupTests(unittest.TestCase):
    def test_a_container_host_has_no_local_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config"
            (config / "hosts/box").mkdir(parents=True)
            (config / "hosts/box/host.toml").write_text(
                '[host]\nuser = "t"\n\n[platform]\nboot = "container"\n')
            # A shared backup/config.toml, as in the configuration of wsgnomebox.
            (config / "backup").mkdir()
            (config / "backup/config.toml").write_text('ssh_host = "unraid"\n')
            env = {k: v for k, v in os.environ.items() if not k.startswith(("WS", "XDG_"))}
            env.update(HOME=tmp, WSCONFIG=str(config), WS_HOST="box")
            p = subprocess.run([str(ROOT / "libexec/ws-check-backup"), "--json"], env=env,
                               text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            result = json.loads(p.stdout)
            self.assertEqual(result["failures"], 0, result)
            self.assertIn("container host", json.dumps(result["messages"]))


if __name__ == "__main__":
    unittest.main()
