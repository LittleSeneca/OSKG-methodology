---
tags: [type/spec, oskg-methodology, budget]
created: 2026-08-12
---

# Format contract — Budget model

The budget is the constraint that makes an unattended run safe. Everything else in the pipeline adapts to
it.

## Where the numbers come from

`hermes -z <prompt> --usage-file <path>` writes a JSON report after every one-shot run — **including when
the run fails**, which is what makes the accounting total:

```json
{
  "estimated_cost_usd": 0.00997281,
  "cost_status": "estimated",
  "cost_source": "official_docs_snapshot",
  "input_tokens": 22922,
  "output_tokens": 2,
  "cache_read_tokens": 0,
  "cache_write_tokens": 0,
  "reasoning_tokens": 0,
  "total_tokens": 22924,
  "api_calls": 1,
  "model": "deepseek-v4-pro",
  "provider": "deepseek",
  "session_id": "20260812_130032_9c171f",
  "completed": true,
  "failed": false,
  "service_tier": null
}
```

`estimated_cost_usd` is estimated from a provider pricing snapshot, not billed. Treat it as accurate to
within a few percent and do not treat the cap as an accounting guarantee — it is a governor, not an
invoice.

**One-shot only.** `--usage-file` is not available on `hermes chat`, so every orchestrated call uses `-z`.
That has a consequence worth knowing: `-z` also ignores `--skills`, so skills are not preloaded. The
orchestrator instead points the agent at the spec file it needs (`Read spec/claim-node.md and follow it`),
which keeps the project self-contained and costs one file read.

## The ledger

`.oskg/ledger.jsonl`, append-only, one line per call:

```json
{"ts":"2026-08-12T13:00:32Z","phase":2,"stage":"extract","label":"batch-3","cost_usd":0.412,"input_tokens":48211,"output_tokens":9022,"api_calls":14,"model":"deepseek-v4-pro","session_id":"20260812_130032_9c171f","ok":true,"attempt":1}
```

Append-only and never rewritten, so a crashed run's spend is still counted on resume. `oskg status` reads
it; nothing else writes it.

## Allocation and rollover

Each phase gets a fraction of the pool:

```
pool = total_usd - reserve_usd
ceiling(p) = allocation[p] * pool + rollover_into(p)
rollover_into(p) = Σ over completed phases q < p of (ceiling(q) - spent(q))
```

Default shares: 12% / 30% / 28% / 16% / 9% / 5%. Phase 0 is funded to acquire about as many sources as
Phase 1 can afford to read — under-fund it and every later phase starves on a thin corpus; over-fund it and
you pay to acquire sources nobody opens.

A phase that finishes under budget widens every phase after it. A phase that would exceed its ceiling stops
at the next batch boundary and passes its remaining work to the trimmer rather than eating the next phase's
allocation.

`reserve_usd` is held out of the pool entirely and released only for Phase 5. A run that spends its last
dollar on edge construction and cannot write a capstone has produced nothing a human can read.

## The hard cap

Before every call:

```python
if ledger.spent() + estimate > total_usd:
    raise BudgetExhausted
```

`estimate` is an EWMA of observed cost for that stage, seeded conservatively and updated after every call
(α = 0.4 — recent batches are more predictive than early ones, which run against an empty graph). The
estimate is deliberately biased high: overshooting the cap is worse than stopping one batch early.

**One exception.** Phase 0's scoping call is admitted against the total cap only, never against Phase 0's
share. It is the run's precondition — it writes the vocabulary and the corpus every later dollar is spent
against — so a small phase share must not be able to skip it. A run that scopes nothing and proceeds
anyway is worse than one that stops.

**Stages bill separately.** A phase with two kinds of work — Phase 0's scoping and its acquisition — records
each under its own stage, so each keeps its own estimate. Averaging a $0.055 scoping call with a $0.079
acquisition call mispredicts both.

On `BudgetExhausted` the run stops, `state.json` records the phase and the pending work list, and
`oskg build` resumes from that point if the cap is raised.

## Adaptive sizing

This is what turns "$20" into "a complete graph" rather than "a third of a graph."

After the first batch of a phase, cost per unit is known. The orchestrator then computes:

