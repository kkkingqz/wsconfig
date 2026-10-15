"""libexec/helpws (ws help): every page has a topic, every `ws help TOPIC`
in the repository opens one (and `helpws TOPIC` of docs/history, written
before helpws plan-v2, 5.6), the completion of ws offers every page
(lib/ws_complete.py)."""
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def case_labels():
    """TOPIC -> page title (None for readme, man, help): the case in libexec/helpws."""
    text = (ROOT / "libexec/helpws").read_text()
    body = text[text.index('case "$topic" in'):]
    body = body[:body.index("\nesac")]
    labels = {}
    for m in re.finditer(r"^    ([a-z0-9|-]+)\)(.*)$", body, re.M):
        title = re.search(r"open_title (\S+) ;;", m[2])
        for name in m[1].split("|"):
            labels[name] = title[1] if title else None
    return labels


def doc_titles():
    titles = set()
    for path in (ROOT / "docs").rglob("*.md"):
        m = re.search(r"^title: (\S+)$", path.read_text(), re.M)
        if m:
            titles.add(m[1])
    return titles


def tracked_files():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    return [ROOT / p for p in out.decode().split("\0") if p]


class HelpwsTests(unittest.TestCase):
    def test_every_page_has_a_topic(self):
        opened = {t for t in case_labels().values() if t}
        self.assertEqual(sorted(doc_titles() - opened), [])

    def test_every_topic_opens_a_page(self):
        missing = {n: t for n, t in case_labels().items() if t and t not in doc_titles()}
        self.assertEqual(missing, {})

    def test_references_in_the_repository_resolve(self):
        labels = case_labels()
        # "ws help wo<Tab>", "ws help history-…": examples, not topics.
        # Wrapped at the end of a line (also of a comment) too; a command on
        # the next line is no topic.
        ref = re.compile(r"\b(?:helpws|ws\s+help)(?:[ \t]+|[ \t]*\n[ \t]*(?:#[ \t]*)?)"
                         r"(?!ws\b)([a-z][a-z0-9-]*[a-z0-9])(?![a-z0-9<…*-])")
        unknown = set()
        for path in tracked_files():
            if path.suffix in {".wav", ".png", ".lock"} or not path.is_file():
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for m in ref.finditer(text):
                if m[1] not in labels:
                    unknown.add(f"{path.relative_to(ROOT)}: {m[0]}")
        self.assertEqual(sorted(unknown), [])

    def test_no_topic_is_the_list(self):
        p = subprocess.run([str(ROOT / "bin/ws"), "help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.startswith("Usage:\n  ws help [TOPIC]"), p.stdout[:80])
        p = subprocess.run([str(ROOT / "bin/ws"), "help", "nosuch"], capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stderr), (2, "Unknown topic: nosuch\nRun: ws help\n"))

    def test_completion_offers_every_page(self):
        sys.path.insert(0, str(ROOT / "lib"))
        import ws_complete
        spec = ws_complete.build(ROOT)
        offered = {n for n, _ in spec["topics"]}
        labels = case_labels()
        self.assertEqual(sorted(offered - set(labels)), [])
        pages = {labels[n] for n in offered if labels[n]}
        self.assertEqual(sorted({t for t in labels.values() if t} - pages), [])


if __name__ == "__main__":
    unittest.main()
