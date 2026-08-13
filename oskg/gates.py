"""Quality gates — programmatic checks at every phase boundary.

No model calls, no judgment, no cost. Gates catch structural defects: missing
fields, unresolved wikilinks, empty evidence, asymmetric contradictions. They do
not check whether a claim is *true* — that is a human spot-check, and every claim
carries a locator to make it quick.

The prior projects used an LLM review pass for this. It cost as much as the
extraction it reviewed and it was unreliable in the case that mattered most: it
would report PASS on a batch with broken wikilinks because it never actually
stat'd the files. Every check below is a loop over parsed markdown, which is why
it can run after every batch instead of every phase.

See spec/quality-gates.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import frontmatter
from .graph import load_graph
from .manifest import CONFIDENCE_LEVELS, Manifest

__all__ = ["Finding", "GateReport", "run_gate", "run_gates", "FATAL", "ERROR", "WARN"]

FATAL = "fatal"
ERROR = "error"
WARN = "warn"
_SEVERITY_ORDER = {WARN: 0, ERROR: 1, FATAL: 2}

# Text that signals extracted source material sitting in a committed note.
# A copyright control, not a style rule — see METHODOLOGY.md §5.
_FULLTEXT_MARKERS = (
    re.compile(r"^\s*(?:\[?page\s+\d+\]?|p{1,2}\.\s*\d+\s*$)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<<<\s*BEGIN\s+(?:FULL\s*TEXT|EXTRACT)", re.IGNORECASE),
)
_FULLTEXT_LINE_BUDGET = 400  # a note this long is a transcript, not an analysis

_REQUIRED_CLAIM_FIELDS = (
    "claim_id",
    "statement",
    "confidence",
    "claim_type",
    "source_note",
    "tags",
)
_REQUIRED_NOTE_FIELDS = (
    "source_title",
    "source_author",
    "source_tier",
    "locator",
    "tags",
)


@dataclass
class Finding:
    check: str
    severity: str
    path: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"check": self.check, "severity": self.severity, "path": self.path, "detail": self.detail}

    def __str__(self) -> str:
        return f"{self.severity.upper():5} {self.check:24} {self.path}  {self.detail}"


@dataclass
class GateReport:
    phase: int
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    root: Path | None = None

    def add(self, check: str, severity: str, path: Any, detail: str = "") -> None:
        self.findings.append(Finding(check, severity, self._display(path), detail))

    def _display(self, path: Any) -> str:
        """Project-relative where possible — absolute paths bury the filename."""
        if self.root is None:
            return str(path)
        try:
            return str(Path(path).relative_to(self.root)) or "."
        except (ValueError, TypeError):
            return str(path)

    def of(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def fatal(self) -> list[Finding]:
        return self.of(FATAL)

    @property
    def errors(self) -> list[Finding]:
        return self.of(ERROR)

    @property
    def warnings(self) -> list[Finding]:
        return self.of(WARN)

    @property
    def passed(self) -> bool:
        """Warnings do not fail a gate; errors and fatals do."""
        return not self.errors and not self.fatal

    def exit_code(self) -> int:
        if self.fatal:
            return 2
        return 1 if self.errors else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "passed": self.passed,
            "counts": {
                "fatal": len(self.fatal),
                "error": len(self.errors),
                "warn": len(self.warnings),
            },
            "stats": self.stats,
            "findings": [f.to_dict() for f in self.findings],
        }

    def format(self, *, verbose: bool = False) -> str:
        lines = [f"Gate {self.phase}: {'PASS' if self.passed else 'FAIL'}"]
        if self.stats:
            lines.append("  " + " · ".join(f"{k}={v}" for k, v in self.stats.items()))
        shown = self.findings if verbose else [f for f in self.findings if f.severity != WARN]
        for f in sorted(shown, key=lambda f: (-_SEVERITY_ORDER[f.severity], f.check, f.path))[:60]:
            lines.append(f"  {f}")
        hidden = len(self.findings) - len(shown)
        if hidden > 0 and not verbose:
            lines.append(f"  ({hidden} warnings hidden — pass --verbose to see them)")
        return "\n".join(lines)

    def repair_brief(self, limit: int = 40) -> str:
        """The failure list, formatted for a targeted repair prompt.

        Failures only, no warnings, no prose: a repair pass that is told what is
        broken fixes it, and a repair pass that is told to "improve quality"
        rewrites things that were fine.
        """
        problems = sorted(
            self.fatal + self.errors, key=lambda f: (-_SEVERITY_ORDER[f.severity], f.path)
        )[:limit]
        return "\n".join(f"- {f.path}: {f.check} — {f.detail}" for f in problems)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────────


def run_gate(project_dir: Path | str, phase: int, manifest: Manifest) -> GateReport:
    root = Path(project_dir)
    report = GateReport(phase=phase, root=root)
    checker = {
        0: _gate_scoping,
        1: _gate_notes,
        2: _gate_claims,
        3: _gate_edges,
        4: _gate_synthesis,
        5: _gate_capstone,
    }.get(phase)
    if checker is None:
        report.add("UNKNOWN_PHASE", ERROR, root, f"no gate defined for phase {phase}")
        return report
    checker(root, manifest, report)
    return report


def run_gates(project_dir: Path | str, manifest: Manifest, through_phase: int) -> list[GateReport]:
    return [run_gate(project_dir, p, manifest) for p in range(0, through_phase + 1)]


# ─────────────────────────────────────────────────────────────────────────────
# Gate 0 — Scoping
# ─────────────────────────────────────────────────────────────────────────────


def _gate_scoping(root: Path, manifest: Manifest, report: GateReport) -> None:
    problems = manifest.validate()
    for p in problems:
        report.add("MANIFEST_INVALID", FATAL, root / "oskg.yaml", p)

    guide = root / "SOURCE-GUIDE.md"
    if not guide.exists():
        report.add("NO_CANON", FATAL, guide, "SOURCE-GUIDE.md is missing")
        return

    sources = parse_source_guide(guide)
    report.stats["sources"] = len(sources)
    report.stats["tier1"] = sum(1 for s in sources if s.get("tier") == 1)

    if not sources:
        report.add("NO_CANON", FATAL, guide, "no sources listed")
        return
    if not any(s.get("tier") == 1 for s in sources):
        report.add("NO_CANON", FATAL, guide, "no Tier 1 source; the graph has no vocabulary anchor")

    for s in sources:
        missing = [k for k in ("title", "slug", "tier") if not s.get(k)]
        if missing:
            report.add("INCOMPLETE_SOURCE", ERROR, guide, f"{s.get('title') or s.get('slug')}: missing {missing}")
        if not s.get("status"):
            report.add("NO_ACQUISITION_STATUS", WARN, guide, f"{s.get('slug')}: no acquisition status")

    if len(manifest.topics) < 3:
        report.add(
            "THIN_TOPICS", WARN, root / "oskg.yaml",
            f"{len(manifest.topics)} seed topics; sparse topics mean sparse Phase 3 clustering",
        )


def parse_source_guide(path: Path) -> list[dict[str, Any]]:
    """Read the source table out of SOURCE-GUIDE.md.

    The guide is markdown because a human reads it before trusting a graph. The
    machine-readable part is a pipe table with a `slug` column, under `## Tier N`
    headings which supply the tier.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    sources: list[dict[str, Any]] = []
    tier = 0
    header: list[str] | None = None
    for line in text.splitlines():
        tier_match = re.match(r"^#{2,3}\s*Tier\s+(\d)", line.strip(), re.IGNORECASE)
        if tier_match:
            tier = int(tier_match.group(1))
            header = None
            continue
        if not line.strip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells if c):
            continue  # the ---|--- separator row
        if header is None:
            header = [c.lower() for c in cells]
            continue
        row = dict(zip(header, cells))
        if not row.get("slug"):
            continue
        sources.append(
            {
                "slug": row.get("slug", ""),
                "title": row.get("title", ""),
                "author": row.get("author", ""),
                "year": row.get("year", ""),
                "tier": int(row["tier"]) if row.get("tier", "").isdigit() else tier,
                "role": row.get("role", ""),
                "status": row.get("status", ""),
            }
        )
    return sources


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1 — Reading notes
# ─────────────────────────────────────────────────────────────────────────────

