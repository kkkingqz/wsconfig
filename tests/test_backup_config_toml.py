"""lib/backup.py: the backup configuration in the configuration repository
(ws help plan-v2, 7.5 and 8.8), the former config.json of the state."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import fast_tmp  # noqa: F401  (tmpfs)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import backup  # noqa: E402

COMMON = ('ssh_host = "unraid"\nremote_root = "/mnt/backup/ws"\n'
          'receiver_fs_uuid = "11111111-2222-3333-4444-555555555555"\n'
          'source_snapshot_root = "/var/lib/workstation-backup"\n')
HOST = 'remote_host_id = "pc"\nsource_fs_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"\n'
JSON = {"schema_version": 1, "ssh_host": "unraid", "remote_root": "/mnt/backup/ws",
        "receiver_fs_uuid": "11111111-2222-3333-4444-555555555555",
        "source_snapshot_root": "/var/lib/workstation-backup",
        "remote_host_id": "pc", "source_fs_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}


class TomlConfigTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = self.root / "config"
        (self.config / "backup").mkdir(parents=True)
        (self.config / "hosts/pc").mkdir(parents=True)
        self.state = self.root / "state"
        (self.state / "backup").mkdir(parents=True)
        for patch in (mock.patch.object(backup.ws_common, "CONFIG", self.config),
                      mock.patch.dict(os.environ, {"WS_STATE": str(self.state), "WS_HOST": "pc"})):
            patch.start()
            self.addCleanup(patch.stop)

    def test_common_and_host_merge_into_what_config_json_held(self):
        (self.config / "backup/config.toml").write_text(COMMON)
        (self.config / "hosts/pc/backup.toml").write_text(HOST)
        self.assertEqual(backup.current_config(), JSON)

    def test_host_file_replaces_a_common_key(self):
        (self.config / "backup/config.toml").write_text(COMMON)
        (self.config / "hosts/pc/backup.toml").write_text(HOST + 'ssh_host = "other"\n')
        self.assertEqual(backup.read_toml()["ssh_host"], "other")

    def test_checks_stay_and_name_the_files(self):
        (self.config / "backup/config.toml").write_text('ssh_host = "bad host"\n')
        with self.assertRaisesRegex(ValueError, r"backup/config.toml: ssh_host must be a safe"):
            backup.read_toml()
        (self.config / "backup/config.toml").write_text("schema_version = 1\n")
        with self.assertRaisesRegex(ValueError, "the schema is that of wsconfig.toml"):
            backup.read_toml()

    def test_former_config_json_until_there_is_toml(self):
        (self.state / "backup/config.json").write_text(json.dumps(JSON))
        self.assertEqual(backup.current_config(), JSON)
        hint = backup.migration()
        self.assertEqual(hint["write"][str(self.config / "backup/config.toml")], COMMON)
        self.assertEqual(hint["write"][str(self.config / "hosts/pc/backup.toml")], HOST)
        # Written: the TOML wins, no hint; config.json stays for the user.
        (self.config / "backup/config.toml").write_text(COMMON.replace("unraid", "tower"))
        (self.config / "hosts/pc/backup.toml").write_text(HOST)
        self.assertEqual(backup.current_config()["ssh_host"], "tower")
        self.assertIsNone(backup.migration())
        self.assertTrue((self.state / "backup/config.json").exists())

    def test_no_hint_in_the_public_checkout_of_core_and_data(self):
        (self.state / "backup/config.json").write_text(json.dumps(JSON))
        (self.config / "bin").mkdir()
        (self.config / "bin/ws").write_text("")
        self.assertIsNone(backup.migration())

    def test_nothing_configured(self):
        self.assertEqual(backup.current_config(), {"schema_version": 1})
        self.assertIsNone(backup.migration())


if __name__ == "__main__":
    unittest.main()
