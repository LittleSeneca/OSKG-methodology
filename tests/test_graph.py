"""Claim parsing, edge extraction, and graph traversal."""

import tempfile
import unittest

from oskg import frontmatter
from oskg.graph import Graph, load_graph, normalize_edge_label, parse_edges

from .fixtures import edge_block, make_claim, make_graph_project, make_project


class TestEdgeParsing(unittest.TestCase):
    def test_labels_normalize_to_manifest_types(self):
        self.assertEqual(normalize_edge_label("Depends on"), "depends_on")
        self.assertEqual(normalize_edge_label("Challenged by"), "challenged_by")
        self.assertEqual(normalize_edge_label("  Exception To  "), "exception_to")

    def test_parses_targets_and_justifications(self):
        section = (
            "**Supports:**\n"
            "- [[target-one]] — because the airport analogy is the same split\n"
            "\n"
            "**Contradicts:**\n"
            "- [[target-two]] — dates the layer three centuries earlier\n"
        )
        edges = parse_edges(section, "src", ["supports", "contradicts"])
        self.assertEqual({(e.target, e.type) for e in edges},
                         {("target-one", "supports"), ("target-two", "contradicts")})
        self.assertIn("airport analogy", edges[0].justification)

    def test_empty_subheadings_yield_nothing(self):
        self.assertEqual(parse_edges(edge_block(), "src", ["supports"]), [])

    def test_unknown_subheading_is_kept_for_the_gate_to_report(self):
        # Dropping it would make an invented edge type vanish silently.
        edges = parse_edges("**Invented Type:**\n- [[x]] — why\n", "src", ["supports"])
        self.assertEqual(edges[0].type, "invented_type")

    def test_duplicate_edges_collapse(self):
        section = "**Supports:**\n- [[x]] — first reason\n- [[x]] — second reason\n"
        self.assertEqual(len(parse_edges(section, "src", ["supports"])), 1)

    def test_aliases_and_anchors_in_wikilinks_are_stripped(self):
        self.assertEqual(frontmatter.wikilinks("[[slug|Display]] and [[other#heading]]"),
                         ["slug", "other"])


class TestGraphIndex(unittest.TestCase):
    def setUp(self):
        self.root, self.manifest = make_graph_project(tempfile.mkdtemp())
        self.graph = load_graph(self.root, self.manifest.edge_types)

    def test_loads_only_claim_typed_files(self):
        # An "Index" note in notes/claims/ is a listing, not a node.
        (self.root / "notes" / "claims" / "Claims Index.md").write_text(
            "---\ntags:\n  - type/index\n---\n\n# Claims Index\n", encoding="utf-8"
        )
        graph = load_graph(self.root, self.manifest.edge_types)
        self.assertNotIn("Claims Index", graph.claims)

    def test_cross_source_is_computed_not_authored(self):
        by_key = {(e.source, e.target): e for e in self.graph.edges}
        self.assertTrue(by_key[("dep-a", "hinge")].cross_source)  # s2 → s1
        self.assertFalse(by_key[("sup-1", "hinge")].cross_source)  # s1 → s1

    def test_broken_links_are_collected_not_traversed(self):
        root, manifest = make_graph_project(tempfile.mkdtemp(), broken=True)
        graph = load_graph(root, manifest.edge_types)
        self.assertEqual([e.target for e in graph.broken_links], ["s1.4"])
        self.assertNotIn("s1.4", {e.target for e in graph.edges})

    def test_retracted_claims_are_excluded(self):
        make_claim(self.root, "retired", statement="Withdrawn", status="superseded")
        graph = load_graph(self.root, self.manifest.edge_types)
        self.assertIn("retired", graph.claims)
        self.assertNotIn("retired", graph.active_claims)

    def test_orphans(self):
        self.assertEqual(self.graph.orphans(), ["orphan"])

    def test_metrics(self):
        m = self.graph.metrics()
        self.assertEqual(m["claims"], 10)
        self.assertEqual(m["sources"], 3)
        self.assertGreater(m["cross_source_ratio"], 0.5)


class TestTraversal(unittest.TestCase):
    def setUp(self):
        self.root, self.manifest = make_graph_project(tempfile.mkdtemp())
        self.graph = load_graph(self.root, self.manifest.edge_types)

    def test_collapse_set_follows_depends_on_transitively(self):
        self.assertEqual(self.graph.collapse_set("hinge"), {"dep-a": 1, "dep-b": 1, "dep-c": 2})

    def test_collapse_set_ignores_supports(self):
        # Evidence for a false claim does not itself collapse.
        self.assertNotIn("sup-1", self.graph.collapse_set("hinge"))

    def test_cascade_tree_reports_levels(self):
        tree = self.graph.cascade_tree("hinge", max_depth=4)
        self.assertEqual(tree["total"], 3)
        self.assertEqual(len(tree["levels"]), 2)
        self.assertEqual({n["slug"] for n in tree["levels"][0]}, {"dep-a", "dep-b"})

    def test_cascade_depth_is_respected(self):
        self.assertEqual(len(self.graph.cascade_tree("hinge", max_depth=1)["levels"]), 1)

    def test_components(self):
        components = self.graph.components()
        # hinge + dep-a + dep-b + dep-c + sup-1 + sup-2 + sup-3
        self.assertEqual(len(components[0]), 7)
        self.assertIn(["orphan"], components)

    def test_cycles_terminate_and_are_reported(self):
        root, manifest = make_project(tempfile.mkdtemp())
        make_claim(root, "a", edges=edge_block(depends_on=["b — a needs b"]))
        make_claim(root, "b", edges=edge_block(depends_on=["a — and b needs a"]))
        graph = load_graph(root, manifest.edge_types)
        self.assertTrue(graph.find_cycles("depends_on"))
        # The traversal must still terminate over a cyclic graph.
        self.assertEqual(set(graph.collapse_set("a")), {"b"})


class TestSerialisation(unittest.TestCase):
    def test_edge_index_round_trips(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        graph = load_graph(root, manifest.edge_types)
        path = graph.write_edge_index(root / ".oskg" / "edges.json")
        import json

        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["edge_count"], len(graph.edges))

    def test_export_carries_claims_and_edges(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        exported = load_graph(root, manifest.edge_types).export()
        self.assertEqual(len(exported["claims"]), 10)
        self.assertIn("metrics", exported)


if __name__ == "__main__":
    unittest.main()