_TIER_CLAIM_RANGE = {1: (6, 12), 2: (5, 10), 3: (3, 8), 4: (2, 6)}


def _gate_notes(root: Path, manifest: Manifest, report: GateReport) -> None:
    notes = list(iter_reading_notes(root, manifest))
    report.stats["notes"] = len(notes)
    if not notes:
        report.add("STUB_NOTE", ERROR, root / "notes", "no reading notes found")
        return

    known_sources = {s["slug"] for s in parse_source_guide(root / "SOURCE-GUIDE.md")}
    total_candidates = 0

    for doc in notes:
        if doc.error:
            report.add("MISSING_FIELDS", ERROR, doc.path, doc.error)
            continue

        missing = [f for f in _REQUIRED_NOTE_FIELDS if not doc.meta.get(f)]
        if missing:
            report.add("MISSING_FIELDS", ERROR, doc.path, f"missing {missing}")

        tier = doc.meta.get("source_tier")
        if not isinstance(tier, int) or tier not in (1, 2, 3, 4):
            report.add("BAD_TIER", ERROR, doc.path, f"source_tier={tier!r}")
            tier = 2

        source_tag = doc.tag_after("source/")
        if not source_tag:
            report.add("MISSING_FIELDS", ERROR, doc.path, "no source/ tag")
        elif known_sources and source_tag not in known_sources:
            report.add("UNKNOWN_SOURCE", ERROR, doc.path, f"source/{source_tag} not in SOURCE-GUIDE.md")

        candidates_section = doc.section("Candidate Claims", "Claims")
        if not candidates_section:
            report.add("NO_CANDIDATES", ERROR, doc.path, "no '## Candidate Claims' section")
        else:
            headings = re.findall(r"^###\s+Claim\s+\d+", candidates_section, re.MULTILINE)
            count = len(headings)
            total_candidates += count
            lo, hi = _TIER_CLAIM_RANGE.get(tier, (3, 10))
            if count < lo:
                report.add("THIN_NOTE", WARN, doc.path, f"{count} candidate claims, tier {tier} expects >={lo}")
            elif count > hi + 4:
                report.add("BLOATED_NOTE", WARN, doc.path, f"{count} candidate claims, tier {tier} expects <={hi}")
            if count and not re.search(r"\*\*Locator:\*\*", candidates_section):
                report.add("NO_LOCATOR", WARN, doc.path, "candidate claims carry no locators")

        if len(doc.body.strip()) < 400:
            report.add("STUB_NOTE", ERROR, doc.path, f"{len(doc.body.strip())} chars of body")

        _check_fulltext_leak(doc, report)

    report.stats["candidate_claims"] = total_candidates


