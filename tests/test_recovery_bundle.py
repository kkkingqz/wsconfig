import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from recovery_fixture import point,U
from test_recovery_cli import TransportPlatform,OPTIONS
try:
    import recovery_bundle as bundle
except ImportError:
    bundle=None
REPO=Path(__file__).resolve().parents[1]

class BundleTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(bundle,'autonomous exporter missing')
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name); self.output=self.directory/'ws-restore'
    def build(self): return bundle.export_bundle(self.output)
    def payload(self):
        text=self.output.read_text(); encoded=re.search("WS_PAYLOAD='([A-Za-z0-9+/=]+)'",text)[1]
        return base64.b64decode(encoded)
    def test_export_help_version_from_empty_home_without_checkout(self):
        info=self.build(); self.assertEqual(info['sha256'],hashlib.sha256(self.output.read_bytes()).hexdigest())
        env=dict(os.environ,HOME=str(self.directory),XDG_CONFIG_HOME=str(self.directory/'config'),XDG_STATE_HOME=str(self.directory/'state'))
        for arg in ('--help','--version'):
            result=subprocess.run(['bash',str(self.output),arg],cwd=self.directory,env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('ws-restore' if arg=='--version' else 'rollback',result.stdout)
        self.assertFalse(list(self.directory.glob('ws-restore-payload-*')))
    def test_payload_whitelist_and_reproducibility(self):
        self.build(); content=self.output.read_bytes()
        with zipfile.ZipFile(io.BytesIO(self.payload())) as archive:
            self.assertEqual(set(archive.namelist()),{'__main__.py','recovery.py','recovery_catalog.py','recovery_platform.py','recovery_transaction.py'})
            for name in archive.namelist():
                data=archive.read(name)
                self.assertNotIn(str(Path.home()).encode(),data); self.assertNotIn(b'BEGIN OPENSSH PRIVATE KEY',data)
        other=self.directory/'other';bundle.export_bundle(other)
        self.assertEqual(content,other.read_bytes())
    def test_refuse_overwrite_and_symlink(self):
        self.build(); content=self.output.read_bytes()
        with self.assertRaises((ValueError,FileExistsError)): self.build()
        self.assertEqual(content,self.output.read_bytes())
        link=self.directory/'link';link.symlink_to(self.output)
        with self.assertRaises(ValueError): bundle.export_bundle(link,overwrite=True)
    def test_corrupt_payload_diagnostic_and_cleanup(self):
        self.build();text=self.output.read_text();encoded=re.search("WS_PAYLOAD='([A-Za-z0-9+/=]+)'",text)[1]
        self.output.write_text(text.replace(encoded,'A'+encoded[1:]))
        env=dict(os.environ,TMPDIR=str(self.directory))
        result=subprocess.run(['bash',str(self.output),'--version'],env=env,text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('payload',result.stderr)
        self.assertFalse(list(self.directory.glob('ws-restore-payload-*')))
    def test_missing_python_diagnostic(self):
        self.build(); empty=self.directory/'empty';empty.mkdir()
        result=subprocess.run(['/bin/bash',str(self.output),'--version'],env={'PATH':str(empty)},text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('python3',result.stderr)
    def test_cli_export_dispatch_without_config(self):
        import backup
        with patch('backup.load_config',side_effect=AssertionError('must not load config')),patch('backup.probe',side_effect=AssertionError('network')):
            backup.main(['recovery-export',str(self.output)])
        self.assertTrue(self.output.is_file())
    def test_exported_modules_receive_and_refuse_switch(self):
        self.build();payload=self.directory/'recovery.pyz';payload.write_bytes(self.payload())
        script='''import sys,io,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1]); sys.path.insert(1,sys.argv[2])
import recovery, recovery_transaction as t
from test_recovery_cli import TransportPlatform,OPTIONS
from recovery_fixture import point,U
assert '.pyz' in recovery.__file__
with tempfile.TemporaryDirectory() as directory:
 top=Path(directory);p=TransportPlatform(top)
 tx=t.create_transaction(top,t.build_plan(point(),{'uuid':U},True),p)
 result=recovery.finish_restore(top,tx,OPTIONS,p,io.StringIO('NO\\n'),io.StringIO())
 assert result['phase']=='prepared'
 assert p.info(top/'@')['uuid']==p.old_root['uuid']
'''
        result=subprocess.run(['python3','-c',script,str(payload),str(REPO/'tests')],cwd=self.directory,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__': unittest.main()
