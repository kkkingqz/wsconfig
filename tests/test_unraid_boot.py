"""backup/unraid/boot.sh on stubs: users, sudo and sshd rules per
workstation, written under WSBACKUP_PREFIX instead of /."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import fast_tmp  # noqa: F401  (tmpfs)

ROOT = Path(__file__).resolve().parents[1]

STUBS = {
    "id": "#!/bin/sh\nexit 1\n",
    "useradd": '#!/bin/sh\necho "useradd $*" >> "$CALLS"\n',
    "usermod": '#!/bin/sh\necho "usermod $*" >> "$CALLS"\n',
    "visudo": "#!/bin/sh\nexit 0\n",
    "sshd": "#!/bin/sh\nexit 0\n",
    "logger": "#!/bin/sh\nexit 0\n",
    # install without -o/-g: the test does not run as root.
    "install": '#!/bin/bash\nargs=()\nwhile (($#)); do case "$1" in -o|-g) shift 2 ;; '
               '*) args+=("$1"); shift ;; esac; done\nexec /usr/bin/install "${args[@]}"\n',
}
CONF = "ROOT=/mnt/disk6/wsbackup\nFS_UUID=66f9196f-99fd-403b-a20f-35671c5b62fe\nHOST_ID={}\n"
LIB = "usr/local/libexec/wsbackup"
SINGLE_SSHD = (
    "Port 22\nAllowUsers root wsbackup\n# wsbackup begin (managed by /boot/config/wsbackup/boot.sh)\n"
    "Match User wsbackup\n\tAuthorizedKeysFile /etc/ssh/wsbackup_authorized_keys\n"
    "\tForceCommand sudo -n /usr/local/libexec/wsbackup/unraid/wsbackup-receiver "
    "/usr/local/libexec/wsbackup/receiver.conf\n\tPasswordAuthentication no\n"
    "\tKbdInteractiveAuthentication no\n\tPermitTTY no\n\tAllowTcpForwarding no\n"
    "\tAllowAgentForwarding no\n\tAllowStreamLocalForwarding no\n\tX11Forwarding no\n"
    "\tPermitTunnel no\n# wsbackup end\n")
SINGLE_SUDOERS = (
    "# Managed by /boot/config/wsbackup/boot.sh\n"
    'Defaults!/usr/local/libexec/wsbackup/unraid/wsbackup-receiver env_keep += "SSH_ORIGINAL_COMMAND"\n'
    "wsbackup ALL=(root) NOPASSWD: /usr/local/libexec/wsbackup/unraid/wsbackup-receiver "
    "/usr/local/libexec/wsbackup/receiver.conf\n")


class UnraidBootTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.flash = self.root / "flash"
        (self.flash / "unraid").mkdir(parents=True)
        for f in ("unraid/wsbackup-receiver", "unraid/catalog.bash"):
            shutil.copy(ROOT / "backup" / f, self.flash / f)
        shutil.copy(ROOT / "backup/btrfs-common.bash", self.flash)
        self.prefix = self.root / "prefix"
        (self.prefix / "etc/ssh").mkdir(parents=True)
        (self.prefix / "etc/sudoers.d").mkdir()
        self.sshd = self.prefix / "etc/ssh/sshd_config"
        self.sshd.write_text("Port 22\nAllowUsers root\n")
        stubs = self.root / "bin"
        stubs.mkdir()
        for name, text in STUBS.items():
            (stubs / name).write_text(text)
            (stubs / name).chmod(0o755)
        self.calls = self.root / "calls"
        self.env = dict(os.environ, PATH=f"{stubs}:{os.environ['PATH']}",
                        WSBACKUP_PREFIX=str(self.prefix), CALLS=str(self.calls))

    def workstation(self, host=None, host_id=None):
        d = self.flash if host is None else self.flash / "hosts" / host
        d.mkdir(parents=True, exist_ok=True)
        (d / "receiver.conf").write_text(CONF.format(host_id or host or "mbp16"))
        (d / "authorized_keys").write_text(f"restrict ssh-ed25519 AAAA {host or 'mbp16'}\n")

    def boot(self, script=None):
        script = script or ROOT / "backup/unraid/boot.sh"
        shutil.copy(script, self.flash / "boot.sh")
        return subprocess.run(["bash", str(self.flash / "boot.sh")], env=self.env,
                              text=True, capture_output=True)

    def test_single_workstation_as_before(self):
        # Byte for byte what the single-host boot.sh wrote (until 2026-10-10):
        # the sshd and sudo rules on tower stay as they are.
        self.workstation()
        result = self.boot()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sshd.read_text(), SINGLE_SSHD)
        self.assertEqual((self.prefix / "etc/sudoers.d/wsbackup").read_text(), SINGLE_SUDOERS)

    def test_each_workstation_its_own_user_config_and_command(self):
        self.workstation()
        self.workstation("legiongo")
        result = self.boot()
        self.assertEqual(result.returncode, 0, result.stderr)
        sudoers = (self.prefix / "etc/sudoers.d/wsbackup").read_text()
        self.assertIn(f"wsbackup ALL=(root) NOPASSWD: /{LIB}/unraid/wsbackup-receiver /{LIB}/receiver.conf\n", sudoers)
        self.assertIn(f"wsbackup-legiongo ALL=(root) NOPASSWD: /{LIB}/unraid/wsbackup-receiver "
                      f"/{LIB}/hosts/legiongo.conf\n", sudoers)
        sshd = self.sshd.read_text()
        self.assertIn("AllowUsers root wsbackup wsbackup-legiongo\n", sshd)
        self.assertIn("Match User wsbackup-legiongo\n"
                      "\tAuthorizedKeysFile /etc/ssh/wsbackup-legiongo_authorized_keys\n"
                      f"\tForceCommand sudo -n /{LIB}/unraid/wsbackup-receiver /{LIB}/hosts/legiongo.conf\n", sshd)
        conf = self.prefix / LIB / "hosts/legiongo.conf"
        self.assertEqual(conf.read_text(), CONF.format("legiongo"))
        self.assertEqual(conf.stat().st_mode & 0o777, 0o600)
        self.assertIn("legiongo", (self.prefix / "etc/ssh/wsbackup-legiongo_authorized_keys").read_text())
        self.assertIn("useradd --system --user-group --home-dir /var/empty --no-create-home "
                      "--shell /bin/bash wsbackup-legiongo", self.calls.read_text())
        again = self.boot()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("sshd already configured", again.stderr)
        self.assertEqual(self.sshd.read_text().count("Match User"), 2)

    def test_host_directory_must_match_its_host_id(self):
        self.workstation()
        self.workstation("legiongo", host_id="mbp16")
        result = self.boot()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HOST_ID must be legiongo", result.stderr)
        self.assertEqual(self.sshd.read_text(), "Port 22\nAllowUsers root\n")

    def test_a_new_workstation_alone(self):
        self.workstation("legiongo")
        result = self.boot()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Match User wsbackup\n", self.sshd.read_text())
        self.assertIn("Match User wsbackup-legiongo\n", self.sshd.read_text())


if __name__ == "__main__":
    unittest.main()
