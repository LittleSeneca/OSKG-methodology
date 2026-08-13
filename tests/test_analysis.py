"""The five structural analyses.

The fixture graph has a known shape, so these assert exact numbers rather than
"it returned something" — which is the point of computing the synthesis instead
of writing it.
"""

import tempfile
import unittest

from oskg.analysis import (
    analyze,
    cascade_trees,
    contradiction_clusters,
    convergence_points,
    format_summary,
    hinge_inventory,
    structural_gaps,
    write_analysis,
)
from oskg.graph import load_graph

from .fixtures import edge_block, make_claim, make_graph_project, make_note, make_project


class TestHinges(unittest.TestCase):
    def setUp(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.graph = load_graph(root, manifest.edge_types)

    def test_the_hinge_ranks_first(self):
        hinges = hinge_inventory(self.graph)
        self.assertEqual(hinges[0]["slug"], "hinge")
        self.assertEqual(hinges[0]["dependents"], 3)  # dep-a, dep-b, dep-c
        self.assertEqual(hinges[0]["direct_dependents"], 2)
        self.assertEqual(hinges[0]["rank"], 1)

    def test_claims_nothing_depends_on_are_excluded(self):
        self.assertNotIn("orphan", {h["slug"] for h in hinge_inventory(self.graph)})

    def test_cross_source_dependents_are_counted(self):
        top = hinge_inventory(self.graph)[0]
        self.assertEqual(top["cross_source_dependents"], 2)  # s2 and s3 depend on an s1 claim


class TestCascades(unittest.TestCase):
    def setUp(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.graph = load_graph(root, manifest.edge_types)

    def test_cascade_reports_levels_for_the_top_hinge(self):
        trees = cascade_trees(self.graph, hinge_inventory(self.graph))
        top = trees[0]
        self.assertEqual(top["root"], "hinge")
        self.assertEqual(top["total_dependents"], 3)
        self.assertEqual(top["depth_reached"], 2)
        self.assertEqual(top["levels"][0]["count"], 2)

    def test_no_hinges_yields_no_trees(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_claim(root, "lonely", note="Note One")
        make_note(root, "Note One")
        graph = load_graph(root, manifest.edge_types)
        self.assertEqual(cascade_trees(graph, hinge_inventory(graph)), [])


class TestConvergence(unittest.TestCase):
    def setUp(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.graph = load_graph(root, manifest.edge_types)

    def test_multi_source_support_converges(self):
        points = convergence_points(self.graph)
        hinge = next(p for p in points if p["slug"] == "hinge")
        self.assertEqual(hinge["source_count"], 3)
        self.assertGreaterEqual(hinge["support_count"], 3)

    def test_one_source_repeating_itself_is_not_convergence(self):
        # Three supports from one source is one source, not three.
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        make_claim(root, "target", source="s1")
        for i in range(3):
            make_claim(root, f"echo-{i}", source="s1",
                       edges=edge_block(supports=["target — the same source restating itself"]))
        graph = load_graph(root, manifest.edge_types)
        self.assertEqual(convergence_points(graph), [])

    def test_a_confident_contradiction_disqualifies(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        make_claim(root, "target", source="s1",
                   edges=edge_block(contradicts=["objector — disputes the central reading"]))
        make_claim(root, "objector", source="s4", confidence="high",
                   edges=edge_block(contradicts=["target — disputes the central reading"]))
        for i, src in enumerate(("s1", "s2", "s3")):
            make_claim(root, f"sup-{i}", source=src,
                       edges=edge_block(supports=["target — independent corroboration here"]))
        graph = load_graph(root, manifest.edge_types)
        self.assertNotIn("target", {p["slug"] for p in convergence_points(graph)})


class TestContradictions(unittest.TestCase):
    def setUp(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.graph = load_graph(root, manifest.edge_types)

    def test_reciprocal_pair_forms_one_cluster(self):
        clusters = contradiction_clusters(self.graph)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["members"], ["contra-x", "contra-y"])
        self.assertEqual(clusters[0]["camp_count"], 2)

    def test_two_confident_sides_is_a_genuine_unknown(self):
        # The graph records the disagreement; it does not resolve it.
        self.assertTrue(contradiction_clusters(self.graph)[0]["genuine_unknown"])

    def test_a_low_confidence_side_is_not_a_genuine_unknown(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        make_claim(root, "strong", source="s1", confidence="high",
                   edges=edge_block(contradicts=["weak — disputes the reading"]))
        make_claim(root, "weak", source="s2", confidence="low",
                   edges=edge_block(contradicts=["strong — disputes the reading"]))
        graph = load_graph(root, manifest.edge_types)
        self.assertFalse(contradiction_clusters(graph)[0]["genuine_unknown"])

    def test_no_contradictions_yields_no_clusters(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_claim(root, "solo", note="Note One")
        make_note(root, "Note One")
        self.assertEqual(contradiction_clusters(load_graph(root, manifest.edge_types)), [])


class TestGaps(unittest.TestCase):
    def setUp(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.graph = load_graph(root, manifest.edge_types)

    def test_orphans_are_reported(self):
        gaps = structural_gaps(self.graph)
        self.assertEqual(gaps["orphan_count"], 1)
        self.assertEqual(gaps["orphans"][0]["slug"], "orphan")

    def test_source_coverage_is_reported(self):
        self.assertEqual(set(structural_gaps(self.graph)["source_coverage"]), {"s1", "s2", "s3"})

    def test_single_source_topics_are_flagged(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        for i in range(4):
            make_claim(root, f"solo-{i}", source="s1", topics=("only-one-source-has-this",))
        gaps = structural_gaps(load_graph(root, manifest.edge_types))
        self.assertIn("only-one-source-has-this", {t["topic"] for t in gaps["single_source_topics"]})

    def test_fragile_bridge_is_a_lone_cross_source_link(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_note(root, "Note One")
        make_claim(root, "left", source="s1",
                   edges=edge_block(supports=["right — the only link between these two bodies of work"]))
        make_claim(root, "right", source="s2")
        gaps = structural_gaps(load_graph(root, manifest.edge_types))
        self.assertEqual(len(gaps["fragile_bridges"]), 1)
        self.assertEqual(gaps["fragile_bridges"][0]["sources"], ["s1", "s2"])


class TestFullAnalysis(unittest.TestCase):
    def test_analyze_produces_every_section(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        result = analyze(load_graph(root, manifest.edge_types))
        for key in ("metrics", "hinges", "cascades", "convergence", "contradictions", "gaps"):
            self.assertIn(key, result)

    def test_result_is_json_serialisable(self):
        import json

        root, manifest = make_graph_project(tempfile.mkdtemp())
        result = analyze(load_graph(root, manifest.edge_types))
        json.loads(json.dumps(result))  # would raise on a non-serialisable value

    def test_write_analysis_lands_where_the_gate_looks(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        path = write_analysis(root, analyze(load_graph(root, manifest.edge_types)))
        self.assertEqual(path, root / ".oskg" / "analysis.json")

    def test_summary_names_the_top_hinge(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        summary = format_summary(analyze(load_graph(root, manifest.edge_types)))
        self.assertIn("hinge", summary)
        self.assertIn("genuine unknown", summary)

    def test_empty_graph_does_not_crash(self):
        root, manifest = make_project(tempfile.mkdtemp())
        result = analyze(load_graph(root, manifest.edge_types))
        self.assertEqual(result["hinges"], [])
        self.assertEqual(result["metrics"]["claims"], 0)


if __name__ == "__main__":
    unittest.main()
