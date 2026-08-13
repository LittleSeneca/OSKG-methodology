---
tags: [type/spec, oskg-methodology, manifest]
created: 2026-08-12
---

# Format contract — `oskg.yaml`

The manifest is what makes the method domain-agnostic. Everything a prior OSKG project hard-coded into its
own `METHODOLOGY.md` — edge vocabulary, evidence types, note domains, claim types — lives here instead, so
the pipeline code never knows what domain it is in.

Written by Phase 0, read by every later phase, committed to the project repo.

## Schema

```yaml
oskg_version: 1                    # int, required. Manifest schema version.

project: OSKG-ZeroTrust            # str, required. Repo/directory name.
topic: "Zero Trust architecture: principles, implementation patterns, and evidence"
question: "What does the weight of evidence show about how to implement Zero Trust?"
slug: zerotrust                    # str, required. Short identifier.
tag: oskg-zerotrust                # str, required. The project tag on every file.
slug_prefix: "zt-"                 # str, optional. Prefixed to every claim slug.
domain_type: domain                # domain | person | corpus

created: 2026-08-12                # ISO date, required.

# ── Vocabulary ────────────────────────────────────────────────────────
edge_types:                        # list[str], required. Must include the base four.
  - supports
  - contradicts
  - extends
  - depends_on
  - operationalizes                # domain extension

claim_types:                       # list[str], required.
  - definitional
  - architectural
  - implementation
  - threat
  - migration
  - governance

evidence_types:                    # list[str], required. Become evidence/<x> tags.
  - primary-standard
  - empirical
  - architectural
  - practitioner
  - vendor

note_domains:                      # list[str], required. Subdirectories of notes/.
  - concepts
  - architecture
  - history
  - questions

topics:                            # list[str], seeded in P0, grown in P2.
  - zt-architecture
  - zt-policy
  - zt-identity

# ── Scope ─────────────────────────────────────────────────────────────
scope:
  target_sources: 18               # int. Sized to budget in P0, trimmed by tier as needed.
  target_notes: 50
  target_claims: 400
  claims_per_note: [5, 10]         # [min, max]
  min_tier: 1                      # Lowest tier to attempt. Raised when budget is tight.

# ── Budget ────────────────────────────────────────────────────────────
budget:
  total_usd: 20.00                 # float, required. HARD cap across the whole run.
  allocation:                      # Fractions of total. Must sum to 1.0.
    phase0: 0.12
    phase1: 0.30
    phase2: 0.28
    phase3: 0.16
    phase4: 0.09
    phase5: 0.05
  rollover: true                   # Unspent allocation widens later phases.
  reserve_usd: 0.50                # Held back so P5 can always finish.

# ── Model ─────────────────────────────────────────────────────────────
model:
  default: deepseek-v4-pro         # Passed to hermes -m. null = hermes config default.
  provider: deepseek               # Passed to hermes --provider. Requires model.
  per_phase: {}                    # Optional override, e.g. {phase4: claude-opus-5}

# ── Gates ─────────────────────────────────────────────────────────────
gates:
  min_edges_per_claim: 1.5
  min_cross_source_ratio: 0.25
  max_orphan_ratio: 0.10
  min_topic_tags: 1
  min_evidence_chars: 120
  repair_attempts: 1               # LLM repair passes before a gate failure is recorded.
  strict: false                    # true = a failed gate aborts the run.
```

## Field rules

**`edge_types`** must be a superset of `[supports, contradicts, extends, depends_on]`. Analysis assumes
those four exist; `depends_on` in particular drives the hinge and cascade analyses.

**`allocation`** must sum to 1.0 ± 0.001 and every phase key must be present. Rebalance rather than
dropping a phase — a zero allocation for phase 3 produces a claim pile, not a graph.

**`budget.total_usd`** is the hard ceiling for the whole run, not per phase and not per invocation. The
ledger enforces it before every call.

**`reserve_usd`** is subtracted from the pool available to phases 0-4, so Phase 5 can always produce a
capstone. A run that spends everything on extraction and cannot write its conclusion has wasted the whole
budget.

**`model.provider`** requires `model.default` — `hermes` rejects `--provider` without `--model`, because
carrying a configured model across to a provider that may not host it fails confusingly at request time.

**`scope.min_tier`** is how budget pressure is applied. Phase 0 sizes the corpus; if measured costs come in
high, the orchestrator raises `min_tier` (dropping Tier 4, then Tier 3) and records the trim in
`PROGRESS.md` rather than silently covering less.

**`gates.strict`** defaults to false so an unattended run degrades rather than dies. Set true for a run you
intend to publish.

## Validation

`oskg validate` checks the manifest before any phase runs:

| Check | Failure |
|---|---|
| `oskg_version` known | `UNSUPPORTED_VERSION` |
| Required keys present | `MISSING_KEY` |
| `edge_types` ⊇ base four | `INCOMPLETE_EDGE_TYPES` |
| `allocation` sums to 1.0 | `BAD_ALLOCATION` |
| `allocation` covers phases 0-5 | `MISSING_PHASE_ALLOCATION` |
| `total_usd` > 0 and > `reserve_usd` | `BAD_BUDGET` |
| `provider` set without `default` model | `PROVIDER_WITHOUT_MODEL` |
| `claims_per_note` is `[min, max]`, min ≤ max | `BAD_RANGE` |
| `tag` matches `^[a-z0-9-]+$` | `BAD_TAG` |
| `note_domains` non-empty, no reserved names | `BAD_NOTE_DOMAINS` |

`claims/` and `synthesis/` are reserved and may not appear in `note_domains`.

## YAML subset

`oskg` ships a dependency-free parser so it runs on a bare `python3` with no venv. It reads the subset the
manifest and frontmatter need, and **nothing more**:

- `key: scalar` — string, int, float, bool, null
- `key:` followed by an indented `- item` list of scalars
- one level of nested mapping (`budget:` → `total_usd:`), two for `allocation:`
- `[a, b]` inline lists of scalars
- `{}` empty inline mapping
- `#` comments, quoted strings, `---` document markers

Not supported, and rejected loudly rather than misparsed: anchors, aliases, multi-document streams, block
scalars (`|`, `>`), nested inline mappings, and lists of mappings. If a manifest needs those, it is doing
something the schema does not intend.
