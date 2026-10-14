from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))

import setup_marks  # noqa: E402
import ws_select  # noqa: E402

APPS = '''# managed apps
flathub org.example.Asked mbp16=yes all=ask
flathub org.example.Everywhere all=yes
flathub org.example.Nowhere all=no
flathub org.example.Plain
flathub org.example.Mine new=no all=yes
flathub org.example.Later new=ask all=no
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
OVERRIDES = '''org.example.Asked env GDK_SCALE=2 mbp16=yes all=yes
org.example.Asked talk org.kde.StatusNotifierWatcher mbp16=yes all=no
org.example.Nowhere filesystem host mbp16=yes all=yes
org.example.Mine filesystem home new=yes
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
        (self.repo / 'flatpak/apps.txt').write_text(APPS)
        (self.repo / 'distrobox/distrobox.nix').write_text(BOXES)
        (self.repo / 'nix/hosts/mbp16').mkdir(parents=True)
        (self.repo / 'nix/hosts/mbp16/boxes.toml').write_text('yes = ["arch", "t2bce-build"]\n')
        (self.repo / 'flatpak/overrides.txt').write_text(OVERRIDES)
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
        return (self.repo / name).read_text()

    def test_offers_lines_without_own_mark_preselected_by_all(self):
        self.run_with([['org.example.Asked', 'org.example.Plain'], ['arch'], []])
        apps, boxes, overrides = (dict(a[1]) for a in self.asked)
        # An own ask is no answer: offered, checked by its own state.
        self.assertEqual(apps, {'org.example.Asked': True, 'org.example.Everywhere': True,
                                'org.example.Nowhere': False, 'org.example.Plain': True,
                                'org.example.Later': True})
        self.assertEqual(boxes, {'arch': True, 't2bce-build': False})
        # Only overrides of apps the workstation has, without its own mark.
        self.assertEqual(overrides, {'org.example.Asked env GDK_SCALE=2': True,
                                     'org.example.Asked talk org.kde.StatusNotifierWatcher': False})

    def test_answers_become_marks_of_the_host(self):
        changed = self.run_with([['org.example.Asked', 'org.example.Nowhere'], [],
                                 ['org.example.Asked env GDK_SCALE=2']])
        self.assertEqual(changed, ['flatpak/apps.txt', 'flatpak/overrides.txt', 'nix/hosts/new/boxes.toml'])
        apps = self.read('flatpak/apps.txt')
        self.assertIn('flathub org.example.Asked mbp16=yes new=yes all=ask\n', apps)
        self.assertIn('flathub org.example.Everywhere new=no all=yes\n', apps)
        self.assertIn('flathub org.example.Nowhere new=yes all=no\n', apps)
        self.assertIn('flathub org.example.Plain new=no\n', apps)
        self.assertIn('flathub org.example.Mine new=no all=yes\n', apps)
        self.assertIn('flathub org.example.Later new=no all=no\n', apps)
        self.assertIn('# managed apps\n', apps)
        self.assertIn('no = ["arch", "t2bce-build"]', self.read('nix/hosts/new/boxes.toml'))
        self.assertEqual(self.read('nix/hosts/mbp16/boxes.toml'), 'yes = ["arch", "t2bce-build"]\n')
        overrides = self.read('flatpak/overrides.txt')
        self.assertIn('org.example.Asked env GDK_SCALE=2 mbp16=yes new=yes all=yes\n', overrides)
        self.assertIn('org.example.Asked talk org.kde.StatusNotifierWatcher mbp16=yes new=no all=no\n', overrides)
        # Nowhere is chosen now: its override was offered and declined.
        self.assertIn('org.example.Nowhere filesystem host mbp16=yes new=no all=yes\n', overrides)
        self.assertIn('org.example.Mine filesystem home new=yes\n', overrides)

    def test_native_steam_host_gets_no_steam_flatpak(self):
        apps = APPS + 'flathub com.valvesoftware.Steam mbp16=yes all=ask\n'
        (self.repo / 'flatpak/apps.txt').write_text(apps)
        (self.repo / 'nix/hosts/new').mkdir(parents=True)
        (self.repo / 'nix/hosts/new/facts.nix').write_text('{\n  nativeSteam = "yes";\n}\n')
        self.run_with([[], [], []])
        self.assertNotIn('com.valvesoftware.Steam', self.asked[0][1])
        self.assertIn('flathub com.valvesoftware.Steam mbp16=yes new=no all=ask\n',
                      self.read('flatpak/apps.txt'))
        # The flatpak elsewhere: offered as before.
        (self.repo / 'nix/hosts/new/facts.nix').write_text('{\n  nativeSteam = "no";\n}\n')
        (self.repo / 'flatpak/apps.txt').write_text(apps)
        self.asked.clear()
        self.run_with([[], [], []])
        self.assertIn('com.valvesoftware.Steam', self.asked[0][1])

    def test_widgets_some_host_has_are_offered_on_a_widget_host(self):
        (self.repo / 'nix/hosts/mbp16/widgets.toml').write_text('yes = ["example", "compact"]\n')
        (self.repo / 'nix/hosts/new').mkdir(parents=True)
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
        self.assertEqual(self.read('flatpak/apps.txt'), APPS)
        self.assertFalse((self.repo / 'nix/hosts/new/boxes.toml').exists())

    def test_nothing_to_ask_changes_nothing(self):
        self.run_with([['org.example.Asked', 'org.example.Everywhere', 'org.example.Later'], ['arch'], []])
        self.asked.clear()
        self.assertEqual(self.run_with([]), [])
        self.assertEqual(self.asked, [])


if __name__ == '__main__':
    unittest.main()
