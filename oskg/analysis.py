"""Phase 4 — five structural analyses, computed from the graph. No model calls.

This is where the method earns its keep. The synthesis is not a summary an LLM
wrote from impressions; it is a computed result an LLM is later asked to write
up. Every number in a capstone traces back to this module, and `oskg analyze`
recomputes all of it in well under a second for a few thousand claims.

Free, in both senses: no tokens, and no judgment smuggled in.

    1. Hinge inventory        — which claims are load-bearing
    2. Cascade trees          — what collapses if a hinge falls
    3. Convergence points     — where independent sources agree, uncontested
    4. Contradiction clusters — where they genuinely conflict, and who is on each side
    5. Structural gaps        — isolation, single-source topics, bridges, orphans
"""

from __future__ import annotations

import datetime as _dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .graph import Graph

__all__ = ["analyze", "write_analysis", "AnalysisConfig"]

# A claim is "confidently held" from medium-high up. Contradictions below that
# are noise: every corpus contains a low-confidence aside that disagrees with
# something, and treating those as fault lines buries the real ones.
CONFIDENT = 4  # index of "medium-high" in CONFIDENCE_LEVELS


class AnalysisConfig:
    top_hinges = 25
    cascade_roots = 5
    cascade_depth = 4
    convergence_min_supports = 3
    convergence_min_sources = 2
    small_component_max = 3
    sparse_topic_max = 2


