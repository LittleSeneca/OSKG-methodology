"""The claim graph: parse `notes/claims/` into nodes and typed edges.

Claim files are the source of truth. `.oskg/edges.json` is derived from them and
regenerated on demand, so a hand edit in Obsidian is never silently discarded —
the gate reports drift instead.

Edges are read out of the `## Edges` section, where each edge type has a bold
subheading (`**Depends on:**`) followed by `- [[slug]] — justification` lines.
Subheading labels map onto manifest edge types by normalisation, so a project
that declares `exception_to` gets `**Exception to:**` parsed for free.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import frontmatter
from .manifest import CONFIDENCE_LEVELS

__all__ = ["Claim", "Edge", "Graph", "load_graph", "COLLAPSE_EDGE_TYPES"]

CONFIDENCE_VALUE = {name: i for i, name in enumerate(CONFIDENCE_LEVELS)}
DEFAULT_CONFIDENCE = "medium"

# Edge types along which falsification propagates. If B is false then anything
# that depends on, extends, operationalizes, or carves an exception out of B has
# nothing left to stand on. `supports` is deliberately absent: evidence for a
# false claim is still whatever it was — it does not collapse with its target.
COLLAPSE_EDGE_TYPES = ("depends_on", "extends", "operationalizes", "exception_to")

# Symmetric types: asserting one direction asserts the other.
SYMMETRIC_EDGE_TYPES = ("contradicts",)

_EDGE_HEADING_RE = re.compile(r"^\s*\*\*(?P<label>[^*]+?)\s*:?\*\*\s*:?\s*$", re.MULTILINE)
_EDGE_LINE_RE = re.compile(r"^\s*[-*]\s+(?P<rest>.*\[\[.*)$")
_JUSTIFICATION_SPLIT_RE = re.compile(r"\s+[—–-]{1,2}\s+")


def normalize_edge_label(label: str) -> str:
    """``Depends on`` → ``depends_on``; ``Challenged by`` → ``challenged_by``."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return cleaned


@dataclass
class Edge:
    source: str
    target: str
    type: str
    justification: str = ""
    cross_source: bool = False

    def key(self) -> tuple[str, str, str]:
        return (self.source, self.target, self.type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "justification": self.justification,
            "cross_source": self.cross_source,
        }


@dataclass
class Claim:
    slug: str
    path: Path
    claim_id: str = ""
    statement: str = ""
    confidence: str = DEFAULT_CONFIDENCE
    claim_type: str = ""
    source: str = ""
    source_note: str = ""
    source_locator: str = ""
    topics: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: str = "active"
    edges: list[Edge] = field(default_factory=list)
    evidence_text: str = ""
    error: str | None = None

    @property
    def confidence_value(self) -> int:
        return CONFIDENCE_VALUE.get(self.confidence, CONFIDENCE_VALUE[DEFAULT_CONFIDENCE])

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "claim_id": self.claim_id,
            "statement": self.statement,
            "confidence": self.confidence,
            "confidence_value": self.confidence_value,
            "claim_type": self.claim_type,
            "source": self.source,
            "topics": self.topics,
            "evidence": self.evidence,
            "status": self.status,
        }


def parse_claim(doc: frontmatter.Document, edge_types: Iterable[str]) -> Claim:
    """Build a `Claim` from a parsed markdown document."""
    claim = Claim(slug=doc.slug, path=doc.path, error=doc.error)
    if doc.error:
        return claim

    meta = doc.meta
    claim.claim_id = str(meta.get("claim_id") or "")
    claim.statement = str(meta.get("statement") or "")
    claim.confidence = str(meta.get("confidence") or DEFAULT_CONFIDENCE).strip().lower()
    claim.claim_type = str(meta.get("claim_type") or "")
    claim.source_note = str(meta.get("source_note") or "")
    claim.source_locator = str(meta.get("source_locator") or "")
    claim.status = str(meta.get("status") or "active").strip().lower()
    claim.tags = doc.tags
    claim.topics = [t[len("topic/") :] for t in doc.tags_with_prefix("topic/")]
    claim.evidence = [t[len("evidence/") :] for t in doc.tags_with_prefix("evidence/")]

    sources = doc.tags_with_prefix("source/")
    claim.source = sources[0][len("source/") :] if sources else ""

    claim.evidence_text = doc.section("Evidence")
    claim.edges = parse_edges(doc.section("Edges"), claim.slug, edge_types)
    return claim


