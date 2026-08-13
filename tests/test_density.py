"""Extraction density — the check a quality audit of a real build produced.

The build acquired Jones 2017 as `partial` and got a 1,682-word book review
instead of the book. Provenance was recorded honestly — the stub said so, and
every claim's locator cited the review, not invented book pages. But extraction
drew 37 claims from it, 22 per 1,000 words against 0.6-0.8 for the full papers,
making the thinnest and most second-hand text the graph's largest single
contributor at 34% of all claims.

Nothing was fabricated. The problem was weight, and no existing gate could see
it, because every individual claim was well-formed.
"""

import tempfile
import unittest
from pathlib import Path

from oskg.gates import WARN, run_gate

from .fixtures import make_claim, make_note, make_project


def findings(report, check: str):
    return [f for f in report.findings if f.check == check]


def write_source_text(root: Path, slug: str, words: int, kind: str = "papers") -> None:
    path = root / "sources" / kind / "_txt" / f"{slug}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(" ".join(["word"] * words), encoding="utf-8")


def populate(root, manifest, spec):
    """spec: {slug: (source_words, claim_count)}"""
    make_note(root, "Note One")
    for slug, (words, count) in spec.items():
        write_source_text(root, slug, words)
        for i in range(count):
            make_claim(root, f"{slug}-c{i}", source=slug, note="Note One", n=i)


class TestOverExtraction(unittest.TestCase):
    def test_a_thin_source_yielding_many_claims_is_flagged(self):
        root, manifest = make_project(tempfile.mkdtemp())
        populate(root, manifest, {
            "s1": (30_000, 25),   # 0.8 per 1k — a full paper
            "s2": (28_000, 16),   # 0.6 per 1k — a full paper
            "s3": (4_800, 27),    # 5.6 per 1k — a short paper, dense but plausible
            "review": (1_700, 37),  # 21.8 per 1k — the review masquerading as a book
        })
        hits = findings(run_gate(root, 2, manifest), "OVER_EXTRACTED")
        self.assertEqual([f.path for f in hits], ["source/review"])
        self.assertIn("review, abstract, or summary", hits[0].detail)

    def test_an_even_corpus_is_not_flagged(self):
        root, manifest = make_project(tempfile.mkdtemp())
        populate(root, manifest, {"a": (10_000, 10), "b": (12_000, 11), "c": (9_000, 8)})
        self.assertEqual(findings(run_gate(root, 2, manifest), "OVER_EXTRACTED"), [])

    def test_the_median_is_a_true_median(self):
        # On an even count, taking the upper-middle skews toward the outlier and
        # let the real 22-per-1k case slip past a 4x threshold.
        root, manifest = make_project(tempfile.mkdtemp())
        populate(root, manifest, {
            "a": (30_000, 24), "b": (28_000, 17), "c": (4_800, 27), "d": (1_700, 37),
        })
        self.assertTrue(findings(run_gate(root, 2, manifest), "OVER_EXTRACTED"))

    def test_a_source_with_no_text_on_disk_is_skipped(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        for i in range(5):
            make_claim(root, f"ghost-{i}", source="ghost", note="Note One", n=i)
        self.assertEqual(findings(run_gate(root, 2, manifest), "OVER_EXTRACTED"), [])

    def test_a_single_source_corpus_has_no_baseline(self):
        root, manifest = make_project(tempfile.mkdtemp())
        populate(root, manifest, {"only": (1_000, 40)})
        self.assertEqual(findings(run_gate(root, 2, manifest), "OVER_EXTRACTED"), [])


class TestSecondhandWeight(unittest.TestCase):
    def test_a_partial_source_dominating_the_graph_is_flagged(self):
        # `partial` means the work itself was not obtained. Such a source
        # outvoting fully-read ones is the finding, even when every individual
        # claim is honest about where it came from.
        root, manifest = make_project(tempfile.mkdtemp())
        (root / "SOURCE-GUIDE.md").write_text(
            "## Tier 1 — Canon\n\n"
            "| slug | title | author | year | tier | role | status |\n"
            "|---|---|---|---|---|---|---|\n"
            "| s1 | Full Paper | A | 2020 | 1 | canon | acquired |\n"
            "| s2 | A Book We Could Not Get | B | 2017 | 1 | context | partial |\n",
            encoding="utf-8",
        )
        populate(root, manifest, {"s1": (30_000, 20), "s2": (12_000, 30)})
        hits = findings(run_gate(root, 2, manifest), "SECONDHAND_WEIGHT")
        self.assertEqual([f.path for f in hits], ["source/s2"])
        self.assertIn("60%", hits[0].detail)

    def test_a_small_partial_contribution_is_fine(self):
        root, manifest = make_project(tempfile.mkdtemp())
        (root / "SOURCE-GUIDE.md").write_text(
            "## Tier 1 — Canon\n\n"
            "| slug | title | author | year | tier | role | status |\n"
            "|---|---|---|---|---|---|---|\n"
            "| s1 | Full Paper | A | 2020 | 1 | canon | acquired |\n"
            "| s2 | Partial | B | 2017 | 1 | context | partial |\n",
            encoding="utf-8",
        )
        populate(root, manifest, {"s1": (30_000, 40), "s2": (12_000, 5)})
        self.assertEqual(findings(run_gate(root, 2, manifest), "SECONDHAND_WEIGHT"), [])

    def test_a_fully_acquired_source_is_never_flagged_as_secondhand(self):
        root, manifest = make_project(tempfile.mkdtemp())
        populate(root, manifest, {"s1": (30_000, 10), "s2": (30_000, 40)})
        self.assertEqual(findings(run_gate(root, 2, manifest), "SECONDHAND_WEIGHT"), [])


class TestSeverity(unittest.TestCase):
    def test_both_are_warnings_not_failures(self):
        # They need a human eye on the corpus, not an automatic repair pass —
        # nothing in the claim files is malformed.
        root, manifest = make_project(tempfile.mkdtemp())
        populate(root, manifest, {"a": (30_000, 20), "b": (1_500, 40)})
        report = run_gate(root, 2, manifest)
        for check in ("OVER_EXTRACTED", "SECONDHAND_WEIGHT"):
            for f in findings(report, check):
                self.assertEqual(f.severity, WARN)


if __name__ == "__main__":
    unittest.main()
