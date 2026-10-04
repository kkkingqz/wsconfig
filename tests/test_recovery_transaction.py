"""Crash windows use real rename/journal files, with only Btrfs simulated."""
import json
from pathlib import Path
import tempfile
import unittest

from recovery_fixture import FakePlatform, point, received
import recovery_transaction as transaction


class PowerLoss(BaseException):
    pass


class CrashPlatform(FakePlatform):
    def arm(self, index, after=False, prepare=False):
        self.trip_index = index; self.trip_after = after
        self.prepare_fault = prepare; self.mutations = 0

    def mutation(self, operation):
        self.mutations += 1
        trip = self.mutations == self.trip_index
        if trip and not self.trip_after: raise PowerLoss()
        result = operation()
        if trip and self.trip_after: raise PowerLoss()
        return result

    def run(self, argv, input_data=None):
        mutation = (argv[:3] == ['btrfs', 'subvolume', 'snapshot'] if getattr(self, 'prepare_fault', False)
                    else argv[:3] == ['btrfs', 'subvolume', 'set-default'])
        if hasattr(self, 'trip_index') and mutation:
            return self.mutation(lambda: super(CrashPlatform, self).run(argv, input_data))
        return super().run(argv, input_data)

    def rename(self, source, destination):
        operation = lambda: super(CrashPlatform, self).rename(source, destination)
        if hasattr(self, 'trip_index') and not self.prepare_fault:
            return self.mutation(operation)
        return operation()


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(transaction, 'create_transaction'), 'durable transaction missing')

    def make(self, home=True):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        top = Path(temporary.name); platform = CrashPlatform(top)
        selection = point(home)
        checked = transaction.preflight(top, selection, received(top), platform)
        tx = transaction.create_transaction(top, checked, platform)
        return top, platform, transaction.prepare_candidates(top, tx, platform)

    def load(self, top, tx):
        return transaction.load_transaction(top, tx['id'])

    def test_switch_system_and_home_and_default(self):
        top, p, tx = self.make()
        result = transaction.switch_transaction(top, tx, p, confirmed=True)
        self.assertEqual(result['phase'], 'complete')
        self.assertEqual(p.info(top / '@')['uuid'], tx['candidates']['system']['uuid'])
        self.assertEqual(p.info(top / '@home')['uuid'], tx['candidates']['home']['uuid'])
        self.assertEqual(p.default, p.info(top / '@')['subvolume_id'])
        self.assertEqual((top / '@home/current-data').read_text(), 'historical HOME')
        self.assertEqual(p.info(top / result['backups']['system']['path'])['uuid'], p.old_root['uuid'])

    def test_system_only_preserves_home(self):
        top, p, tx = self.make(home=False)
        transaction.switch_transaction(top, tx, p, confirmed=True)
        self.assertEqual(p.info(top / '@home')['uuid'], p.old_home['uuid'])
        self.assertEqual((top / '@home/current-data').read_text(), 'current HOME')

    def test_refusing_confirmation_keeps_original_names(self):
        top, p, tx = self.make()
        with self.assertRaisesRegex(ValueError, 'confirm'):
            transaction.switch_transaction(top, tx, p, confirmed=False)
        self.assertEqual(p.info(top / '@')['uuid'], p.old_root['uuid'])
        self.assertEqual(p.info(top / '@home')['uuid'], p.old_home['uuid'])

    def test_switch_crash_before_and_after_every_mutation_resumes(self):
        for index in range(1, 6):
            for after in (False, True):
                with self.subTest(index=index, after=after):
                    top, p, tx = self.make(); p.arm(index, after)
                    with self.assertRaises(PowerLoss):
                        transaction.switch_transaction(top, tx, p, confirmed=True)
                    saved = self.load(top, tx)
                    transaction.observe_transaction(top, saved, p)
                    del p.trip_index
                    done = transaction.resume_transaction(top, saved, p, confirmed=True)
                    self.assertEqual(done['phase'], 'complete')
                    self.assertEqual(p.info(top / '@')['uuid'], tx['candidates']['system']['uuid'])
                    self.assertEqual(p.default, p.info(top / '@')['subvolume_id'])

    def test_prepare_crash_after_creation_recovers_candidate_by_parent_uuid(self):
        for index in (1, 2):
            for after in (False, True):
                with self.subTest(index=index, after=after):
                    temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
                    top = Path(temp.name); p = CrashPlatform(top)
                    checked = transaction.preflight(top, point(), received(top), p)
                    tx = transaction.create_transaction(top, checked, p); p.arm(index, after, prepare=True)
                    with self.assertRaises(PowerLoss):
                        transaction.prepare_candidates(top, tx, p)
                    saved = self.load(top, tx); del p.trip_index
                    done = transaction.resume_transaction(top, saved, p, confirmed=True)
                    self.assertEqual(done['phase'], 'complete')

    def test_foreign_subvolume_and_destination_are_never_overwritten(self):
        top, p, tx = self.make()
        path = top / '@/.meta'; data = json.loads(path.read_text())
        data['uuid'] = '33333333-3333-3333-3333-333333333333'; path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            transaction.switch_transaction(top, tx, p, confirmed=True)
        self.assertEqual(p.info(top / '@')['uuid'], data['uuid'])
        top, p, tx = self.make()
        backup = top / tx['backups']['system']['path']; backup.mkdir()
        (backup / 'foreign').write_text('retain')
        with self.assertRaises((ValueError, OSError)):
            transaction.switch_transaction(top, tx, p, confirmed=True)
        self.assertEqual((backup / 'foreign').read_text(), 'retain')

    def test_tampered_paths_and_completed_journal_are_rejected(self):
        top, p, tx = self.make()
        modified = json.loads(json.dumps(tx))
        modified['backups']['system']['path'] = '../outside'
        with self.assertRaises(ValueError):
            transaction.switch_transaction(top, modified, p, confirmed=True)
        tx['phase'] = 'complete'
        with self.assertRaises(ValueError):
            transaction.observe_transaction(top, tx, p)

    def test_journal_operations_are_bound_to_transaction(self):
        for change in ('path', 'default', 'direction', 'intent'):
            with self.subTest(change=change):
                top, p, tx = self.make()
                tx.update(direction='switch', operations=transaction.switch_operations(tx), phase='switching')
                if change == 'path': tx['operations'][0]['to'] = '@nix'
                if change == 'default': tx['operations'][-1]['id'] = 999
                if change == 'direction': tx['direction'] = 'unexpected'
                if change == 'intent': tx['intent'] = {'action': 'snapshot', 'scope': 'home', 'path': '@nix', 'source_uuid': p.old_root['uuid']}
                with self.assertRaises(ValueError): transaction.validate_transaction(tx)

    def test_candidate_id_and_boot_config_rechecked_before_switch(self):
        for change in ('id','boot'):
            top,p,tx=self.make()
            if change=='id': tx['candidates']['system']['subvolume_id']=999
            else: (top/tx['candidates']['system']['path']/'etc/fstab').write_text('damaged')
            with self.subTest(change=change),self.assertRaises(ValueError):
                transaction.switch_transaction(top,tx,p,True)
            self.assertEqual(p.info(top/'@')['uuid'],p.old_root['uuid'])

    def test_rollback_after_unpublished_candidate_retains_copy(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        top=Path(temp.name);p=CrashPlatform(top)
        tx=transaction.create_transaction(top,transaction.preflight(top,point(),received(top),p),p)
        p.arm(1,True,prepare=True)
        with self.assertRaises(PowerLoss): transaction.prepare_candidates(top,tx,p)
        tx=self.load(top,tx);del p.trip_index
        done=transaction.rollback_transaction(top,tx,p,True)
        self.assertEqual(done['phase'],'rolled-back')
        self.assertTrue((top/('@restore-'+tx['id'])).is_dir())

    def test_each_mutation_refuses_new_foreign_mount(self):
        top,p,tx=self.make();p.target_device='/dev/fixture';p.target_uuid=tx['selection']['source_fs_uuid']
        original=p.rename
        def mount_after(source,destination):
            original(source,destination)
            p.mounts=[{'source':'/dev/fixture','uuid':p.target_uuid,'target':'/media/auto'}]
        p.rename=mount_after
        with self.assertRaisesRegex(ValueError,'mounted'): transaction.switch_transaction(top,tx,p,True)
        self.assertFalse((top/'@').exists())
        p.mounts=[];p.rename=original
        self.assertEqual(transaction.resume_transaction(top,self.load(top,tx),p,True)['phase'],'complete')

    def test_rollback_retains_restored_home_and_restores_original_default(self):
        top, p, tx = self.make()
        done = transaction.switch_transaction(top, tx, p, confirmed=True)
        (top / '@home/current-data').write_text('edited after boot')
        undone = transaction.rollback_transaction(top, done, p, confirmed=True)
        self.assertEqual(undone['phase'], 'rolled-back')
        self.assertEqual(p.info(top / '@')['uuid'], p.old_root['uuid'])
        self.assertEqual(p.info(top / '@home')['uuid'], p.old_home['uuid'])
        self.assertEqual(p.default, p.old_root['subvolume_id'])
        saved_home = top / undone['restored']['home']['path']
        self.assertEqual((saved_home / 'current-data').read_text(), 'edited after boot')
        self.assertEqual(transaction.rollback_transaction(top, undone, p, confirmed=True)['phase'], 'rolled-back')

    def test_rollback_crash_before_and_after_each_mutation_resumes(self):
        for index in range(1, 6):
            for after in (False, True):
                with self.subTest(index=index, after=after):
                    top, p, tx = self.make()
                    done = transaction.switch_transaction(top, tx, p, confirmed=True)
                    p.arm(index, after)
                    with self.assertRaises(PowerLoss):
                        transaction.rollback_transaction(top, done, p, confirmed=True)
                    saved = self.load(top, done); del p.trip_index
                    undone = transaction.resume_transaction(top, saved, p, confirmed=True)
                    self.assertEqual(undone['phase'], 'rolled-back')
                    self.assertEqual(p.info(top / '@')['uuid'], p.old_root['uuid'])

    def test_partial_switch_can_be_rolled_back_without_finishing(self):
        top, p, tx = self.make(); p.arm(2, after=False)
        with self.assertRaises(PowerLoss):
            transaction.switch_transaction(top, tx, p, confirmed=True)
        saved = self.load(top, tx); del p.trip_index
        undone = transaction.rollback_transaction(top, saved, p, confirmed=True)
        self.assertEqual(undone['phase'], 'rolled-back')
        self.assertEqual(p.info(top / '@')['uuid'], p.old_root['uuid'])
        self.assertEqual(p.info(top / '@home')['uuid'], p.old_home['uuid'])


if __name__ == '__main__':
    unittest.main()
