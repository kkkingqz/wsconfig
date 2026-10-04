import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prefix = self.root / 'wine/.wine'
        self.menu = self.prefix / 'drive_c/ProgramData/Microsoft/Windows/Start Menu'
        self.menu.mkdir(parents=True)
        (self.prefix / 'drive_c/App.exe').write_bytes(b'fixture')
        (self.root / 'distrobox').mkdir()
        (self.root / 'windows').mkdir()
        (self.root / 'distrobox/boxes.ini').write_text(f'[wine]\nprofile=wine\nhome={self.root}/wine\n')
        (self.root / 'windows/apps.ini').write_text('[wswin]\ndefault_box=wine\n')
        self.env = dict(os.environ, HOME=str(self.root), WSWIN_DATA=str(self.root))

    def menu_add(self, data):
        (self.menu / 'Example.lnk').write_bytes(data)
        with subprocess.Popen(['bash', str(ROOT / 'bin/wswin'), 'menu', 'add'],
                              env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, start_new_session=True) as process:
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                self.fail('shortcut parsing did not finish within 3 seconds')
            return process.returncode, stdout, stderr

    def header(self):
        data = bytearray(76)
        data[:4] = b'L\0\0\0'
        struct.pack_into('<I', data, 20, 2)
        return data

    def test_truncated_unicode_string_is_skipped_without_hanging(self):
        data = self.header()
        data.extend(struct.pack('<9I', 38, 36, 1, 0, 0, 0, 0, 36, 36))
        data.extend(b'A\0')
        status, _, stderr = self.menu_add(data)
        self.assertEqual(status, 0, stderr)
        self.assertIn('malformed shortcut', stderr)

    def test_out_of_range_unicode_offset_is_skipped(self):
        data = self.header()
        data.extend(struct.pack('<9I', 38, 36, 1, 0, 0, 0, 0, 9999, 36))
        data.extend(b'\0\0')
        status, _, stderr = self.menu_add(data)
        self.assertEqual(status, 0, stderr)
        self.assertIn('malformed shortcut', stderr)

    def test_truncated_header_is_skipped(self):
        status, _, stderr = self.menu_add(b'L\0\0\0')
        self.assertEqual(status, 0, stderr)
        self.assertIn('malformed shortcut', stderr)

    def test_valid_unicode_target_is_still_offered(self):
        target = 'C:\\App.exe\0'.encode('utf-16le')
        data = self.header()
        data.extend(struct.pack('<9I', 36 + len(target) + 2, 36, 1, 0, 0, 0, 0, 36, 36 + len(target)))
        data.extend(target + b'\0\0')
        status, _, stderr = self.menu_add(data)
        self.assertEqual(status, 0, stderr)
        self.assertIn('App.exe', stderr)
        self.assertNotIn('malformed shortcut', stderr)


if __name__ == '__main__':
    unittest.main()
