"""Phase 3 — Cross-source edge construction.

The clustering is done here, in Python, for free: claims that share a topic tag
are the only pairs worth comparing, and comparing all pairs is quadratic and
mostly wasted. The model is then asked to do the one thing it is actually good
at — judging whether two specific claims are related, and how.

Clusters are filtered to those spanning more than one source. A single-source
cluster produces intra-source edges, which organize one book and connect
nothing; cross-source edges are what the graph is for.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..graph import Graph, load_graph
from .base import Phase, markdown_table

# Cluster sizing. Below the floor there is nothing to connect; above the ceiling
# the pairwise space is too large to judge well in one call, so the cluster is
# split into overlapping chunks.
MIN_CLUSTER = 3
MAX_CLUSTER = 28
CHUNK_OVERLAP = 4


class EdgesPhase(Phase):
    number = 3
    name = "Edge construction"
    stage = "edges"
    batch_size = 1
    specs = ("spec/edge-types.md", "spec/claim-node.md")

    def __init__(self, ctx):
        super().__init__(ctx)
        self._clusters: dict[str, list[str]] = {}
        self._graph: Graph | None = None

    def plan(self) -> list[str]:
        self._graph = load_graph(self.root, self.manifest.edge_types)
        if not self._graph.claims:
            self.log.warn("phase 3: no claims to connect")
            return []

        self._clusters = self._build_clusters(self._graph)
        if not self._clusters:
            self.log.warn(
                "phase 3: no multi-source topic cluster — either the corpus is single-source "
                "or topic tags are too sparse to cluster on"
            )
            return []

        keys = list(self._clusters)
        affordable = self.budget.affordable(3, self.stage)
        if affordable and len(keys) > affordable:
            # Keep the clusters that span the most sources: those are where
            # cross-source edges — the ones that make the graph worth having —
            # are densest.
            keys.sort(key=lambda k: -self._source_count(k))
            dropped = keys[affordable:]
            keys = keys[:affordable]
            self.state.record_trim(
                3, "clusters", f"{len(dropped)} topic clusters not processed", dropped=dropped
            )
        self.log.info(f"phase 3: {len(keys)} cross-source clusters to connect")
        return keys

    # ── clustering ──────────────────────────────────────────────────────
    def _build_clusters(self, graph: Graph) -> dict[str, list[str]]:
        """Topic tag → claim slugs, keeping only multi-source clusters."""
        clusters: dict[str, list[str]] = {}
        for topic, slugs in sorted(graph.topics().items()):
            if len(slugs) < MIN_CLUSTER:
                continue
            sources = {graph.claims[s].source for s in slugs if graph.claims[s].source}
            if len(sources) < 2:
                continue
            ordered = sorted(slugs, key=lambda s: (graph.claims[s].source, s))
            if len(ordered) <= MAX_CLUSTER:
                clusters[topic] = ordered
                continue
            # Overlapping chunks: a claim at a chunk boundary still gets a chance
            # to connect to the claims on the other side of it.
            step = MAX_CLUSTER - CHUNK_OVERLAP
            for i, start in enumerate(range(0, len(ordered), step), start=1):
                chunk = ordered[start : start + MAX_CLUSTER]
                if len(chunk) >= MIN_CLUSTER:
                    clusters[f"{topic}#{i}"] = chunk
        return clusters

    def _source_count(self, key: str) -> int:
        graph = self._graph
        if graph is None:
            return 0
        return len({graph.claims[s].source for s in self._clusters.get(key, []) if s in graph.claims})

    # ── prompt ──────────────────────────────────────────────────────────
    def build_prompt(self, batch: list[str]) -> str:
        key = batch[0]
        if not self._clusters:
            self._graph = load_graph(self.root, self.manifest.edge_types)
            self._clusters = self._build_clusters(self._graph)
        slugs = self._clusters.get(key, [])
        graph = self._graph or load_graph(self.root, self.manifest.edge_types)

        rows: list[dict[str, Any]] = []
        by_source: dict[str, int] = defaultdict(int)
        for slug in slugs:
            claim = graph.claims.get(slug)
            if not claim:
                continue
            by_source[claim.source] += 1
            rows.append(
                {
                    "slug": slug,
                    "source": claim.source,
                    "confidence": claim.confidence,
                    "type": claim.claim_type,
                    "statement": claim.statement[:150],
                    "edges": len(claim.edges),
                }
            )

        return self.render(
            "phase3_edges.md",
            cluster_name=key,
            claim_count=len(rows),
            source_count=len(by_source),
            claim_table=markdown_table(
                rows, ("slug", "source", "confidence", "type", "statement", "edges")
            ),
            target_edges=self._target_edges(len(rows), len(by_source)),
        )

    def _target_edges(self, claims: int, sources: int) -> str:
        """A range, not a number — a quota invites edge spam to fill it."""
        if claims < 6:
            return "2-5"
        low = max(3, claims // 3)
        high = max(low + 3, min(claims, claims // 2 + sources))
        return f"{low}-{high}"

    def on_phase_complete(self, outcome) -> None:
        graph = load_graph(self.root, self.manifest.edge_types)
        graph.write_edge_index(self.root / ".oskg" / "edges.json")
        m = graph.metrics()
        self.log.info(
            f"graph: {m['claims']} claims · {m['edges']} edges "
            f"({m['edges_per_claim']}/claim, {int(m['cross_source_ratio'] * 100)}% cross-source) · "
            f"{m['orphans']} orphans"
        )
