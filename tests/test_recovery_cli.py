import io
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from recovery_fixture import FakePlatform, point, U
import recovery_transaction as transaction
try:
    import recovery
except ImportError:
    recovery = None

OPTIONS = {'host': 'nas.example', 'user': 'root', 'port': 22, 'config': '/usb/ssh_config', 'key': '/usb/id_ed25519'}
NAS_UUID = '33333333-3333-3333-3333-333333333333'

class TransportPlatform(FakePlatform):
    def remote(self, options, words):
        self.remote_calls = getattr(self, 'remote_calls', []) + [words]
        if words[0] == 'probe': return json.dumps({'protocol_version': 1, 'capabilities': ['recovery-catalog-v1'], 'host_id':'mbp16', 'filesystem_uuid':NAS_UUID}).encode()
        if words[0] == 'catalog-list': return b'\n'.join(json.dumps(point()[s]).encode() for s in ('system','home'))
        return json.dumps({'uuid': NAS_UUID, 'received_uuid': point()[words[2]]['source_uuid'], 'ro': True}).encode()
    def receive_stream(self, options, words, destination):
        path = Path(destination) / words[-1]
        self.seed(path, received_uuid=NAS_UUID, readonly=True)
        if words[2] == 'system': self.boot(path)
        if getattr(self, 'fail', False): raise ValueError('failed stream')
        if getattr(self, 'extra', False): (Path(destination)/'unexpected').mkdir()
        if getattr(self, 'wrong', False):
            m = self.info(path); m['received_uuid']=U; (path/'.meta').write_text(json.dumps(m))
        if getattr(self, 'writable', False):
            m = self.info(path); m['readonly']=False; (path/'.meta').write_text(json.dumps(m))

class CLITests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(recovery, 'Live recovery CLI missing')
    def fixture(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        top = Path(temp.name); p = TransportPlatform(top)
        plan = transaction.build_plan(point(), {'uuid':U, 'device':'/dev/fixture'}, True)
        tx = transaction.create_transaction(top, plan, p)
        return top,p,tx
    def test_ssh_explicit_paths_and_host_check(self):
        for host in ('nas.example','192.0.2.1','2001:db8::1','nas-alias'):
            args = recovery.ssh_argv(dict(OPTIONS, host=host), ['probe','mbp16'])
            self.assertIn('StrictHostKeyChecking=yes',args)
            self.assertEqual(args[args.index('-F')+1],'/usb/ssh_config')
            self.assertEqual(args[args.index('-i')+1],'/usb/id_ed25519')
        for field,value in [('host','nas;touch x'),('host','-oProxyCommand=evil'),('user','root@nas'),('port',True),('port',65536),('key','relative'),('config','~/config')]:
            with self.subTest(field=field,value=value), self.assertRaises(ValueError): recovery.ssh_argv(dict(OPTIONS, **{field:value}), ['probe','mbp16'])
        with self.assertRaises(ValueError): recovery.ssh_argv(OPTIONS,['send','mbp16','system','id;evil'])
    def test_catalog_capability_and_identity(self):
        _,p,_ = self.fixture()
        records = recovery.read_catalog(OPTIONS,'mbp16',p)
        self.assertEqual(len(records),2)
        with patch.object(p,'remote',return_value=b'{}'):
            with self.assertRaises(ValueError): recovery.read_catalog(OPTIONS,'mbp16',p)
        with patch.object(p,'remote',side_effect=[p.remote(OPTIONS,['probe','mbp16']), b'x'*20000001]):
            with self.assertRaises(ValueError): recovery.read_catalog(OPTIONS,'mbp16',p)
    def test_receive_full_uses_nas_uuid_and_keeps_secrets_out_of_journal(self):
        top,p,tx = self.fixture()
        result = recovery.receive_selection(top,tx,OPTIONS,p)
        self.assertEqual(result['phase'],'received')
        for entry in result['received'].values(): self.assertEqual(entry['received_uuid'],NAS_UUID)
        saved = transaction.journal_path(top,tx['id']).read_text()
        for secret in ('ssh_config','id_ed25519','nas.example'): self.assertNotIn(secret,saved)
        self.assertEqual(p.info(top/'@')['uuid'],p.old_root['uuid'])
    def test_failed_stream_retries_in_new_directory_and_keeps_partials(self):
        top,p,tx = self.fixture(); p.fail=True
        with self.assertRaises(ValueError): recovery.receive_selection(top,tx,OPTIONS,p)
        saved = transaction.load_transaction(top,tx['id'])
        first = saved['receive_attempts'][-1]['path']; self.assertTrue((top/first).is_dir())
        p.fail=False
        result = recovery.receive_selection(top,saved,OPTIONS,p)
        self.assertNotEqual(first,result['receive_attempts'][1]['path'])
        self.assertTrue((top/first).is_dir())
    def test_bad_receive_refuses_before_switch(self):
        for fault in ('extra','wrong','writable'):
            top,p,tx = self.fixture(); setattr(p,fault,True)
            with self.subTest(fault=fault), self.assertRaises(ValueError): recovery.receive_selection(top,tx,OPTIONS,p)
            self.assertEqual(p.info(top/'@')['uuid'],p.old_root['uuid'])
    def test_plan_confirmation_and_refusal(self):
        top,p,tx = self.fixture(); output=io.StringIO()
        result=recovery.finish_restore(top,tx,OPTIONS,p,io.StringIO('NO\n'),output)
        self.assertEqual(result['phase'],'prepared')
        for value in (U,'mbp16','ts-system','@nix','EFI',tx['id']): self.assertIn(value,output.getvalue())
        self.assertEqual(p.info(top/'@')['uuid'],p.old_root['uuid'])
    def test_wizard_uses_tty_and_offers_unfinished_before_network(self):
        top,p,tx=self.fixture()
        @contextmanager
        def opened(device,fs_uuid):
            yield top,{'device':device,'uuid':fs_uuid,'model':'Fixture SSD','available_bytes':1000000}
        p.open_target=opened
        class Terminal(io.StringIO):
            def __enter__(self): return self
            def __exit__(self,*args): return False
        tty=Terminal('1\nstatus\n')
        # Separate read and write offsets, as a real terminal does.
        tty.reader=io.StringIO('1\nstatus\n'); tty.readline=tty.reader.readline
        with patch('recovery.os.geteuid',return_value=0), patch('recovery.dependencies'), patch('recovery.open_tty',return_value=tty), patch('recovery.LivePlatform',return_value=p):
            self.assertEqual(recovery.main(['--device','/dev/fixture']),0)
        self.assertIn('unfinished transaction',tty.getvalue())
        self.assertFalse(hasattr(p,'remote_calls'))

    def test_non_tty_refuses_before_mount(self):
        with patch('recovery.os.geteuid',return_value=0), patch('recovery.open_tty',side_effect=ValueError('TTY required')):
            with self.assertRaisesRegex(ValueError,'TTY'): recovery.main([])
    def test_help_and_version_require_no_privilege(self):
        with patch('recovery.os.geteuid',return_value=1000), patch('recovery.open_tty',side_effect=AssertionError):
            with self.assertRaises(SystemExit) as done: recovery.main(['--help'])
            self.assertEqual(done.exception.code,0)
            with self.assertRaises(SystemExit) as done: recovery.main(['--version'])
            self.assertEqual(done.exception.code,0)

if __name__=='__main__': unittest.main()