def _check_fulltext_leak(doc: frontmatter.Document, report: GateReport) -> None:
    body = doc.body
    if len(body.splitlines()) > _FULLTEXT_LINE_BUDGET:
        report.add(
            "FULLTEXT_LEAK", FATAL, doc.path,
            f"{len(body.splitlines())} lines — reads as a transcript, not an analysis",
        )
        return
    for marker in _FULLTEXT_MARKERS:
        hits = marker.findall(body)
        if len(hits) > 12:
            report.add(
                "FULLTEXT_LEAK", FATAL, doc.path,
                f"{len(hits)} page-break markers — extracted source text belongs in sources/**/_txt/",
            )
            return


def iter_reading_notes(root: Path, manifest: Manifest) -> Iterable[frontmatter.Document]:
    notes_dir = root / "notes"
    if not notes_dir.is_dir():
        return
    for domain in manifest.note_domains:
        for path in sorted((notes_dir / domain).glob("**/*.md")):
            if path.stem.endswith("Index") or path.stem == "Index":
                continue
            doc = frontmatter.read(path)
            if doc.error or "type/note" in doc.tags:
                yield doc


# ─────────────────────────────────────────────────────────────────────────────
# Gate 2 — Claims
# ─────────────────────────────────────────────────────────────────────────────


