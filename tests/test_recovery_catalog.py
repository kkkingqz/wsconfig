"""Recovery catalog selection must never silently pair different snapshots."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
try:
    import recovery_catalog as catalog
except ImportError:
    catalog = None

U = '11111111-1111-1111-1111-111111111111'
V = '22222222-2222-2222-2222-222222222222'


def record(scope='system', **changes):
    return dict(schema_version=1, host_id='mbp16', source_fs_uuid=U,
                scope=scope, id='ts-' + scope, source_uuid=U, origin_uuid=V,
                timeshift_name='2026-10-03_10-00-00', timestamp=1791018000,
                **changes)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(catalog, 'recovery catalog is not implemented')

    def test_pair_has_both_scopes_of_same_point(self):
        points = catalog.build_selections([record('home'), record()])
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]['system']['id'], 'ts-system')
        self.assertEqual(points[0]['home']['id'], 'ts-home')
        self.assertEqual(points[0]['source_fs_uuid'], U)

    def test_no_home_is_never_filled_from_other_date(self):
        other = record('home')
        other.update(timeshift_name='2026-10-02_10-00-00', timestamp=1790931600)
        points = catalog.build_selections([record(), other])
        self.assertEqual(len(points), 1)
        self.assertIsNone(points[0]['home'])

    def test_duplicate_origin_is_selected_deterministically(self):
        older = record()
        newer = record()
        newer['id'] = 'ts-z'
        for entries in ([older, newer], [newer, older]):
            self.assertEqual(catalog.build_selections(entries)[0]['system']['id'], 'ts-z')

    def test_different_origins_in_one_group_are_rejected(self):
        changed = record()
        changed.update(id='ts-z', origin_uuid=U)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            catalog.build_selections([record(), changed])

    def test_distinct_hosts_and_filesystems_do_not_pair(self):
        for field, value in [('host_id', 'other'), ('source_fs_uuid', V)]:
            home = record('home')
            home[field] = value
            point = catalog.build_selections([record(), home])[0]
            self.assertIsNone(point['home'])

    def test_bad_fields_are_rejected(self):
        for field, value in [('schema_version', True), ('timestamp', True),
                             ('timestamp', -1), ('timestamp', 10_000_000_000),
                             ('scope', 'vms'), ('id', '../evil'),
                             ('host_id', 'mbp16;touch'), ('source_uuid', 'bad'),
                             ('timeshift_name', '2026-02-30_10-00-00')]:
            entry = record()
            entry[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                catalog.validate_record(entry)
        entry = record()
        entry['extra'] = 'ignored'
        with self.assertRaises(ValueError):
            catalog.validate_record(entry)
        entry = record()
        del entry['source_uuid']
        with self.assertRaises(ValueError):
            catalog.validate_record(entry)

    def test_bounded_json_lines_rejects_corruption_and_overflow(self):
        import json
        line = json.dumps(record())
        self.assertEqual(catalog.parse_catalog(line + '\n')[0]['id'], 'ts-system')
        for text in [line + '\n{bad', 'x' * 2049, (line + '\n') * 10001]:
            with self.assertRaises(ValueError):
                catalog.parse_catalog(text)

    def test_selection_rejects_home_from_different_point(self):
        point = catalog.build_selections([record(), record('home')])[0]
        point['home']['timestamp'] -= 1
        with self.assertRaises(ValueError):
            catalog.validate_selection(point)

    def test_selection_boolean_timestamp_does_not_equal_integer(self):
        entry = record()
        entry['timestamp'] = 1
        point = catalog.build_selections([entry])[0]
        point['timestamp'] = True
        with self.assertRaises(ValueError):
            catalog.validate_selection(point)

    def test_duplicate_json_fields_are_not_silently_overwritten(self):
        import json
        text = json.dumps(record())
        text = text.replace('"schema_version": 1', '"schema_version": 2, "schema_version": 1')
        with self.assertRaises(ValueError):
            catalog.parse_catalog(text)


if __name__ == '__main__':
    unittest.main()
