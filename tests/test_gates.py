"""Quality gates — the checks that catch the defects Obsidian hides."""

import tempfile
import unittest
from pathlib import Path

from oskg.gates import ERROR, FATAL, WARN, parse_source_guide, run_gate

from .fixtures import SOURCE_GUIDE, edge_block, make_claim, make_graph_project, make_note, make_project


def checks(report) -> set[str]:
    return {f.check for f in report.findings}


def checks_of(report, severity) -> set[str]:
    return {f.check for f in report.findings if f.severity == severity}


class TestSourceGuideParsing(unittest.TestCase):
    def test_reads_tiered_tables(self):
        root = Path(tempfile.mkdtemp())
        (root / "SOURCE-GUIDE.md").write_text(SOURCE_GUIDE, encoding="utf-8")
        sources = parse_source_guide(root / "SOURCE-GUIDE.md")
        self.assertEqual(len(sources), 4)
        self.assertEqual({s["slug"] for s in sources}, {"s1", "s2", "s3", "s4"})
        self.assertEqual(next(s for s in sources if s["slug"] == "s1")["tier"], 1)
        self.assertEqual(next(s for s in sources if s["slug"] == "s4")["status"], "pending")

    def test_missing_file_is_empty_not_an_exception(self):
        self.assertEqual(parse_source_guide(Path("/nonexistent/SOURCE-GUIDE.md")), [])


class TestGate0(unittest.TestCase):
    def test_passes_a_scaffolded_project(self):
        root, manifest = make_project(tempfile.mkdtemp())
        self.assertTrue(run_gate(root, 0, manifest).passed)

    def test_no_source_guide_is_fatal(self):
        root, manifest = make_project(tempfile.mkdtemp())
        (root / "SOURCE-GUIDE.md").unlink()
        report = run_gate(root, 0, manifest)
        self.assertIn("NO_CANON", checks_of(report, FATAL))

    def test_a_corpus_without_tier_one_is_fatal(self):
        # No canon means no vocabulary anchor and no shared edge targets.
        root, manifest = make_project(tempfile.mkdtemp())
        (root / "SOURCE-GUIDE.md").write_text(
            "## Tier 2 — Core\n\n| slug | title | author | year | tier | role | status |\n"
            "|---|---|---|---|---|---|---|\n| s2 | T | A | 2020 | 2 | role | acquired |\n",
            encoding="utf-8",
        )
        self.assertIn("NO_CANON", checks_of(run_gate(root, 0, manifest), FATAL))