def parse_edges(section: str, source_slug: str, edge_types: Iterable[str]) -> list[Edge]:
    """Parse an `## Edges` section body into typed edges.

    Unknown subheadings are kept with their normalised label rather than
    dropped, so the gate can report `UNKNOWN_EDGE_TYPE` instead of the edge
    vanishing without a trace.
    """
    if not section.strip():
        return []
    known = {normalize_edge_label(t): t for t in edge_types}
    edges: list[Edge] = []
    seen: set[tuple[str, str, str]] = set()

    headings = list(_EDGE_HEADING_RE.finditer(section))
    for i, m in enumerate(headings):
        label = normalize_edge_label(m.group("label"))
        edge_type = known.get(label, label)
        end = headings[i + 1].start() if i + 1 < len(headings) else len(section)
        for line in section[m.end() : end].splitlines():
            lm = _EDGE_LINE_RE.match(line)
            if not lm:
                continue
            rest = lm.group("rest")
            targets = frontmatter.wikilinks(rest)
            if not targets:
                continue
            justification = _justification_from(rest)
            for target in targets:
                key = (source_slug, target, edge_type)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    Edge(source=source_slug, target=target, type=edge_type, justification=justification)
                )
    return edges


def _justification_from(line: str) -> str:
    """Text after the em-dash following the wikilink(s)."""
    tail = line[line.rfind("]]") + 2 :]
    parts = _JUSTIFICATION_SPLIT_RE.split(tail, maxsplit=1)
    return (parts[1] if len(parts) > 1 else tail).strip(" -—–:\t")


