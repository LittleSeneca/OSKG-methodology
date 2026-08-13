"""Local library matching and the acquisition hook.

Matching is deliberately conservative. A false positive here attributes claims
to a work nobody read — the same class of failure the density gates exist to
catch, but harder to spot because the provenance record would look correct.
"""

import os
import stat
import tempfile
import unittest
from pathlib import Path

from oskg.library import index_library, match_sources, run_fetch_command


def make_library(files) -> Path:
    root = Path(tempfile.mkdtemp())
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")
    return root


SOURCES = [
    {"slug": "jones-2017", "title": "A Portable Cosmos: Revealing the Antikythera Mechanism",
     "author": "Jones, Alexander", "year": 2017},
    {"slug": "freeth-2006", "title": "Decoding the ancient Greek astronomical calculator",
     "author": "Freeth, Tony", "year": 2006},
]


class TestIndexing(unittest.TestCase):
    def test_finds_readable_formats_recursively(self):
        root = make_library(["a/book.pdf", "b/c/paper.epub", "notes.txt", "cover.jpg", "data.sqlite"])
        found = {p.name for p in index_library([root])}
        self.assertEqual(found, {"book.pdf", "paper.epub", "notes.txt"})

    def test_missing_directory_is_not_an_error(self):
        self.assertEqual(index_library(["/nonexistent/library"]), [])

    def test_respects_the_file_cap(self):
        root = make_library([f"f{i}.pdf" for i in range(30)])
        self.assertEqual(len(index_library([root], max_files=10)), 10)

    def test_multiple_roots_deduplicate(self):
        root = make_library(["one.pdf"])
        self.assertEqual(len(index_library([root, root])), 1)


class TestMatching(unittest.TestCase):
    def test_matches_on_title_plus_author(self):
        root = make_library(["Jones - A Portable Cosmos.pdf"])
        matches = match_sources(SOURCES, index_library([root]))
        self.assertIn("jones-2017", matches)
        self.assertIn("author", matches["jones-2017"][0].reason)

    def test_matches_on_title_plus_year(self):
        root = make_library(["Portable Cosmos Antikythera 2017.epub"])
        self.assertIn("jones-2017", match_sources(SOURCES, index_library([root])))

    def test_matches_on_the_slug_itself(self):
        root = make_library(["freeth-2006.txt"])
        matches = match_sources(SOURCES, index_library([root]))
        self.assertIn("freeth-2006", matches)

    def test_title_overlap_alone_is_not_enough(self):
        # Every paper in this corpus shares "antikythera"; matching on that
        # would attach the wrong book to almost every source.
        root = make_library(["Some Other Antikythera Book.pdf"])
        self.assertEqual(match_sources(SOURCES, index_library([root])), {})

    def test_generic_title_words_do_not_match(self):
        root = make_library(["A Guide To The Modern History Of Everything.pdf"])
        self.assertEqual(match_sources(SOURCES, index_library([root])), {})

    def test_a_wrong_author_does_not_match(self):
        root = make_library(["Smith - A Portable Cosmos Of Something Else 1999.pdf"])
        matches = match_sources(SOURCES, index_library([root]))
        self.assertNotIn("freeth-2006", matches)

    def test_the_parent_directory_counts_as_context(self):
        # Libraries are often organised author/title/file.
        root = make_library(["Jones Alexander 2017/portable cosmos antikythera.pdf"])
        self.assertIn("jones-2017", match_sources(SOURCES, index_library([root])))

    def test_results_are_capped_and_ordered_by_score(self):
        root = make_library([f"Jones - A Portable Cosmos Antikythera 2017 copy{i}.pdf" for i in range(9)])
        matches = match_sources(SOURCES, index_library([root]))
        scores = [m.score for m in matches["jones-2017"]]
        self.assertLessEqual(len(scores), 4)
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestFetchCommand(unittest.TestCase):
    def _script(self, body: str) -> str:
        path = Path(tempfile.mkdtemp()) / "fetch.sh"
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return str(path)

    def test_a_command_that_produces_a_file_succeeds(self):
        script = self._script('printf "text" > "$1"\n')
        out = Path(tempfile.mkdtemp())
        ok, detail = run_fetch_command(f"{script} {{out}}", {"slug": "s1"}, out)
        self.assertTrue(ok, detail)
        self.assertTrue((out / "s1.txt").exists())

    def test_a_command_that_produces_nothing_fails_cleanly(self):
        ok, detail = run_fetch_command(self._script("exit 3\n"), {"slug": "s1"}, Path(tempfile.mkdtemp()))
        self.assertFalse(ok)
        self.assertIn("exit 3", detail)

    def test_a_missing_command_is_reported_not_raised(self):
        ok, detail = run_fetch_command("/nonexistent/tool {out}", {"slug": "s1"}, Path(tempfile.mkdtemp()))
        self.assertFalse(ok)
        self.assertIn("not found", detail)

    def test_fields_are_substituted(self):
        script = self._script('printf "%s" "$1" > "$2"\n')
        out = Path(tempfile.mkdtemp())
        ok, _ = run_fetch_command(
            f"{script} {{title}} {{out}}", {"slug": "s1", "title": "A Portable Cosmos"}, out
        )
        self.assertTrue(ok)
        self.assertEqual((out / "s1.txt").read_text(), "A Portable Cosmos")

    def test_shell_metacharacters_in_a_title_cannot_execute(self):
        # Argument vector, never a shell: a title is data, not a command.
        script = self._script('printf "%s" "$1" > "$2"\n')
        out = Path(tempfile.mkdtemp())
        hostile = "; touch /tmp/oskg-pwned-marker; echo"
        ok, _ = run_fetch_command(
            f"{script} {{title}} {{out}}", {"slug": "s1", "title": hostile}, out
        )
        self.assertTrue(ok)
        self.assertEqual((out / "s1.txt").read_text(), hostile)
        self.assertFalse(Path("/tmp/oskg-pwned-marker").exists())

    def test_a_bad_template_is_reported(self):
        ok, detail = run_fetch_command("tool {nosuchfield}", {"slug": "s1"}, Path(tempfile.mkdtemp()))
        self.assertFalse(ok)
        self.assertIn("template", detail)

    def test_an_empty_template_is_reported(self):
        ok, detail = run_fetch_command("   ", {"slug": "s1"}, Path(tempfile.mkdtemp()))
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