class TestGate1(unittest.TestCase):
    def test_passes_well_formed_notes(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One", source="s1", tier=1)
        report = run_gate(root, 1, manifest)
        self.assertTrue(report.passed, report.format(verbose=True))

    def test_note_without_candidate_claims_fails(self):
        root, manifest = make_project(tempfile.mkdtemp())
        path = make_note(root, "Note One")
        path.write_text(path.read_text().replace("## Candidate Claims", "## Something Else"), encoding="utf-8")
        self.assertIn("NO_CANDIDATES", checks_of(run_gate(root, 1, manifest), ERROR))

    def test_source_not_in_the_guide_fails(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One", source="not-in-the-guide")
        self.assertIn("UNKNOWN_SOURCE", checks_of(run_gate(root, 1, manifest), ERROR))

    def test_transcript_length_is_a_fatal_copyright_leak(self):
        # Fatal regardless of gates.strict: committing extracted source text is
        # the one failure that cannot be repaired after a push.
        root, manifest = make_project(tempfile.mkdtemp())
        path = make_note(root, "Note One")
        path.write_text(path.read_text() + "\n" + "\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
        self.assertIn("FULLTEXT_LEAK", checks_of(run_gate(root, 1, manifest), FATAL))

    def test_page_markers_are_a_fatal_copyright_leak(self):
        root, manifest = make_project(tempfile.mkdtemp())
        path = make_note(root, "Note One")
        pages = "\n".join(f"[page {i}]\nsome extracted text\n" for i in range(20))
        path.write_text(path.read_text() + "\n" + pages, encoding="utf-8")
        self.assertIn("FULLTEXT_LEAK", checks_of(run_gate(root, 1, manifest), FATAL))


class TestGate2(unittest.TestCase):
    def test_passes_a_well_formed_graph(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        report = run_gate(root, 2, manifest)
        self.assertTrue(report.passed, report.format(verbose=True))

    def test_claim_id_style_wikilink_fails(self):
        # The failure the whole gate suite exists for: Obsidian renders it as a
        # dead link rather than an error, so the vault looks fine and the graph
        # is empty.
        root, manifest = make_graph_project(tempfile.mkdtemp(), broken=True)
        report = run_gate(root, 2, manifest)
        self.assertIn("BROKEN_LINK", checks_of(report, ERROR))
        self.assertFalse(report.passed)

    def test_self_edge_fails(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        make_claim(root, "loop", edges=edge_block(supports=["loop — points at itself"]))
        self.assertIn("SELF_EDGE", checks_of(run_gate(root, 2, manifest), ERROR))

    def test_bad_confidence_and_claim_type_fail(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        make_claim(root, "odd", confidence="extremely-sure", claim_type="not-a-type")
        found = checks_of(run_gate(root, 2, manifest), ERROR)
        self.assertIn("BAD_CONFIDENCE", found)
        self.assertIn("BAD_CLAIM_TYPE", found)

    def test_thin_evidence_warns_without_failing(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        path = make_claim(root, "thin")
        text = path.read_text()
        start = text.index("## Evidence")
        end = text.index("## Confidence")
        path.write_text(text[:start] + "## Evidence\n\nToo short.\n\n" + text[end:], encoding="utf-8")
        report = run_gate(root, 2, manifest)
        self.assertIn("THIN_EVIDENCE", checks_of(report, WARN))
        self.assertTrue(report.passed)  # warnings do not fail a gate

    def test_broken_source_note_fails(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_claim(root, "c", note="A Note That Was Never Written")
        self.assertIn("BROKEN_SOURCE_NOTE", checks_of(run_gate(root, 2, manifest), ERROR))


class TestGate3(unittest.TestCase):
    def test_passes_a_connected_graph(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        report = run_gate(root, 3, manifest)
        self.assertTrue(report.passed, report.format(verbose=True))

    def test_one_sided_contradiction_fails(self):
        root, manifest = make_graph_project(tempfile.mkdtemp(), broken=True)
        self.assertIn("ASYMMETRIC_CONTRADICTION", checks_of(run_gate(root, 3, manifest), ERROR))

    def test_sparse_graph_fails(self):
        root, manifest = make_project(tempfile.mkdtemp())
        for i in range(6):
            make_claim(root, f"lonely-{i}", note="Note One")
        make_note(root, "Note One")
        self.assertIn("SPARSE_GRAPH", checks_of(run_gate(root, 3, manifest), ERROR))

    def test_single_source_corpus_fails_on_isolation(self):
        # Intra-source edges organize one book and connect nothing.
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        make_claim(root, "a", source="s1", edges=edge_block(supports=["b — one reason among several"]))
        make_claim(root, "b", source="s1", edges=edge_block(supports=["c — another distinct reason"]))
        make_claim(root, "c", source="s1", edges=edge_block(supports=["a — closing the triangle here"]))
        self.assertIn("ISOLATED_SOURCES", checks_of(run_gate(root, 3, manifest), ERROR))

    def test_dependency_cycle_fails(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        make_claim(root, "a", source="s1", edges=edge_block(depends_on=["b — a requires b"]))
        make_claim(root, "b", source="s2", edges=edge_block(depends_on=["a — and b requires a"]))
        self.assertIn("DEPENDENCY_CYCLE", checks_of(run_gate(root, 3, manifest), ERROR))

    def test_edge_index_is_regenerated(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        run_gate(root, 3, manifest)
        self.assertTrue((root / ".oskg" / "edges.json").exists())


class TestGates4And5(unittest.TestCase):
    def test_missing_analysis_is_fatal(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.assertIn("NO_ANALYSIS", checks_of(run_gate(root, 4, manifest), FATAL))

    def test_phantom_citation_fails(self):
        import json

        from oskg.analysis import analyze, write_analysis
        from oskg.graph import load_graph

        root, manifest = make_graph_project(tempfile.mkdtemp())
        write_analysis(root, analyze(load_graph(root, manifest.edge_types)))
        (root / "notes" / "synthesis" / "phase1-hinge-inventory.md").write_text(
            "---\ntags:\n  - type/synthesis\n---\n\n# Hinges\n\n"
            "The load-bearing claim is [[hinge]], which rests on [[a-claim-that-does-not-exist]].\n",
            encoding="utf-8",
        )
        self.assertIn("PHANTOM_CITATION", checks_of(run_gate(root, 4, manifest), ERROR))

    def test_missing_capstone_is_fatal(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.assertIn("NO_CAPSTONE", checks_of(run_gate(root, 5, manifest), FATAL))


class TestReporting(unittest.TestCase):
    def test_repair_brief_lists_failures_only(self):
        root, manifest = make_graph_project(tempfile.mkdtemp(), broken=True)
        brief = run_gate(root, 2, manifest).repair_brief()
        self.assertIn("BROKEN_LINK", brief)
        self.assertNotIn("SUSPECTED_SYNONYM", brief)  # a warning, not a failure

    def test_paths_are_project_relative(self):
        root, manifest = make_graph_project(tempfile.mkdtemp(), broken=True)
        for finding in run_gate(root, 2, manifest).findings:
            self.assertFalse(finding.path.startswith("/"), finding.path)

    def test_exit_codes(self):
        clean, _ = make_graph_project(tempfile.mkdtemp())
        broken, manifest = make_graph_project(tempfile.mkdtemp(), broken=True)
        self.assertEqual(run_gate(clean, 2, manifest).exit_code(), 0)
        self.assertEqual(run_gate(broken, 2, manifest).exit_code(), 1)
        self.assertEqual(run_gate(broken, 5, manifest).exit_code(), 2)


if __name__ == "__main__":
    unittest.main()
