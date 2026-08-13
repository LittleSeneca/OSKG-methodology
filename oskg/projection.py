"""What will $N actually buy?

A dry run on a fresh project can only *walk* Phase 0 — every later phase depends
on a source list Phase 0 has not written yet. Rather than reporting "0 calls" and
looking broken, `--dry-run` prints this projection.

The projection is a **chain**, not six independent estimates. Phase 1 cannot
read more sources than Phase 0 acquired; Phase 2 cannot extract more notes than
Phase 1 wrote. Reporting each phase's allowance in isolation would promise 192
reading notes from a corpus of 13 sources. The bottleneck is the interesting
number, so it is named explicitly.

These are seed estimates. A live run measures real cost after its first batch
and re-sizes scope from there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .budget import Budget
from .manifest import Manifest

__all__ = ["project_run", "format_projection", "PhaseProjection"]

# Artifacts one call of each phase produces, from the batch sizes the drivers use.
SOURCES_PER_ACQUIRE_CALL = 6  # phases/phase0.ACQUIRE_BATCH
NOTES_PER_SOURCE = 3.0  # tier-weighted average: Tier 1-2 many, Tier 3-4 one or two
NOTES_PER_EXTRACT_CALL = 3  # phases/phase2.ClaimsPhase.batch_size
CLAIMS_PER_CLUSTER = 12.0  # typical multi-source topic cluster
EDGES_PER_CLAIM = (1.2, 2.4)  # after Phase 3 over a connected corpus

_PHASE_NAMES = {
    0: "Scoping and acquisition",
    1: "Reading notes",
    2: "Claims extraction",
    3: "Edge construction",
    4: "Structural analysis",
    5: "Capstone",
}


@dataclass
class PhaseProjection:
    phase: int
    name: str
    allowance_usd: float
    calls: int
    yield_text: str
    limited_by: str = ""


def _calls(allowance: float, unit_cost: float) -> int:
    return max(0, int(allowance / unit_cost)) if unit_cost > 0 else 0


def project_run(manifest: Manifest, budget: Budget) -> dict[str, Any]:
    """Chained per-phase projection for the configured budget."""
    allow = {n: budget.phase_base(n) for n in range(6)}

    # Phase 0: one scope call, the rest on acquisition.
    scope_cost = budget.estimate("scope")
    acquire_calls = _calls(max(0.0, allow[0] - scope_cost), budget.estimate("sources"))
    sources = acquire_calls * SOURCES_PER_ACQUIRE_CALL

    # Phase 1: one call per source, capped by what Phase 0 acquired.
    read_capacity = _calls(allow[1], budget.estimate("notes"))
    sources_read = min(sources, read_capacity)
    notes = int(sources_read * NOTES_PER_SOURCE)

    # Phase 2: three notes per call, capped by what Phase 1 wrote.
    extract_capacity = _calls(allow[2], budget.estimate("extract")) * NOTES_PER_EXTRACT_CALL
    notes_extracted = min(notes, extract_capacity)
    lo, hi = manifest.claims_per_note
    claims = (int(notes_extracted * lo), int(notes_extracted * hi))

    # Phase 3: one call per topic cluster, capped by how many clusters a corpus
    # this size actually produces.
    cluster_capacity = _calls(allow[3], budget.estimate("edges"))
    clusters = min(cluster_capacity, max(1, int(claims[1] / CLAIMS_PER_CLUSTER)))
    coverage = clusters / cluster_capacity if cluster_capacity else 1.0
    edges = (
        int(claims[0] * EDGES_PER_CLAIM[0] * min(1.0, coverage or 1.0)),
        int(claims[1] * EDGES_PER_CLAIM[1]),
    )

    phases = [
        PhaseProjection(
            0, _PHASE_NAMES[0], allow[0], 1 + acquire_calls, f"~{sources} sources researched"
        ),
        PhaseProjection(
            1, _PHASE_NAMES[1], allow[1], sources_read, f"~{notes} reading notes",
            limited_by="sources acquired" if sources < read_capacity else "budget",
        ),
        PhaseProjection(
            2, _PHASE_NAMES[2], allow[2], max(1, notes_extracted // NOTES_PER_EXTRACT_CALL),
            f"{claims[0]}-{claims[1]} claims",
            limited_by="notes written" if notes <= extract_capacity else "budget",
        ),
        PhaseProjection(
            3, _PHASE_NAMES[3], allow[3], clusters,
            f"{edges[0]}-{edges[1]} edges across {clusters} clusters",
            limited_by="claims extracted" if clusters < cluster_capacity else "budget",
        ),
        PhaseProjection(
            4, _PHASE_NAMES[4], allow[4], min(5, _calls(allow[4], budget.estimate("synthesis"))),
            "5 analyses (computed free) + write-ups",
        ),
        PhaseProjection(5, _PHASE_NAMES[5], allow[5], 1, "1 capstone"),
    ]

    constrained = [p for p in phases[1:4] if p.limited_by and p.limited_by != "budget"]
    return {
        "total_usd": manifest.total_usd,
        "reserve_usd": manifest.reserve_usd,
        "phases": phases,
        "sources": sources,
        "notes": notes,
        "notes_extracted": notes_extracted,
        "claims": claims,
        "edges": edges,
        "clusters": clusters,
        "bottleneck": constrained[0] if constrained else None,
    }


def format_projection(p: dict[str, Any]) -> str:
    lines = [
        f"Projected for a ${p['total_usd']:.2f} budget "
        f"(${p['reserve_usd']:.2f} reserved so the capstone always gets written):",
        "",
        "  Phase                        allowance   ~calls   yields",
        "  " + "─" * 68,
    ]
    for ph in p["phases"]:
        lines.append(
            f"  {ph.phase}. {ph.name:<24} ${ph.allowance_usd:7.2f}   {ph.calls:>6}   {ph.yield_text}"
        )

    claims_lo, claims_hi = p["claims"]
    edges_lo, edges_hi = p["edges"]
    lines += [
        "",
        f"  End state: ~{p['sources']} sources → ~{p['notes']} reading notes → "
        f"{claims_lo}-{claims_hi} claims",
        f"             → {edges_lo}-{edges_hi} typed edges → 5 structural analyses → 1 capstone",
    ]
    bottleneck = p["bottleneck"]
    if bottleneck is not None:
        lines += [
            "",
            f"  Bottleneck: phase {bottleneck.phase} ({bottleneck.name}) is limited by "
            f"{bottleneck.limited_by},",
            "  not by its allowance. Raising the budget widens the phase before it first.",
        ]
    lines += [
        "",
        "  Seed estimates, biased high. A live run measures real cost after its first batch",
        "  and re-sizes scope to fit — trimming by tier, lowest first, never Tiers 1-2.",
    ]
    return "\n".join(lines)