class Graph:
    """Claims and typed edges, with the traversals Phase 4 needs."""

    def __init__(self, claims: dict[str, Claim], edge_types: Iterable[str]):
        self.claims = claims
        self.edge_types = list(edge_types)
        self.broken_links: list[Edge] = []
        self.edges: list[Edge] = []
        self._out: dict[str, list[Edge]] = defaultdict(list)
        self._in: dict[str, list[Edge]] = defaultdict(list)
        self._index()

    # ── construction ────────────────────────────────────────────────────
    def _index(self) -> None:
        active = {s for s, c in self.claims.items() if c.is_active}
        for claim in self.claims.values():
            if not claim.is_active:
                continue
            for edge in claim.edges:
                if edge.target not in active:
                    self.broken_links.append(edge)
                    continue
                if edge.target == edge.source:
                    continue  # self-edge: reported by the gate, never traversed
                edge.cross_source = (
                    self.claims[edge.source].source != self.claims[edge.target].source
                    and bool(self.claims[edge.source].source)
                    and bool(self.claims[edge.target].source)
                )
                self.edges.append(edge)
                self._out[edge.source].append(edge)
                self._in[edge.target].append(edge)

    # ── accessors ───────────────────────────────────────────────────────
    @property
    def active_claims(self) -> dict[str, Claim]:
        return {s: c for s, c in self.claims.items() if c.is_active}

    def out_edges(self, slug: str, types: Iterable[str] | None = None) -> list[Edge]:
        edges = self._out.get(slug, [])
        return [e for e in edges if e.type in set(types)] if types else list(edges)

    def in_edges(self, slug: str, types: Iterable[str] | None = None) -> list[Edge]:
        edges = self._in.get(slug, [])
        return [e for e in edges if e.type in set(types)] if types else list(edges)

    def degree(self, slug: str) -> int:
        return len(self._out.get(slug, [])) + len(self._in.get(slug, []))

    def orphans(self) -> list[str]:
        return sorted(s for s in self.active_claims if self.degree(s) == 0)

    def sources(self) -> set[str]:
        return {c.source for c in self.active_claims.values() if c.source}

    def topics(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for slug, claim in self.active_claims.items():
            for topic in claim.topics:
                out[topic].append(slug)
        return dict(out)

    # ── traversal ───────────────────────────────────────────────────────
    def collapse_set(self, slug: str, max_depth: int = 32) -> dict[str, int]:
        """Claims that lose their footing if `slug` is false, with their depth.

        Walks inbound `COLLAPSE_EDGE_TYPES` edges: if B is false, anything that
        depends on / extends / operationalizes B collapses, and so does anything
        that collapses with those. Visited-set BFS, so a `depends_on` cycle
        terminates instead of hanging — the gate reports the cycle separately.
        """
        types = [t for t in COLLAPSE_EDGE_TYPES if t in self.edge_types]
        seen: dict[str, int] = {}
        queue = deque([(slug, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for edge in self.in_edges(current, types):
                if edge.source in seen or edge.source == slug:
                    continue
                seen[edge.source] = depth + 1
                queue.append((edge.source, depth + 1))
        return seen

    def cascade_tree(self, slug: str, max_depth: int = 4) -> dict[str, Any]:
        """Level-by-level collapse radius for `slug`, capped at `max_depth`."""
        types = [t for t in COLLAPSE_EDGE_TYPES if t in self.edge_types]
        levels: list[list[dict[str, Any]]] = []
        seen = {slug}
        frontier = [slug]
        for _ in range(max_depth):
            nxt: list[dict[str, Any]] = []
            for node in frontier:
                for edge in self.in_edges(node, types):
                    if edge.source in seen:
                        continue
                    seen.add(edge.source)
                    child = self.claims[edge.source]
                    nxt.append(
                        {
                            "slug": edge.source,
                            "via": edge.type,
                            "parent": node,
                            "confidence": child.confidence,
                            "statement": child.statement,
                            "contested": bool(self.in_edges(edge.source, ["contradicts"])),
                        }
                    )
            if not nxt:
                break
            levels.append(nxt)
            frontier = [n["slug"] for n in nxt]
        return {"root": slug, "levels": levels, "total": sum(len(l) for l in levels)}

    def components(self, types: Iterable[str] | None = None) -> list[list[str]]:
        """Connected components over undirected edges, largest first."""
        wanted = set(types) if types else None
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in self.edges:
            if wanted and edge.type not in wanted:
                continue
            adjacency[edge.source].add(edge.target)
            adjacency[edge.target].add(edge.source)

        seen: set[str] = set()
        out: list[list[str]] = []
        for slug in self.active_claims:
            if slug in seen:
                continue
            group: list[str] = []
            queue = deque([slug])
            seen.add(slug)
            while queue:
                node = queue.popleft()
                group.append(node)
                for neighbour in adjacency.get(node, ()):
                    if neighbour not in seen:
                        seen.add(neighbour)
                        queue.append(neighbour)
            out.append(sorted(group))
        return sorted(out, key=len, reverse=True)

    def find_cycles(self, edge_type: str = "depends_on", limit: int = 20) -> list[list[str]]:
        """Directed cycles in one edge type. Iterative DFS — no recursion limit."""
        cycles: list[list[str]] = []
        colour: dict[str, int] = {}  # 0 = on stack, 1 = finished
        for start in self.active_claims:
            if colour.get(start) is not None:
                continue
            stack: list[tuple[str, Iterator[Edge]]] = [(start, iter(self.out_edges(start, [edge_type])))]
            path = [start]
            colour[start] = 0
            while stack:
                node, edges = stack[-1]
                advanced = False
                for edge in edges:
                    nxt = edge.target
                    if colour.get(nxt) == 0:
                        cycle = path[path.index(nxt) :] + [nxt]
                        cycles.append(cycle)
                        if len(cycles) >= limit:
                            return cycles
                    elif colour.get(nxt) is None:
                        colour[nxt] = 0
                        path.append(nxt)
                        stack.append((nxt, iter(self.out_edges(nxt, [edge_type]))))
                        advanced = True
                        break
                if not advanced:
                    colour[node] = 1
                    stack.pop()
                    if path:
                        path.pop()
        return cycles

    # ── metrics ─────────────────────────────────────────────────────────
    def metrics(self) -> dict[str, Any]:
        active = self.active_claims
        n = len(active)
        cross = sum(1 for e in self.edges if e.cross_source)
        orphans = self.orphans()
        by_type: dict[str, int] = defaultdict(int)
        for e in self.edges:
            by_type[e.type] += 1
        return {
            "claims": n,
            "claims_total": len(self.claims),
            "edges": len(self.edges),
            "edges_per_claim": round(len(self.edges) / n, 3) if n else 0.0,
            "cross_source_edges": cross,
            "cross_source_ratio": round(cross / len(self.edges), 3) if self.edges else 0.0,
            "orphans": len(orphans),
            "orphan_ratio": round(len(orphans) / n, 3) if n else 0.0,
            "sources": len(self.sources()),
            "topics": len(self.topics()),
            "broken_links": len(self.broken_links),
            "edges_by_type": dict(sorted(by_type.items())),
            "components": len(self.components()),
        }

    # ── serialisation ───────────────────────────────────────────────────
    def edge_index(self) -> dict[str, Any]:
        return {
            "edge_count": len(self.edges),
            "edges": [e.to_dict() for e in sorted(self.edges, key=lambda e: e.key())],
        }

    def write_edge_index(self, path: Path | str) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.edge_index(), indent=2) + "\n", encoding="utf-8")
        return p

    def export(self) -> dict[str, Any]:
        """The whole graph as JSON, for a real query layer."""
        return {
            "metrics": self.metrics(),
            "claims": [c.to_dict() for c in sorted(self.active_claims.values(), key=lambda c: c.slug)],
            "edges": [e.to_dict() for e in sorted(self.edges, key=lambda e: e.key())],
        }


def load_graph(project_dir: Path | str, edge_types: Iterable[str] | None = None) -> Graph:
    """Parse every claim file under `notes/claims/` into a `Graph`."""
    from .manifest import BASE_EDGE_TYPES

    root = Path(project_dir)
    claims_dir = root / "notes" / "claims"
    types = list(edge_types or BASE_EDGE_TYPES)

    claims: dict[str, Claim] = {}
    if claims_dir.is_dir():
        for path in sorted(claims_dir.glob("*.md")):
            doc = frontmatter.read(path)
            # Index files and templates live alongside claims; `type/claim` is
            # what distinguishes a node from a directory listing of nodes.
            if not doc.error and "type/claim" not in doc.tags:
                continue
            claims[doc.slug] = parse_claim(doc, types)
    return Graph(claims, types)