def _gate_claims(root: Path, manifest: Manifest, report: GateReport) -> None:
    claims_dir = root / "notes" / "claims"
    if not claims_dir.is_dir():
        report.add("MISSING_FIELDS", ERROR, claims_dir, "notes/claims/ does not exist")
        return

    graph = load_graph(root, manifest.edge_types)
    report.stats["claims"] = len(graph.claims)
    if not graph.claims:
        report.add("MISSING_FIELDS", ERROR, claims_dir, "no claim files found")
        return

    gates = manifest.gates
    valid_confidence = set(CONFIDENCE_LEVELS)
    valid_types = set(manifest.claim_types)
    note_stems = {p.stem for p in (root / "notes").glob("**/*.md")}
    seen_ids: dict[str, str] = {}
    per_note: dict[str, int] = {}

    for slug, claim in graph.claims.items():
        path = claim.path
        if claim.error:
            report.add("YAML_PARSE_ERROR", ERROR, path, claim.error)
            continue

        present = {
            "claim_id": claim.claim_id,
            "statement": claim.statement,
            "confidence": claim.confidence,
            "claim_type": claim.claim_type,
            "source_note": claim.source_note,
            "tags": claim.tags,
        }
        missing = sorted(f for f in _REQUIRED_CLAIM_FIELDS if not present.get(f))
        if missing:
            report.add("MISSING_FIELDS", ERROR, path, f"missing {missing}")

        if claim.confidence not in valid_confidence:
            report.add("BAD_CONFIDENCE", ERROR, path, f"confidence={claim.confidence!r}")
        if valid_types and claim.claim_type and claim.claim_type not in valid_types:
            report.add("BAD_CLAIM_TYPE", ERROR, path, f"claim_type={claim.claim_type!r} not in manifest")

        if len(claim.topics) < int(gates["min_topic_tags"]):
            report.add("THIN_TAGS", WARN, path, f"{len(claim.topics)} topic tags")
        if not claim.evidence:
            report.add("THIN_TAGS", WARN, path, "no evidence/ tag")

        source_tags = [t for t in claim.tags if t.startswith("source/")]
        if len(source_tags) != 1:
            report.add("BAD_SOURCE_TAG", ERROR, path, f"{len(source_tags)} source/ tags, expected exactly 1")

        if claim.claim_id:
            if claim.claim_id in seen_ids and seen_ids[claim.claim_id] != slug:
                report.add("DUPLICATE_SLUG", WARN, path, f"claim_id {claim.claim_id} also on {seen_ids[claim.claim_id]}")
            seen_ids[claim.claim_id] = slug

        if len(claim.evidence_text.strip()) < int(gates["min_evidence_chars"]):
            report.add(
                "THIN_EVIDENCE", WARN, path,
                f"{len(claim.evidence_text.strip())} chars, want >={gates['min_evidence_chars']}",
            )

        note_ref = _wikilink_target(claim.source_note)
        if note_ref:
            per_note[note_ref] = per_note.get(note_ref, 0) + 1
            if note_stems and note_ref not in note_stems:
                report.add("BROKEN_SOURCE_NOTE", ERROR, path, f"source_note [[{note_ref}]] does not resolve")

        for edge in claim.edges:
            if edge.target == slug:
                report.add("SELF_EDGE", ERROR, path, f"{edge.type} → itself")
            if edge.type not in manifest.edge_types:
                report.add(
                    "UNKNOWN_EDGE_TYPE", ERROR, path,
                    f"'{edge.type}' not in manifest edge_types {manifest.edge_types}",
                )

    for edge in graph.broken_links:
        report.add(
            "BROKEN_LINK", ERROR, graph.claims[edge.source].path,
            f"[[{edge.target}]] does not resolve — wikilinks use the FILENAME slug, not claim_id",
        )

    lo, hi = manifest.claims_per_note
    for note, count in sorted(per_note.items()):
        if count < lo or count > hi:
            report.add("BAD_CLAIM_COUNT", WARN, note, f"{count} claims, expected {lo}-{hi}")

    for topic, slugs in sorted(graph.topics().items()):
        if len(slugs) < 3:
            report.add(
                "SUSPECTED_SYNONYM", WARN, f"topic/{topic}",
                f"only {len(slugs)} claims — check it is not a synonym of an existing topic",
            )

    report.stats["broken_links"] = len(graph.broken_links)
    report.stats["sources"] = len(graph.sources())


