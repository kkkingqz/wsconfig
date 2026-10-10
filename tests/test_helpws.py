"""bin/helpws: every page has a topic, every `helpws TOPIC` in the
repository opens one, the fish completion knows the same topics."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPLETION = ROOT / "terminal/fish/completions/helpws.fish"


def case_labels():
    """TOPIC -> page title (None for readme, man, help): the case in bin/helpws."""
    text = (ROOT / "bin/helpws").read_text()
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
        # "helpws wo<Tab>", "helpws history-…": examples, not topics.
        ref = re.compile(r"\bhelpws ([a-z][a-z0-9-]*[a-z0-9])(?![a-z0-9<…*-])")
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
                    unknown.add(f"{path.relative_to(ROOT)}: helpws {m[1]}")
        self.assertEqual(sorted(unknown), [])

    def test_fish_completion_has_the_same_topics(self):
        text = COMPLETION.read_text()
        listed = set(re.search(r"^set -l helpws_topics (.*)$", text, re.M)[1].split())
        labels = {n for n in case_labels() if not n.startswith("-")}
        self.assertEqual(sorted(labels ^ listed), [])
        offered = set(re.findall(r"^__helpws_topic (\S+) ", text, re.M))
        self.assertEqual(sorted(offered - labels), [])
        # Every page is offered under one of its names.
        pages = {t for n, t in case_labels().items() if n in offered and t}
        self.assertEqual(sorted({t for t in case_labels().values() if t} - pages), [])


if __name__ == "__main__":
    unittest.main()
