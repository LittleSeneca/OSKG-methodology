---
tags: [type/spec, oskg-methodology, gates]
created: 2026-08-12
---

# Format contract — Quality gates

A gate is a **programmatic** check at a phase boundary. No model calls, no judgment, no cost. Gates catch
structural defects — the failures that are cheap to detect and expensive to discover in Phase 4.

Gates do not check whether a claim is *right*. They check that it is *well-formed*: fields present, links
resolving, evidence non-empty, edges reciprocal where they must be. Correctness is a human spot-check, and
the graph is built to make that easy.

## Why programmatic

The prior projects used an LLM quality-review pass (`extract-loop.sh` Phase 2). It worked, but it cost as
much as the extraction it reviewed, and it was unreliable in exactly the case that matters: it would report
PASS on a batch with broken wikilinks because it did not actually stat the files.

Every check below is a `for` loop over parsed markdown. Running the full gate suite over 400 claims takes
well under a second and costs nothing, which is why it runs after every batch rather than every phase.

## Failure handling

```
gate fails → collect failures → targeted repair prompt (≤ gates.repair_attempts)
           → re-gate → still failing?
                        strict: true  → abort, record state
                        strict: false → record failures in PROGRESS.md, continue
```

The repair prompt carries the exact failure list — file, check, detail — and nothing else. Repair is
cheaper than re-extraction and much cheaper than discovering the defect in Phase 4.

## Gate 0 — Scoping

| Check | ID | Severity |
|---|---|---|
| `oskg.yaml` validates | `MANIFEST_INVALID` | fatal |
| ≥1 Tier-1 source in `SOURCE-GUIDE.md` | `NO_CANON` | fatal |
| Every source has title, author, year, tier, role | `INCOMPLETE_SOURCE` | error |
| Every source has an acquisition status | `NO_ACQUISITION_STATUS` | warn |
| `topics` seeded with ≥3 entries | `THIN_TOPICS` | warn |

## Gate 1 — Reading notes

| Check | ID | Severity |
|---|---|---|
| Frontmatter parses, required fields present | `MISSING_FIELDS` | error |
| `source_tier` in 1-4 | `BAD_TIER` | error |
| `## Candidate Claims` present | `NO_CANDIDATES` | error |
| Candidate count within tier range | `THIN_NOTE` / `BLOATED_NOTE` | warn |
| Every candidate has a locator | `NO_LOCATOR` | warn |
| Body over substance threshold | `STUB_NOTE` | error |
| `source/` tag matches a source in the manifest | `UNKNOWN_SOURCE` | error |
| No source full text under `notes/` | `FULLTEXT_LEAK` | **fatal** |

`FULLTEXT_LEAK` is fatal regardless of `strict`. It is a copyright control, not a quality preference:
committing extracted source text is the one failure that cannot be repaired after a push.

## Gate 2 — Claims

| Check | ID | Severity |
|---|---|---|
| Frontmatter parses | `YAML_PARSE_ERROR` | error |
| Required fields present and non-empty | `MISSING_FIELDS` | error |
| `confidence` in the allowed set | `BAD_CONFIDENCE` | error |
| `claim_type` in the manifest's set | `BAD_CLAIM_TYPE` | error |
| ≥`min_topic_tags` topic tags, ≥1 evidence tag | `THIN_TAGS` | warn |
| Exactly one `source/` tag | `BAD_SOURCE_TAG` | error |
| Every claim wikilink resolves | `BROKEN_LINK` | **error** |
| `source_note` resolves | `BROKEN_SOURCE_NOTE` | error |
| Evidence ≥ `min_evidence_chars` | `THIN_EVIDENCE` | warn |
| No self-edge | `SELF_EDGE` | error |
| Claims per note within `claims_per_note` | `BAD_CLAIM_COUNT` | warn |
| Topic tag on <3 claims | `SUSPECTED_SYNONYM` | warn |
| Slug unique | `DUPLICATE_SLUG` | fatal |

`BROKEN_LINK` is the check the whole gate suite exists for. Obsidian renders an unresolved wikilink as a
dead link rather than an error, so a batch that used `claim_id` instead of the filename slug looks fine in
the vault and produces an empty graph in analysis.

## Gate 3 — Edges

| Check | ID | Severity |
|---|---|---|
| Both endpoints exist and are `status: active` | `DANGLING_EDGE` | error |
| Edge type in the manifest's `edge_types` | `UNKNOWN_EDGE_TYPE` | error |
| `contradicts` is reciprocal | `ASYMMETRIC_CONTRADICTION` | error |
| No `depends_on` cycle | `DEPENDENCY_CYCLE` | error |
| Justification present and not slug-restatement | `EMPTY_JUSTIFICATION` | warn |
| Edges per claim ≥ `min_edges_per_claim` | `SPARSE_GRAPH` | error |
| Cross-source share ≥ `min_cross_source_ratio` | `ISOLATED_SOURCES` | error |
| Orphan share ≤ `max_orphan_ratio` | `HIGH_ORPHAN_RATE` | warn |
| `.oskg/edges.json` matches the claim files | `EDGE_INDEX_DRIFT` | error (auto-repaired) |

`DEPENDENCY_CYCLE` is fatal to the cascade analysis rather than to the run: BFS over a cyclic `depends_on`
graph does not terminate. The gate reports the cycle and `oskg analyze` breaks it at the lowest-confidence
edge, recording the break.

## Gate 4 — Synthesis

| Check | ID | Severity |
|---|---|---|
| `.oskg/analysis.json` produced | `NO_ANALYSIS` | fatal |
| Every claim slug cited in a write-up exists | `PHANTOM_CITATION` | error |
| Every quantitative statement matches the analysis | `UNBACKED_NUMBER` | warn |
| All five analyses present | `INCOMPLETE_ANALYSIS` | error |

`PHANTOM_CITATION` catches the characteristic synthesis failure: a write-up that invents a plausible claim
slug. The check is a set membership test, and it is the reason Phase 4 computes before it writes.

## Gate 5 — Capstone

| Check | ID | Severity |
|---|---|---|
| Capstone exists and is over the length floor | `NO_CAPSTONE` | fatal |
| Cites ≥10 distinct claims | `THIN_CITATION` | warn |
| Every cited slug exists | `PHANTOM_CITATION` | error |
| Names its own limitations | `NO_LIMITATIONS` | warn |

## Running gates

```bash
oskg gate                 # every gate up to the current phase
oskg gate --phase 2       # one phase
oskg gate --fix           # gate, then one LLM repair pass on failures
oskg gate --json          # machine-readable, for CI
```

Exit codes: `0` clean (warnings allowed), `1` errors present, `2` fatal, `3` project not found.