def _wikilink_target(value: str) -> str:
    links = frontmatter.wikilinks(value or "")
    return links[0] if links else ""


# ─────────────────────────────────────────────────────────────────────────────
# Gate 3 — Edges
# ─────────────────────────────────────────────────────────────────────────────


def _gate_edges(root: Path, manifest: Manifest, report: GateReport) -> None:
    graph = load_graph(root, manifest.edge_types)
    metrics = graph.metrics()
    report.stats.update(
        {
            "claims": metrics["claims"],
            "edges": metrics["edges"],
            "per_claim": metrics["edges_per_claim"],
            "cross_source": f"{int(metrics['cross_source_ratio'] * 100)}%",
            "orphans": metrics["orphans"],
        }
    )
    if not graph.claims:
        report.add("DANGLING_EDGE", ERROR, root, "no claims to build edges from")
        return

    gates = manifest.gates
    known_types = set(manifest.edge_types)

    for edge in graph.broken_links:
        report.add(
            "DANGLING_EDGE", ERROR, graph.claims[edge.source].path,
            f"{edge.type} → [[{edge.target}]] (missing or not status: active)",
        )

    for edge in graph.edges:
        if edge.type not in known_types:
            report.add("UNKNOWN_EDGE_TYPE", ERROR, graph.claims[edge.source].path, f"'{edge.type}'")
        if _is_restatement(edge.justification, edge.target, edge.type):
            report.add(
                "EMPTY_JUSTIFICATION", WARN, graph.claims[edge.source].path,
                f"{edge.type} → {edge.target}: justification restates the link",
            )

    # `contradicts` is reciprocal by definition; a one-sided one hides half the
    # fault line from the contradiction-cluster analysis.
    contradictions = {(e.source, e.target) for e in graph.edges if e.type == "contradicts"}
    for a, b in sorted(contradictions):
        if (b, a) not in contradictions:
            report.add(
                "ASYMMETRIC_CONTRADICTION", ERROR, graph.claims[a].path,
                f"{a} contradicts {b}, but {b} does not contradict {a}",
            )

    for cycle in graph.find_cycles("depends_on"):
        report.add("DEPENDENCY_CYCLE", ERROR, graph.claims[cycle[0]].path, " → ".join(cycle))

    if metrics["edges_per_claim"] < float(gates["min_edges_per_claim"]):
        report.add(
            "SPARSE_GRAPH", ERROR, root,
            f"{metrics['edges_per_claim']} edges/claim, floor is {gates['min_edges_per_claim']}",
        )
    if metrics["cross_source_ratio"] < float(gates["min_cross_source_ratio"]):
        report.add(
            "ISOLATED_SOURCES", ERROR, root,
            f"{int(metrics['cross_source_ratio'] * 100)}% cross-source, floor is "
            f"{int(float(gates['min_cross_source_ratio']) * 100)}% — sources were processed in isolation",
        )
    if metrics["orphan_ratio"] > float(gates["max_orphan_ratio"]):
        report.add(
            "HIGH_ORPHAN_RATE", WARN, root,
            f"{int(metrics['orphan_ratio'] * 100)}% of claims have no edges",
        )

    # `.oskg/edges.json` is derived. Regenerate rather than complain: claim files
    # are the source of truth, so drift means the index is stale, not wrong.
    index_path = root / ".oskg" / "edges.json"
    if index_path.exists():
        try:
            import json

            stored = json.loads(index_path.read_text(encoding="utf-8"))
            if stored.get("edge_count") != len(graph.edges):
                report.add(
                    "EDGE_INDEX_DRIFT", WARN, index_path,
                    f"index has {stored.get('edge_count')} edges, claim files have {len(graph.edges)} — regenerated",
                )
        except (OSError, ValueError):
            pass
    graph.write_edge_index(index_path)


