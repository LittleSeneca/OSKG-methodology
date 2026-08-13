---
tags: [type/spec, oskg-methodology, edges]
created: 2026-08-12
---

# Format contract — Edge types

Edges are the graph. Claims without them are a tagged pile of notes, and every Phase 4 analysis is a
function of edge structure alone.

## Base vocabulary

Four types, present in every project:

| Type | Meaning | Direction | Symmetry |
|---|---|---|---|
| `supports` | A provides evidence or reasoning for B | A → B | asymmetric |
| `contradicts` | A and B cannot both be true | A ↔ B | **reciprocal** |
| `extends` | A builds on, refines, or adds detail to B | A → B | asymmetric |
| `depends_on` | A requires B to be true | A → B | asymmetric |

`contradicts` is reciprocal and the gate enforces it: if A contradicts B, B contradicts A. The others are
directional and must not be mirrored — a mirrored `depends_on` is a cycle, and cycles corrupt the cascade
analysis.

## Domain extensions

Declared in `oskg.yaml` under `edge_types`. Use an extension only when the base four genuinely cannot carry
the distinction; every added type makes the graph harder to reason about and harder to compare across
projects.

| Type | Meaning | Use when |
|---|---|---|
| `challenged_by` | B is substantive criticism of A that stops short of asserting the opposite | Interpretive domains where scholars rarely say "X is wrong" outright |
| `operationalizes` | A is the concrete mechanism for abstract B | Architectural domains separating principle from implementation |
| `exception_to` | A is a specific carve-out from general rule B | Prescriptive rule systems |
| `replaces` | A supersedes B — errata, revision, later edition | Corpora with versioned authority |
| `cites` | A explicitly references B | Tracking influence separately from agreement |

Precedents: OSKG-YahWeh uses `challenged_by`; OSKG-ZeroTrust and OSKG-vCISO use `operationalizes`;
OSKG-DND uses `exception_to` and `replaces`.

## Choosing the type

Work down this list and take the first that fits:

1. Does A **supersede** B by authority (errata, later edition)? → `replaces`
2. Is A a **carve-out** from B's general case? → `exception_to`
3. Would A be **incoherent** if B were false? → `depends_on`
4. Do A and B make **incompatible** assertions about the same thing? → `contradicts`
5. Is A the **mechanism** for abstract B? → `operationalizes`
6. Does A **weaken** B without asserting its negation? → `challenged_by`
7. Does A **add detail** to B while agreeing? → `extends`
8. Does A give **reason to believe** B? → `supports`

The `supports` / `depends_on` confusion is the expensive one. `supports` is evidential: A makes B more
credible. `depends_on` is logical: B being false makes A meaningless. A hinge inventory built on
`depends_on` edges that should have been `supports` overstates fragility everywhere.

The `extends` / `supports` confusion is cheaper but pervasive: if A agrees with B and adds nothing new, it
is `supports`; if A agrees and carries the argument further, it is `extends`.

## Storage

Edges live in **two** places, and both are authoritative for different purposes:

1. **In the claim file**, under the Edges section — outbound only, human-readable, what Obsidian traverses.
2. **In `.oskg/edges.json`** — the parsed inventory, what analysis consumes.

`.oskg/edges.json` is derived; `oskg gate` regenerates it from the claim files and fails if it drifted.
Claim files are the source of truth so a hand edit in Obsidian is never silently discarded.

```json
{
  "generated": "2026-08-12T14:22:01Z",
  "edge_count": 412,
  "edges": [
    {
      "source": "zt-pdp-pep-model",
      "target": "zt-control-data-plane-split",
      "type": "supports",
      "justification": "PDP/PEP is the same separation in standards vocabulary",
      "cross_source": true
    }
  ]
}
```

`cross_source` is computed, not authored: true when the endpoints carry different `source/` tags. It is the
quality signal that matters most — a graph of intra-source edges has organized one book at a time and
connected nothing.

## Density targets

| Metric | Floor | Target | Meaning below floor |
|---|---:|---:|---|
| Edges per claim | 1.5 | 3.0+ | Claims were extracted but never connected |
| Cross-source share | 25% | 40%+ | Sources were processed in isolation |
| Orphan rate (0 edges) | — | <10% | Claims too idiosyncratic to connect, or clustering too narrow |
| Reciprocal `contradicts` | 100% | 100% | Gate failure, not a warning |

Below the floor, Phase 4 still runs but its output is not worth much: hinge inventories over a sparse graph
rank noise. `oskg gate --phase 3` reports these and fails the phase if a floor is breached.

## Anti-patterns

**Edge spam.** Connecting everything to everything produces a graph where nothing is load-bearing because
everything is. If a claim has more than ~8 outbound edges, most of them are `supports` edges that should
not exist.

**Justification-by-restatement.** `— supports [[x]]` is not a justification. The verification pass rejects
justifications that contain no content beyond the slug and the type.

**Direction drift.** In long batches, direction inverts — the model writes `A depends_on B` under B's
heading. The gate cannot catch semantic inversion, which is why Phase 3 verifies edges in a separate pass
from the one that proposed them.

**Cross-vocabulary blindness.** The same concept under two names in two sources produces zero edges between
two clusters that should be one. Tier-1-first ordering mitigates this by fixing vocabulary early; the
structural-gap analysis surfaces what it missed as suspiciously isolated subgraphs.
