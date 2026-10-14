"""ws_catalog offer --all --setup: the choices of setup.sh (helpws setup)
and the start of ws apply (apply_offer)."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))

import ws_catalog  # noqa: E402
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
# distrobox/catalog.toml as setup reads it without Nix.
BOXES = '''[[boxes]]
name = "arch"
image = "x"

[[boxes]]
name = "t2bce-build"
default = "no"
image = "y"
'''


class FakeTerm:
    def __init__(self):
        self.text = ''

    def write(self, text):
        self.text += text


class SetupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        (self.repo / 'flatpak').mkdir()
        (self.repo / 'distrobox').mkdir()
        (self.repo / 'flatpak/catalog.toml').write_text(CATALOG)
        (self.repo / 'distrobox/catalog.toml').write_text(BOXES)
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
            return ws_catalog.setup(self.repo, 'new', FakeTerm())

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
        (self.repo / 'nix/hosts/new/host.toml').write_text('[layers]\nnativeSteam = true\n')
        self.run_with([[], [], []])
        self.assertNotIn('com.valvesoftware.Steam', self.asked[0][1])
        self.assertIn('com.valvesoftware.Steam', self.read('flatpak.toml')['no'])
        # The flatpak elsewhere: offered as before.
        (self.repo / 'nix/hosts/new/host.toml').write_text('[layers]\nnativeSteam = false\n')
        (self.repo / 'nix/hosts/new/flatpak.toml').write_text('')
        self.asked.clear()
        self.run_with([[], [], []])
        self.assertIn('com.valvesoftware.Steam', self.asked[0][1])

    def test_widgets_some_host_has_are_offered_on_a_widget_host(self):
        (self.repo / 'nix/hosts/mbp16/widgets.toml').write_text('yes = ["example", "compact"]\n')
        (self.repo / 'nix/hosts/new/host.toml').write_text('[layers]\nwidgets = true\n')
        (self.repo / 'nix/hosts/new/widgets.toml').write_text('# mine\nno = ["compact"]\n')
        changed = self.run_with([[], [], ['example'], []])
        self.assertEqual(self.asked[2], ('Виджеты (ws widgets) на new', {'example': True}))
        self.assertIn('nix/hosts/new/widgets.toml', changed)
        text = (self.repo / 'nix/hosts/new/widgets.toml').read_text()
        self.assertTrue(text.startswith('# mine\n'), text)
        self.assertIn('yes = ["example"]', text)

    def test_box_catalog_of_the_repository(self):
        self.assertEqual(ws_catalog.box_catalog(ROOT), [
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


class ApplyOfferTests(unittest.TestCase):
    """apply_offer: what ws apply asks before its steps."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.config = root / 'config'
        (self.config / 'flatpak').mkdir(parents=True)
        (self.config / 'flatpak/catalog.toml').write_text(CATALOG)
        (self.config / 'nix/hosts/new').mkdir(parents=True)
        (self.config / 'nix/hosts/new/host.toml').write_text('[layers]\nwidgets = true\n')
        boxes = root / 'distrobox'
        boxes.mkdir()
        (boxes / 'boxes.json').write_text(json.dumps([{'name': 'arch'}, {'name': 't2', 'default': 'no'}]))
        home = root / 'home/.local/share/workstation/widgets'
        home.mkdir(parents=True)
        (home / 'catalog.json').write_text(json.dumps([{'id': 'clock', 'label': 'Clock'}]))
        patches = [mock.patch.object(ws_catalog.ws_common, 'CONFIG', self.config),
                   mock.patch.dict(os.environ, {'WSBOX_CONFIG': str(boxes), 'HOME': str(root / 'home')}),
                   mock.patch.object(Path, 'home', lambda: root / 'home')]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.asked = []

    def choose(self, answers):
        replies = iter(answers)

        def choose(offered, what, unchecked, tty):
            self.asked.append((what, [n for n, _ in offered], list(unchecked)))
            return next(replies)
        return mock.patch.object(ws_select, 'choose', choose)

    def test_asks_each_module_about_its_ask_positions(self):
        err = io.StringIO()
        with self.choose([['org.example.Asked'], None, ['clock']]):
            written = ws_catalog.apply_offer('new', ['flatpak', 'boxes', 'widgets'], err=err)
        self.assertEqual(self.asked, [
            ('приложения Flatpak', ['org.example.Asked', 'org.example.Mine'], []),
            ('контейнеры Distrobox', ['arch'], []),
            ('виджеты wswidgets', ['clock'], [])])
        # The cancel of the boxes left them ask; the rest was written.
        self.assertIn('выбор отменён, контейнеры Distrobox не тронуты', err.getvalue())
        self.assertEqual([Path(p).name for p in written], ['flatpak.toml', 'widgets.toml'])
        flatpak = ws_catalog.Choice('flatpak', 'new', self.config)
        self.assertEqual((flatpak.yes(), flatpak.no()), (['org.example.Asked'], ['org.example.Mine']))
        self.assertFalse((self.config / 'nix/hosts/new/boxes.toml').exists())

    def test_without_a_terminal_names_the_positions(self):
        err = io.StringIO()
        with mock.patch.object(ws_select, 'open_tty', return_value=None):
            self.assertEqual(ws_catalog.apply_offer('new', ['boxes'], err=err), [])
        self.assertIn('no terminal to ask): arch;', err.getvalue())

    def test_select_offers_the_declined(self):
        with self.choose([[]]):
            ws_catalog.apply_offer('new', ['boxes'], select=True)
        self.assertEqual(self.asked, [('контейнеры Distrobox', ['arch', 't2'], ['t2'])])


if __name__ == '__main__':
    unittest.main()