def _is_restatement(justification: str, target: str, edge_type: str) -> bool:
    """True when a justification carries no content beyond the slug and type."""
    text = justification.strip().lower()
    if not text:
        return True
    for token in (target.lower(), edge_type.lower(), edge_type.replace("_", " ").lower(), "claim", "this"):
        text = text.replace(token, " ")
    return len(re.sub(r"[^a-z]+", "", text)) < 12


# ─────────────────────────────────────────────────────────────────────────────
# Gates 4 and 5 — Synthesis and capstone
# ─────────────────────────────────────────────────────────────────────────────

_ANALYSIS_KEYS = ("hinges", "cascades", "convergence", "contradictions", "gaps")


def _gate_synthesis(root: Path, manifest: Manifest, report: GateReport) -> None:
    import json

    analysis_path = root / ".oskg" / "analysis.json"
    if not analysis_path.exists():
        report.add("NO_ANALYSIS", FATAL, analysis_path, "run `oskg analyze` first")
        return
    try:
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report.add("NO_ANALYSIS", FATAL, analysis_path, str(exc))
        return

    missing = [k for k in _ANALYSIS_KEYS if k not in analysis]
    if missing:
        report.add("INCOMPLETE_ANALYSIS", ERROR, analysis_path, f"missing {missing}")

    synthesis_dir = root / "notes" / "synthesis"
    docs = [
        frontmatter.read(p)
        for p in sorted(synthesis_dir.glob("*.md"))
        if not p.stem.endswith("Index")
    ]
    report.stats["synthesis_docs"] = len(docs)
    if not docs:
        report.add("INCOMPLETE_ANALYSIS", ERROR, synthesis_dir, "no synthesis documents written")
        return

    _check_citations(root, manifest, docs, report)


def _gate_capstone(root: Path, manifest: Manifest, report: GateReport) -> None:
    candidates = sorted((root / "notes" / "synthesis").glob("*capstone*.md"))
    if not candidates:
        report.add("NO_CAPSTONE", FATAL, root / "notes" / "synthesis", "no capstone document")
        return

    doc = frontmatter.read(candidates[0])
    report.stats["capstone"] = doc.path.name
    if doc.error:
        report.add("NO_CAPSTONE", FATAL, doc.path, doc.error)
        return
    if len(doc.body.strip()) < 2000:
        report.add("NO_CAPSTONE", ERROR, doc.path, f"{len(doc.body.strip())} chars — too thin to be a capstone")

    cited = set(_check_citations(root, manifest, [doc], report))
    report.stats["cited_claims"] = len(cited)
    if len(cited) < 10:
        report.add("THIN_CITATION", WARN, doc.path, f"cites {len(cited)} claims, want >=10")

    text = doc.body.lower()
    if not any(w in text for w in ("limitation", "caveat", "what this does not", "unknown", "fragil")):
        report.add("NO_LIMITATIONS", WARN, doc.path, "no section naming the graph's limitations")


def _check_citations(
    root: Path, manifest: Manifest, docs: list[frontmatter.Document], report: GateReport
) -> list[str]:
    """Every claim slug cited in a write-up must exist. Returns those cited."""
    graph = load_graph(root, manifest.edge_types)
    known = set(graph.claims)
    note_stems = {p.stem for p in (root / "notes").glob("**/*.md")}
    cited: list[str] = []
    for doc in docs:
        for link in doc.wikilinks():
            target = link.split("/")[-1]
            if target in known:
                cited.append(target)
            elif target not in note_stems:
                report.add(
                    "PHANTOM_CITATION", ERROR, doc.path,
                    f"[[{link}]] matches no claim or note — the write-up invented it",
                )
    return cited
