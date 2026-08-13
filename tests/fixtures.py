"""Fixture builders — a synthetic OSKG project with a known graph shape.

The graph is small but not trivial: it has a hinge with a two-level cascade, a
reciprocal contradiction between confident claims, a three-source convergence,
an orphan, and (on request) the two defects the gates exist to catch — a
`claim_id`-style broken wikilink and a one-sided contradiction.

Knowing the shape by construction is what lets the analysis tests assert exact
numbers rather than "it returned something".
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oskg.manifest import Manifest, default_manifest

CLAIM_TEMPLATE = """---
tags:
  - type/claim
  - {tag}
  - evidence/{evidence}
  - source/{source}
{topic_tags}
claim_id: "{source}.{n}"
statement: "{statement}"
confidence: "{confidence}"
confidence_rationale: "Stated by the source with named supporting evidence."
claim_type: "{claim_type}"
source_note: "[[{note}]]"
source_locator: "p. {n}"
created: 2026-08-12
status: {status}
---

# {source}.{n}: {statement}

## The Claim

{statement}

## Evidence

- The source argues this at length, naming the material it rests on and the
  reasoning that connects them, which is enough to clear the evidence floor.
- A second, independent line of support is given in the same section.

## Confidence

**Rating:** {confidence}
**Rationale:** Stated by the source with named supporting evidence.

## Stakes

If this is wrong, the arguments that build on it lose their footing.

## Disagreement

**Who disagrees:** _None identified._

## Edges

{edges}

## Assessment

Sits where the corpus puts it.
"""

NOTE_TEMPLATE = """---
tags:
  - type/note
  - {tag}
  - source/{source}
  - topic/{topic}
source_title: "{title}"
source_author: "An Author"
source_year: 2020
source_tier: {tier}
locator: "Ch 1, pp. 1-20"
created: 2026-08-12
claims_status: {claims_status}
claims_count: {claims_count}
---

# {title}

**Work:** An Author, *{title}*, 2020

## What This Section Argues

The section makes an argument, states the evidence it rests on, and engages with
two other works in the corpus. This paragraph exists so the note clears the
substance floor the Phase 1 gate enforces on reading notes.

## Argument Structure

1. **Opening move** (p. 1) — the thesis is stated and the evidence named.
2. **Second move** (p. 8) — the objection is raised and answered.

## Candidate Claims

### Claim 1: The first assertion the section makes
- **Locator:** p. 3
- **Evidence:** what the author offers
- **Confidence:** high — stated directly with named evidence
- **Type:** definitional

### Claim 2: The second assertion the section makes
- **Locator:** p. 9
- **Evidence:** what the author offers
- **Confidence:** medium — inferred from the surrounding argument
- **Type:** empirical

## Cross-References

| Source | Engagement | Locator |
|---|---|---|
| [[Other Note]] | extends | p. 12 |

## Open Questions

What the section raises and does not settle.
"""

SOURCE_GUIDE = """---
tags: [type/meta, source-guide]
created: 2026-08-12
---

# Source Guide

## Why this corpus

Three sources chosen to exercise cross-source edges.

## Tier 1 — Canon

| slug | title | author | year | tier | role | status |
|---|---|---|---|---|---|---|
| s1 | The Canonical Work | An Author | 2020 | 1 | sets the vocabulary | acquired |

## Tier 2 — Core

| slug | title | author | year | tier | role | status |
|---|---|---|---|---|---|---|
| s2 | The Second Work | Another Author | 2021 | 2 | carries most claims | acquired |
| s3 | The Third Work | A Third Author | 2022 | 2 | the minority position | acquired |

## Tier 3 — Practitioner and community