```
affordable = floor(phase_remaining / cost_per_unit)
```

and compares it to the work outstanding. If the work does not fit, it trims — in this order, because each
step costs less than the one before it:

1. **Drop the lowest tier.** Raise `scope.min_tier`. Tier 4 is adjacent material; Tier 3 is
   community/practitioner. Tiers 1-2 are never dropped.
2. **Reduce depth.** Lower `claims_per_note` toward its floor; take fewer chapters from Tier 3 sources.
3. **Narrow the corpus.** Drop the lowest-ranked sources within the surviving tiers.
4. **Stop cleanly.** Finish the current batch, mark the rest unprocessed, proceed to the next phase.

Step 4 matters most. A graph with 120 claims, full edges, and a capstone beats one with 380 claims, no
edges, and no synthesis. **The pipeline always reaches Phase 5**, even on a budget that cannot cover the
planned corpus, because a truncated graph that has been analyzed is usable and an unanalyzed one is not.

Every trim is recorded in `PROGRESS.md` under "Scope trims". A graph that silently covered less than it
claimed would be worse than useless.

## Reference costs

Measured with `deepseek-v4-pro` via Hermes, August 2026. Your mileage varies with model, provider, and
source length.

| Stage | Unit | Seed | Measured | Notes |
|---|---|---:|---:|---|
| Fixed overhead | per call | — | ~$0.010 | System prompt + tool definitions, ~23k input tokens |
| `scope` | one call | $0.12 | **$0.055** | 14 API calls, 37k in / 41k out |
| `sources` | ~6 sources | $0.20 | **$0.079** | 44 API calls, 71k in / 43k out — search, download, extract |
| `notes` | one source | $0.25 | **$0.047** | 6 API calls, 35k in / 35k out → 3 reading notes |
| `extract` | 3 notes | $0.25 | — | 15-30 claim files written; output-heavy |
| `edges` | one cluster | $0.12 | — | Scales with cluster size, not claim count |
| **Phase 4 analysis** | — | **$0.00** | **$0.00** | Pure computation |
| `synthesis` | one write-up | $0.08 | — | Over an already-computed result |
| `capstone` | one call | $0.15 | — | Long, but over condensed input |
| `repair` | one gate pass | $0.06 | **$0.044** | 13 API calls, targeted at named failures |

Measured column: `deepseek-v4-pro` via Hermes, August 2026, on a real build
(*the Antikythera mechanism*, 7 sources, 6 acquired). Seeds sit 2-5x above the measurements on purpose. An
agent turn re-sends its growing context on every tool call, so a stage's cost is dominated by how many tool
calls it makes rather than by its prompt length — and that varies far more than the prompt does. A seed
that is too high costs one conservatively-sized first batch and is corrected within it; a seed that is too
low makes the projection a user reads before starting into a lie.

At $20 with the default allocation, expect roughly **20-25 sources, 60-70 reading notes, 300-600 claims,
400-1,400 edges, five analyses, and a capstone** — the same order as OSKG-ZeroTrust (50 notes, 406 claims),
which took multiple supervised sessions to build by hand.

Run `oskg build --dry-run` for the projection at your budget. It chains the phases — Phase 1 cannot read
more sources than Phase 0 acquired — and names which phase is the binding constraint, which is more useful
than any single phase's allowance.

## Fixed overhead is the tax to watch

Every call pays ~$0.01 before it does any work. At 200 calls that is $2 — 10% of a $20 budget spent on
system prompts. This is why batching matters: 3 notes per extraction call rather than 1 cuts overhead by
two thirds.

The counter-pressure is context. Large batches degrade — later items in a batch get thinner treatment than
earlier ones, a failure the prior projects hit and explicitly checked for ("are later claims as thorough as
the first?"). Batch size defaults to 3 because that is where the prior projects landed after hitting both
walls.

## Commands

```bash
oskg status                 # phase, spend, remaining, per-phase burn
oskg status --ledger        # every call
oskg build --budget 20      # set the cap for this run
oskg build --dry-run        # plan and estimate, no calls, no spend
```

`--dry-run` prints the plan and the projected cost per phase without making a single call. Run it first.
