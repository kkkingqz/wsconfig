from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))

import setup_marks  # noqa: E402
import ws_select  # noqa: E402

CATALOG = '''[remotes]
flathub = "https://example.org/repo"

[[apps]]
# managed apps
id = "org.example.Asked"
remote = "flathub"
env = { GDK_SCALE = "2" }
talk = ["org.kde.StatusNotifierWatcher"]

[[apps]]
id = "org.example.Everywhere"
remote = "flathub"
default = "yes"

[[apps]]
id = "org.example.Nowhere"
remote = "flathub"
default = "no"
filesystems = ["host"]

[[apps]]
id = "org.example.Mine"
remote = "flathub"
'''
# distrobox.nix as setup_marks reads it: name, then default.
BOXES = '''  containers = [
    {
      name = "arch";
      image = "x";
    }
    {
      name = "t2bce-build";
      default = "no";
    }
  ];
'''


class FakeTerm:
    def __init__(self):
        self.text = ''

    def write(self, text):
        self.text += text


class SetupMarksTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        (self.repo / 'flatpak').mkdir()
        (self.repo / 'distrobox').mkdir()
        (self.repo / 'flatpak/catalog.toml').write_text(CATALOG)
        (self.repo / 'distrobox/distrobox.nix').write_text(BOXES)
        for host in ('mbp16', 'new'):
            (self.repo / 'nix/hosts' / host).mkdir(parents=True)
        (self.repo / 'nix/hosts/mbp16/boxes.toml').write_text('yes = ["arch", "t2bce-build"]\n')
        # An own choice of new: not offered again.
        (self.repo / 'nix/hosts/new/flatpak.toml').write_text('# mine\nno = ["org.example.Mine"]\n')
        self.asked = []

    def run_with(self, answers):
        """answers: per checklist, the names to check (None cancels)."""
        replies = iter(answers)

        def checklist(term, title, items, checked):
            self.asked.append((title, dict(zip([n for n, _ in items], checked))))
            return next(replies)

        with mock.patch.object(ws_select, 'checklist', checklist):
            return setup_marks.run(self.repo, 'new', FakeTerm())

    def read(self, name):
        path = self.repo / 'nix/hosts/new' / name
        return tomllib.loads(path.read_text()) if path.exists() else None

    def test_offers_positions_without_a_choice_checked_by_default(self):
        self.run_with([['org.example.Asked'], ['arch'], []])
        apps, boxes, overrides = (dict(a[1]) for a in self.asked)
        self.assertEqual(apps, {'org.example.Asked': True, 'org.example.Everywhere': True,
                                'org.example.Nowhere': False})
        self.assertEqual(boxes, {'arch': True, 't2bce-build': False})
        # Only the catalog overrides of the apps the host gets.
        self.assertEqual(overrides, {'org.example.Asked env GDK_SCALE=2': True,
                                     'org.example.Asked talk org.kde.StatusNotifierWatcher': True})

    def test_answers_become_the_choice_of_the_host(self):
        changed = self.run_with([['org.example.Asked', 'org.example.Nowhere'], [],
                                 ['org.example.Asked env GDK_SCALE=2', 'org.example.Nowhere filesystem host']])
        self.assertEqual(changed, ['nix/hosts/new/flatpak.toml', 'nix/hosts/new/boxes.toml'])
        apps = self.read('flatpak.toml')
        self.assertEqual(apps['yes'], ['org.example.Asked', 'org.example.Nowhere'])
        self.assertEqual(apps['no'], ['org.example.Mine', 'org.example.Everywhere'])
        # Unchecked: a skip of this host.
        self.assertEqual(apps['overrides'], {'org.example.Asked': {'skip': ['talk org.kde.StatusNotifierWatcher']}})
        self.assertTrue((self.repo / 'nix/hosts/new/flatpak.toml').read_text().startswith('# mine\n'))
        self.assertEqual(self.read('boxes.toml')['no'], ['arch', 't2bce-build'])
        self.assertEqual((self.repo / 'nix/hosts/mbp16/boxes.toml').read_text(), 'yes = ["arch", "t2bce-build"]\n')

    def test_native_steam_host_gets_no_steam_flatpak(self):
        catalog = CATALOG + '\n[[apps]]\nid = "com.valvesoftware.Steam"\nremote = "flathub"\n'
        (self.repo / 'flatpak/catalog.toml').write_text(catalog)
        (self.repo / 'nix/hosts/new/facts.nix').write_text('{\n  nativeSteam = "yes";\n}\n')
        self.run_with([[], [], []])
        self.assertNotIn('com.valvesoftware.Steam', self.asked[0][1])
        self.assertIn('com.valvesoftware.Steam', self.read('flatpak.toml')['no'])
        # The flatpak elsewhere: offered as before.
        (self.repo / 'nix/hosts/new/facts.nix').write_text('{\n  nativeSteam = "no";\n}\n')
        (self.repo / 'nix/hosts/new/flatpak.toml').write_text('')
        self.asked.clear()
        self.run_with([[], [], []])
        self.assertIn('com.valvesoftware.Steam', self.asked[0][1])

    def test_widgets_some_host_has_are_offered_on_a_widget_host(self):
        (self.repo / 'nix/hosts/mbp16/widgets.toml').write_text('yes = ["example", "compact"]\n')
        (self.repo / 'nix/hosts/new/facts.nix').write_text('{\n  widgets = "yes";\n}\n')
        (self.repo / 'nix/hosts/new/widgets.toml').write_text('# mine\nno = ["compact"]\n')
        changed = self.run_with([[], [], ['example'], []])
        self.assertEqual(self.asked[2], ('Виджеты (ws widgets) на new', {'example': True}))
        self.assertIn('nix/hosts/new/widgets.toml', changed)
        text = (self.repo / 'nix/hosts/new/widgets.toml').read_text()
        self.assertTrue(text.startswith('# mine\n'), text)
        self.assertIn('yes = ["example"]', text)

    def test_box_catalog_of_the_repository(self):
        self.assertEqual(setup_marks.box_catalog(ROOT), [
            ('arch', 'ask'), ('wine-wayland', 'ask'), ('wine', 'ask'), ('proton', 'ask'),
            ('t2bce-build', 'no'), ('touchbar-build', 'no')])

    def test_cancel_writes_nothing(self):
        self.assertIsNone(self.run_with([['org.example.Asked'], None]))
        self.assertEqual(self.read('flatpak.toml'), {'no': ['org.example.Mine']})
        self.assertIsNone(self.read('boxes.toml'))

    def test_nothing_to_ask_changes_nothing(self):
        self.run_with([['org.example.Asked', 'org.example.Everywhere'], ['arch'], []])
        self.asked.clear()
        self.assertEqual(self.run_with([]), [])
        self.assertEqual(self.asked, [])


if __name__ == '__main__':
    unittest.main()