| slug | title | author | year | tier | role | status |
|---|---|---|---|---|---|---|
| s4 | The Adjacent Work | A Fourth Author | 2019 | 3 | field perspective | pending |
"""


def make_claim(
    root: Path,
    slug: str,
    *,
    tag: str = "oskg-test",
    source: str = "s1",
    statement: str = "A claim about the subject matter",
    confidence: str = "high",
    claim_type: str = "definitional",
    topics: tuple[str, ...] = ("alpha",),
    evidence: str = "empirical",
    edges: str = "",
    note: str = "Note One",
    status: str = "active",
    n: int = 1,
) -> Path:
    path = root / "notes" / "claims" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        CLAIM_TEMPLATE.format(
            tag=tag,
            source=source,
            statement=statement,
            confidence=confidence,
            claim_type=claim_type,
            topic_tags="\n".join(f"  - topic/{t}" for t in topics),
            evidence=evidence,
            edges=edges or _empty_edges(),
            note=note,
            status=status,
            n=n,
        ),
        encoding="utf-8",
    )
    return path


def _empty_edges() -> str:
    return "\n\n".join(
        f"**{label}:**"
        for label in ("Depends on", "Supports", "Contradicts", "Extends")
    )


_EDGE_LABELS = {
    "depends_on": "Depends on",
    "supports": "Supports",
    "contradicts": "Contradicts",
    "extends": "Extends",
    "operationalizes": "Operationalizes",
    "challenged_by": "Challenged by",
}


def edge_block(**by_type: list[str]) -> str:
    """Build an `## Edges` body.

    Each item is ``"target-slug — justification"``; the justification is
    optional and defaults to something long enough to pass the
    restatement check.
    """
    sections = []
    for key, label in _EDGE_LABELS.items():
        rendered = []
        for item in by_type.get(key) or []:
            target, _, justification = item.partition(" — ")
            rendered.append(
                f"- [[{target.strip()}]] — "
                f"{justification.strip() or 'a justification naming the actual argument at issue'}"
            )
        sections.append(f"**{label}:**" + ("\n" + "\n".join(rendered) if rendered else ""))
    return "\n\n".join(sections)


def make_note(
    root: Path,
    name: str,
    *,
    tag: str = "oskg-test",
    source: str = "s1",
    tier: int = 1,
    topic: str = "alpha",
    domain: str = "concepts",
    claims_status: str = "pending",
    claims_count: int = 0,
) -> Path:
    path = root / "notes" / domain / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        NOTE_TEMPLATE.format(
            tag=tag,
            source=source,
            tier=tier,
            topic=topic,
            title=name,
            claims_status=claims_status,
            claims_count=claims_count,
        ),
        encoding="utf-8",
    )
    return path


def make_project(tmpdir: str | Path | None = None, *, budget: float = 20.0) -> tuple[Path, Manifest]:
    """An empty but valid project: manifest, directories, source guide."""
    root = Path(tmpdir or tempfile.mkdtemp())
    root.mkdir(parents=True, exist_ok=True)
    manifest = default_manifest(project="OSKG-Test", topic="a test subject", slug="test", budget_usd=budget)
    manifest.data["tag"] = "oskg-test"
    manifest.data["topics"] = ["alpha", "beta", "gamma"]
    manifest.save(root)
    for sub in ("claims", "synthesis", *manifest.note_domains):
        (root / "notes" / sub).mkdir(parents=True, exist_ok=True)
    (root / "SOURCE-GUIDE.md").write_text(SOURCE_GUIDE, encoding="utf-8")
    return root, manifest


def make_graph_project(tmpdir: str | Path | None = None, *, broken: bool = False):
    """A project with a known graph shape.

    Shape, by construction:

      hinge          ← depends_on ← dep-a, dep-b       (2 direct)
      dep-a          ← depends_on ← dep-c              (1 more, depth 2)
      hinge          ← supports   ← sup-1, sup-2, sup-3 (3 sources → convergence)
      contra-x      ↔ contradicts ↔ contra-y           (both high → genuine unknown)
      orphan         (no edges)

    So: collapse_set(hinge) == {dep-a: 1, dep-b: 1, dep-c: 2}.

    With `broken=True`, two defects are added for the gates to find: a wikilink
    written as a `claim_id` (the failure the whole gate suite exists for) and a
    one-sided `contradicts`.
    """
    root, manifest = make_project(tmpdir)
    make_note(root, "Note One", source="s1", tier=1)
    make_note(root, "Note Two", source="s2", tier=2)
    make_note(root, "Note Three", source="s3", tier=2)

    make_claim(root, "hinge", source="s1", statement="The load-bearing claim", topics=("alpha", "beta"))
    make_claim(
        root, "dep-a", source="s2", note="Note Two", statement="Rests on the hinge",
        topics=("alpha",),
        edges=edge_block(
            depends_on=["hinge — the argument presupposes it"],
            supports=["dep-b — the same evidence reaches the parallel conclusion"],
        ),
    )
    make_claim(
        root, "dep-b", source="s3", note="Note Three", statement="Also rests on the hinge",
        topics=("alpha",),
        edges=edge_block(
            depends_on=["hinge — same presupposition, different route"],
            supports=["dep-c — the corollary follows from this reading too"],
        ),
    )
    make_claim(
        root, "dep-c", source="s2", note="Note Two", statement="Rests on dep-a",
        topics=("beta",),
        edges=edge_block(
            depends_on=["dep-a — a corollary of it"],
            supports=["sup-1 — the corollary is what the inscription records"],
        ),
    )
    # Supports are cross-source and cross-linked, so the fixture clears the
    # 1.5-edges-per-claim floor rather than tripping SPARSE_GRAPH.
    support_edges = [
        {"supports": ["hinge — corroborating material from a separate line"],
         "extends": ["sup-2 — carries the same reading further into the sequence"]},
        {"supports": ["hinge — corroborating material from a separate line",
                      "dep-b — the parallel case rests on the same material"],
         "extends": ["sup-3 — refines the dating the third source proposes"]},
        {"supports": ["hinge — corroborating material from a separate line",
                      "dep-a — independent confirmation of the dependent reading"]},
    ]
    for i, (src, edges) in enumerate(zip(("s1", "s2", "s3"), support_edges), start=1):
        make_claim(
            root, f"sup-{i}", source=src, note=f"Note {['One', 'Two', 'Three'][i - 1]}",
            statement=f"Independent support number {i}", topics=("alpha",),
            edges=edge_block(**edges),
        )
    make_claim(
        root, "contra-x", source="s2", note="Note Two", statement="The dating is early",
        confidence="high", topics=("gamma",),
        edges=edge_block(contradicts=["contra-y — reads the same stratum three centuries later"]),
    )
    make_claim(
        root, "contra-y", source="s3", note="Note Three", statement="The dating is late",
        confidence="high", topics=("gamma",),
        edges=edge_block(contradicts=["contra-x — reads the same stratum three centuries earlier"]),
    )
    make_claim(root, "orphan", source="s3", note="Note Three", statement="Connected to nothing",
               topics=("gamma",))

    if broken:
        make_claim(
            root, "broken-link", source="s1", statement="Points at a claim_id, not a slug",
            topics=("alpha",), edges=edge_block(supports=["s1.4 — the classic slug mistake"]),
        )
        make_claim(
            root, "one-sided", source="s2", note="Note Two", statement="Contradicts without reciprocity",
            confidence="high", topics=("gamma",),
            edges=edge_block(contradicts=["hinge — disputes the hinge without the return edge"]),
        )
    return root, manifest