def analyze(graph: Graph, config: AnalysisConfig | None = None) -> dict[str, Any]:
    """Run all five analyses. Returns the JSON-serialisable result."""
    cfg = config or AnalysisConfig()
    hinges = hinge_inventory(graph, cfg)
    return {
        "generated": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": graph.metrics(),
        "hinges": hinges,
        "cascades": cascade_trees(graph, hinges, cfg),
        "convergence": convergence_points(graph, cfg),
        "contradictions": contradiction_clusters(graph, cfg),
        "gaps": structural_gaps(graph, cfg),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Hinge inventory
# ─────────────────────────────────────────────────────────────────────────────


def hinge_inventory(graph: Graph, cfg: AnalysisConfig | None = None) -> list[dict[str, Any]]:
    """Rank claims by how much of the graph rests on them.

    Score is the size of the transitive collapse set — every claim that loses
    its footing if this one is false. Ties break on direct inbound collapse
    edges, so a claim carrying ten things directly outranks one carrying ten
    things four levels down.
    """
    cfg = cfg or AnalysisConfig()
    rows: list[dict[str, Any]] = []
    for slug, claim in graph.active_claims.items():
        collapse = graph.collapse_set(slug)
        if not collapse:
            continue
        contradicted = graph.in_edges(slug, ["contradicts"]) + graph.out_edges(slug, ["contradicts"])
        rows.append(
            {
                "slug": slug,
                "statement": claim.statement,
                "source": claim.source,
                "confidence": claim.confidence,
                "claim_type": claim.claim_type,
                "dependents": len(collapse),
                "direct_dependents": sum(1 for d in collapse.values() if d == 1),
                "max_depth": max(collapse.values()),
                "in_degree": len(graph.in_edges(slug)),
                "out_degree": len(graph.out_edges(slug)),
                "contested": len(contradicted) > 0,
                "cross_source_dependents": len(
                    {graph.claims[d].source for d in collapse if graph.claims[d].source != claim.source}
                ),
            }
        )
    rows.sort(key=lambda r: (-r["dependents"], -r["direct_dependents"], r["slug"]))
    for i, row in enumerate(rows[: cfg.top_hinges], start=1):
        row["rank"] = i
    return rows[: cfg.top_hinges]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cascade trees
# ─────────────────────────────────────────────────────────────────────────────


def cascade_trees(
    graph: Graph, hinges: list[dict[str, Any]], cfg: AnalysisConfig | None = None
) -> list[dict[str, Any]]:
    """Full collapse radius for the top hinges, level by level.

    `critical_children` is the payload: claims deep in a dependency chain that
    are *also* directly contradicted. Those are where the graph is both
    load-bearing and actively disputed.
    """
    cfg = cfg or AnalysisConfig()
    out: list[dict[str, Any]] = []
    for hinge in hinges[: cfg.cascade_roots]:
        tree = graph.cascade_tree(hinge["slug"], cfg.cascade_depth)
        critical = [
            node
            for level in tree["levels"]
            for node in level
            if node["contested"]
        ]
        out.append(
            {
                "root": hinge["slug"],
                "statement": hinge["statement"],
                "total_dependents": tree["total"],
                "depth_reached": len(tree["levels"]),
                "levels": [
                    {"level": i + 1, "count": len(level), "nodes": level}
                    for i, level in enumerate(tree["levels"])
                ],
                "critical_children": critical,
            }
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 3. Convergence points
# ─────────────────────────────────────────────────────────────────────────────


def convergence_points(graph: Graph, cfg: AnalysisConfig | None = None) -> list[dict[str, Any]]:
    """Claims that several independent sources support and nobody confidently disputes.

    The independence check is what makes this meaningful: three supports from
    one source is one source repeating itself, not convergence.
    """
    cfg = cfg or AnalysisConfig()
    out: list[dict[str, Any]] = []
    for slug, claim in graph.active_claims.items():
        supports = graph.in_edges(slug, ["supports"])
        if len(supports) < cfg.convergence_min_supports:
            continue
        supporting_sources = {
            graph.claims[e.source].source for e in supports if graph.claims[e.source].source
        }
        if len(supporting_sources) < cfg.convergence_min_sources:
            continue

        contradictions = graph.in_edges(slug, ["contradicts"]) + graph.out_edges(slug, ["contradicts"])
        live = [
            e
            for e in contradictions
            if max(
                graph.claims[e.source].confidence_value,
                graph.claims[e.target].confidence_value,
            )
            >= CONFIDENT
        ]
        if live:
            continue

        out.append(
            {
                "slug": slug,
                "statement": claim.statement,
                "confidence": claim.confidence,
                "support_count": len(supports),
                "supporting_sources": sorted(supporting_sources),
                "source_count": len(supporting_sources),
                "weak_contradictions": len(contradictions),
                "supporters": [
                    {
                        "slug": e.source,
                        "source": graph.claims[e.source].source,
                        "confidence": graph.claims[e.source].confidence,
                    }
                    for e in supports
                ],
            }
        )
    out.sort(key=lambda r: (-r["source_count"], -r["support_count"], r["slug"]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 4. Contradiction clusters
# ─────────────────────────────────────────────────────────────────────────────


def contradiction_clusters(graph: Graph, cfg: AnalysisConfig | None = None) -> list[dict[str, Any]]:
    """Connected components of the `contradicts` subgraph — the fault lines.

    A cluster where both sides are held confidently is a `genuine_unknown`: the
    graph records the disagreement and declines to resolve it. That distinction
    is the honest output, and it is the reason the capstone can say "contested"
    without implying the better-connected camp is right.
    """
    cfg = cfg or AnalysisConfig()
    contradiction_edges = [e for e in graph.edges if e.type == "contradicts"]
    if not contradiction_edges:
        return []

    adjacency: dict[str, set[str]] = defaultdict(set)
    for e in contradiction_edges:
        adjacency[e.source].add(e.target)
        adjacency[e.target].add(e.source)

    seen: set[str] = set()
    clusters: list[dict[str, Any]] = []
    for slug in sorted(adjacency):
        if slug in seen:
            continue
        members: list[str] = []
        stack = [slug]
        seen.add(slug)
        while stack:
            node = stack.pop()
            members.append(node)
            for neighbour in adjacency[node]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        members.sort()

        by_source: dict[str, list[str]] = defaultdict(list)
        for m in members:
            by_source[graph.claims[m].source or "(unattributed)"].append(m)

        confident = [m for m in members if graph.claims[m].confidence_value >= CONFIDENT]
        pairs = [
            {
                "a": e.source,
                "b": e.target,
                "a_confidence": graph.claims[e.source].confidence,
                "b_confidence": graph.claims[e.target].confidence,
                "justification": e.justification,
                "both_confident": (
                    graph.claims[e.source].confidence_value >= CONFIDENT
                    and graph.claims[e.target].confidence_value >= CONFIDENT
                ),
            }
            for e in contradiction_edges
            if e.source in set(members) and e.source < e.target
        ]

        clusters.append(
            {
                "members": members,
                "size": len(members),
                "camps": {src: sorted(slugs) for src, slugs in sorted(by_source.items())},
                "camp_count": len(by_source),
                "confident_members": len(confident),
                "genuine_unknown": any(p["both_confident"] for p in pairs),
                "topics": sorted({t for m in members for t in graph.claims[m].topics}),
                "pairs": pairs,
                "statements": {m: graph.claims[m].statement for m in members},
            }
        )
    clusters.sort(key=lambda c: (-c["size"], -c["camp_count"]))
    return clusters


# ─────────────────────────────────────────────────────────────────────────────
# 5. Structural gaps
# ─────────────────────────────────────────────────────────────────────────────


def structural_gaps(graph: Graph, cfg: AnalysisConfig | None = None) -> dict[str, Any]:
    """Where the graph is thin, and what that thinness means.

    Reads as a to-do list for the next build: an isolated component is usually
    a vocabulary mismatch Phase 3 could not bridge, and a single-source topic is
    a claim nobody has corroborated.
    """
    cfg = cfg or AnalysisConfig()
    components = graph.components()
    topics = graph.topics()

    single_source_topics = []
    sparse_topics = []
    for topic, slugs in sorted(topics.items()):
        sources = {graph.claims[s].source for s in slugs if graph.claims[s].source}
        if len(slugs) <= cfg.sparse_topic_max:
            sparse_topics.append({"topic": topic, "claims": len(slugs), "slugs": slugs})
        if len(sources) == 1 and len(slugs) > cfg.sparse_topic_max:
            single_source_topics.append(
                {"topic": topic, "source": next(iter(sources)), "claims": len(slugs)}
            )

    # A bridge is the sole cross-source link between two source clusters:
    # remove it and the two bodies of work stop talking to each other.
    bridge_counts: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for e in graph.edges:
        a, b = graph.claims[e.source].source, graph.claims[e.target].source
        if a and b and a != b:
            bridge_counts[tuple(sorted((a, b)))].append(
                {"source": e.source, "target": e.target, "type": e.type}
            )
    bridges = [
        {"sources": list(pair), "edge": edges[0]}
        for pair, edges in sorted(bridge_counts.items())
        if len(edges) == 1
    ]

    source_coverage = defaultdict(int)
    for claim in graph.active_claims.values():
        if claim.source:
            source_coverage[claim.source] += 1

    return {
        "orphans": [
            {"slug": s, "statement": graph.claims[s].statement, "source": graph.claims[s].source}
            for s in graph.orphans()
        ],
        "orphan_count": len(graph.orphans()),
        "components": len(components),
        "largest_component": len(components[0]) if components else 0,
        "isolated_components": [
            {"size": len(c), "members": c, "sources": sorted({graph.claims[m].source for m in c})}
            for c in components
            if 1 < len(c) <= cfg.small_component_max
        ],
        "single_source_topics": single_source_topics,
        "sparse_topics": sparse_topics,
        "fragile_bridges": bridges,
        "source_coverage": dict(sorted(source_coverage.items(), key=lambda kv: -kv[1])),
        "uncontested_sources": sorted(
            src
            for src in graph.sources()
            if not any(
                e.type == "contradicts"
                and (graph.claims[e.source].source == src or graph.claims[e.target].source == src)
                for e in graph.edges
            )
        ),
        "dependency_cycles": graph.find_cycles("depends_on"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────────


def write_analysis(project_dir: Path | str, result: dict[str, Any]) -> Path:
    path = Path(project_dir) / ".oskg" / "analysis.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path


def format_summary(result: dict[str, Any]) -> str:
    """A terminal-readable digest. `oskg analyze` prints this."""
    m = result["metrics"]
    lines = [
        f"Graph: {m['claims']} claims · {m['edges']} edges "
        f"({m['edges_per_claim']}/claim, {int(m['cross_source_ratio'] * 100)}% cross-source) · "
        f"{m['sources']} sources · {m['topics']} topics",
        "",
        "Top hinges (claims the most rests on):",
    ]
    for h in result["hinges"][:8]:
        flag = " ⚠ contested" if h["contested"] else ""
        lines.append(f"  {h['rank']:2}. [{h['dependents']:3}] {h['slug']}{flag}")
        if h["statement"]:
            lines.append(f"       {h['statement'][:96]}")

    conv = result["convergence"]
    lines += ["", f"Convergence points ({len(conv)}):"]
    for c in conv[:6]:
        lines.append(f"  · {c['slug']} — {c['source_count']} sources, {c['support_count']} supports")

    clusters = result["contradictions"]
    unknowns = [c for c in clusters if c["genuine_unknown"]]
    lines += ["", f"Contradiction clusters: {len(clusters)} ({len(unknowns)} genuine unknowns)"]
    for c in clusters[:5]:
        mark = " ⚑ genuine unknown" if c["genuine_unknown"] else ""
        lines.append(f"  · {c['size']} claims across {c['camp_count']} sources{mark}")

    gaps = result["gaps"]
    lines += [
        "",
        "Structural gaps:",
        f"  orphans: {gaps['orphan_count']} · components: {gaps['components']} "
        f"(largest {gaps['largest_component']})",
        f"  single-source topics: {len(gaps['single_source_topics'])} · "
        f"fragile bridges: {len(gaps['fragile_bridges'])}",
    ]
    if gaps["dependency_cycles"]:
        lines.append(f"  ⚠ dependency cycles: {len(gaps['dependency_cycles'])}")
    return "\n".join(lines)
