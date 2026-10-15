"""The commands of ws are named alike everywhere (ws help plan-v2, 11.4):
the dispatch of bin/ws, its usage and the module table; the fish completion
is made from the usage (tests/test_ws_complete.py)."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WS = (ROOT / "bin/ws").read_text()
# Plumbing of other commands and the fish completion, no usage of its own.
INTERNAL = {"data-files", "unpublished", "modules", "steps", "switch"}


def dispatch():
    """The words of the last case of bin/ws (the command dispatch)."""
    block = WS[WS.rindex('case "${1:-}" in'):]
    block = block[:block.index("\nesac")]
    words = set()
    for alts in re.findall(r"^    ([a-z][a-z|-]*)\)", block, re.M):
        words.update(alts.split("|"))
    return words


def usage():
    text = WS[WS.index("usage() {"):]
    text = text[:text.index("\nUSAGE")]
    commands = set()
    for alts in re.findall(r"^  ws ([a-z|]+)", text, re.M):
        commands.update(alts.split("|"))
    return commands


def modules():
    table = re.search(r"^modules=\(\n(.*?)^\)", WS, re.M | re.S).group(1)
    return dict(re.findall(r'^\s+"(\S+) (\S+)"', table, re.M))


class WsCommandTests(unittest.TestCase):
    def test_usage_names_every_command_and_module(self):
        self.assertEqual(usage(), dispatch() - INTERNAL | set(modules()))

    def test_owners_exist(self):
        for name, owner in modules().items():
            self.assertTrue((ROOT / "libexec" / owner).is_file(), f"{name}: libexec/{owner}")


class WsScriptCommandTests(unittest.TestCase):
    def test_usage_names_every_command(self):
        text = (ROOT / "libexec/wsscript").read_text()
        table = re.search(r"^COMMANDS = \{\n(.*?)^\}", text, re.M | re.S).group(1)
        commands = set(re.findall(r'^    "([a-z]+)":', table, re.M))
        usage_text = re.search(r'^USAGE = """(.*?)"""', text, re.M | re.S).group(1)
        in_usage = set(re.findall(r"^  ws script ([a-z]+)", usage_text, re.M))
        # names: for the completion itself.
        self.assertEqual(in_usage, commands - {"names"})


if __name__ == "__main__":
    unittest.main()
