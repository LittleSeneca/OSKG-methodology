# OSKG-methodology

**One prompt in. A complete, audited knowledge graph out. Under a budget you set.**

```bash
oskg build "the archaeology and interpretation of Göbekli Tepe" --budget 20
```

That command scopes the question, finds and tiers the sources, reads them into structured notes, decomposes
those notes into individually-addressable claims, connects the claims with typed edges, computes the
structural analysis, and writes a capstone — unattended, resumable, and stopping at $20.

---

## What this repo is

Two things:

1. **The method.** [METHODOLOGY.md](METHODOLOGY.md) is the canonical, domain-agnostic statement of the
   Open Source Knowledge Graph method, distilled from seven implementations that each restated it with
   local drift. [`spec/`](spec/) holds the normative format contracts — claim nodes, edge types, reading
   notes, tags, the manifest, the gates, the budget model.

2. **The machine.** [`oskg/`](oskg/) is a dependency-free Python toolkit that runs the method end to end
   through the [Hermes](https://github.com/LittleSeneca/hermes) agent, with real per-call cost accounting
   and a hard spend cap.

### Prior implementations

| Project | Domain | Result |
|---|---|---|
| [OSKG-YahWeh](https://github.com/LittleSeneca/OSKG-YahWeh) | Origins of Yahweh, biblical monotheism | 17 monographs → 149 notes → 723 claims → capstone |
| [OSKG-ZeroTrust](https://github.com/LittleSeneca/OSKG-ZeroTrust) | Zero Trust architecture | 33 sources → 50 notes → 406 claims |
| OSKG-vCISO | Security leadership (GRC/SecOps/DevOps) | 50-60 sources, powers the Paul agent |
| OSKG-DND | D&D 5e rules | Rules corpus for an AI DM |
| [OSKG-IBD](https://github.com/LittleSeneca/OSKG-IBD) | IBD/SIBO medical literature | Capstone published as an epub |
| [OSKG-OnePageRules](https://github.com/LittleSeneca/OSKG-OnePageRules) | Grimdark Future | Rules graph |
| OSKG-GrahamBrooks | Person-knowledge graph | Private agent context |

Each took supervised sessions across days. This repo exists to make the eighth one a single command.

## The pipeline

```
topic → sources → reading notes → claims → typed-edge graph → synthesis → capstone
  P0       P0          P1           P2           P3              P4          P5
```

| Phase | Produces | Model calls |
|---|---|---|
| 0 Scoping | `oskg.yaml`, `SOURCE-GUIDE.md`, tiered corpus | yes |
| 1 Reading notes | `notes/<domain>/*.md` | yes |
| 2 Claims | `notes/claims/*.md`, one claim per file | yes |
| 3 Edges | typed edges in claim files + `.oskg/edges.json` | yes |
| 4 Analysis | hinges, cascades, convergence, contradictions, gaps | **no** — pure computation |
| 5 Capstone | `notes/synthesis/capstone.md` | yes |

Phase 4 is the design's centre of gravity. The five structural analyses are computed from the parsed graph
with zero model calls; the model is then asked to *write up* a computed result rather than to discover one.
That is what makes the synthesis auditable — and nearly free, which is what makes the budget work.

## A validated run

The first end-to-end build, on *the Antikythera mechanism: construction, function, and dating*:

| | |
|---|---|
| **Cost** | **$2.09** across 36 calls (cap was $4.00) |
| **Wall clock** | 5.5 hours, unattended |
| **Corpus** | 6 sources researched and acquired, 4 read |
| **Graph** | 17 reading notes → **109 claims** → **291 edges** (2.67/claim, 50% cross-source) |
| **Structure** | 0 orphans, 1 connected component, 25 hinges, 14 convergence points, 1 contradiction cluster |
| **Output** | 5 analysis write-ups + a 2,238-word capstone citing 46 claims |
| **Gates** | 1-5 all pass |

The capstone found what the graph made visible and a reader would not: the corpus splits into two
near-mirror camps — reconstruction/function versus eclipse/dating — joined by a **single bridge claim**
about Babylonian eclipse records. It reported the dating dispute without resolving it, and noted that it is
not even a *genuine unknown*, because neither side holds its position confidently. It also flagged that one
convergence's "three-source breadth masks a single-author load."

That is the whole argument for computing the synthesis instead of writing it.

## Install

Requires Python 3.9+ and [Hermes](https://github.com/LittleSeneca/hermes) on your `PATH`. **No Python
dependencies** — it runs on a bare system `python3` with no venv, by design.

```bash
git clone https://github.com/LittleSeneca/OSKG-methodology.git
cd OSKG-methodology
make install          # symlinks `oskg` into ~/.local/bin
```

Or run it in place:

```bash
python3 -m oskg build "your topic" --budget 20
```

To let Hermes trigger it conversationally:

```bash
make install-skill    # copies skills/oskg-pipeline into ~/.hermes/skills/research/
```

Then `hermes chat` and say *"build me a knowledge graph about the Bronze Age collapse"*.

## Usage

```bash
# Plan and estimate. No model calls, no spend. Run this first.
oskg build "the Bronze Age collapse" --budget 20 --dry-run

# Build for real. Resumable — re-run after an interrupt and it picks up.
oskg build "the Bronze Age collapse" --budget 20

# Where did it get to and what did it cost?
oskg status
oskg status --ledger

# Run the gates by hand
oskg gate --phase 2
oskg gate --fix

# Recompute the structural analysis (free)
oskg analyze
oskg analyze --json > analysis.json

# Export the graph for a real query layer
oskg export --format json
```

Projects are created as sibling directories: `oskg build` from `~/Projects/Personal/OSKG-methodology`
writes `~/Projects/Personal/OSKG-BronzeAgeCollapse/`, git-initialized, committed per phase.
**Nothing is pushed anywhere** unless you pass `--github`.

### Resuming and adjusting

```bash
oskg build --resume                       # continue in the current project dir
oskg build --resume --budget 35           # raise the cap and continue
oskg build --resume --from-phase 3        # redo edges onward
```

**It is slow.** Each call is a full agent turn doing real research — the validated run above took 5.5 hours
for $2.09. Budget most of a day for a $20 build, start it and leave it. An interrupt costs nothing but
time.

## How the budget works

Every call runs as `hermes -z <prompt> --usage-file <tmp>`, which reports actual dollars per call — even
when the call fails. Those land in an append-only ledger at `.oskg/ledger.jsonl`.

- Each phase gets a fraction of the pool; unspent allocation **rolls forward**.
- A reserve (default $0.50) is held back so Phase 5 can always write a capstone.
- After the first batch of a phase, cost-per-unit is measured, and the remaining scope is **sized to fit**.
- If it does not fit, scope is trimmed by tier — Tier 4 first, never Tiers 1-2 — and every trim is recorded
  in `PROGRESS.md`.
- The cap is hard. At the ceiling the run stops cleanly and records exactly where.

The design choice underneath: **a 120-claim graph with full edges and a capstone beats a 380-claim pile
with neither.** The pipeline always reaches Phase 5.

See [spec/budget-model.md](spec/budget-model.md) for measured per-stage costs. At $20 with defaults, expect
roughly 20-25 sources, 60-70 reading notes, 300-600 claims, 400-1,400 edges, five analyses, and a capstone.
`--dry-run` prints the projection for your budget and names the binding constraint.

## What it does not do

Worth stating plainly, because it runs unattended:

- **It does not adjudicate.** A `contradicts` edge records a conflict; it does not pick a winner, and the
  synthesis is written not to imply the better-connected side is right.
- **Confidence is the source's, not the graph's.** HIGH means the source asserts it strongly with evidence
  it names — not that the graph vouches for it.
- **Gates check form, not truth.** They catch missing fields, broken links, empty evidence, asymmetric
  contradictions. They cannot catch a misreading. Spot-checking is a human job, and every claim carries a
  locator to make it quick.
- **Source selection is a judgment the agent makes for you.** Read `SOURCE-GUIDE.md` before trusting a
  graph. A corpus missing the strongest counter-position yields a confident, wrong graph, and no amount of
  internal structure reveals that.

## Repository layout

```
OSKG-methodology/
├── METHODOLOGY.md          # the canonical method
├── spec/                   # normative format contracts
│   ├── claim-node.md       ├── tag-taxonomy.md    ├── quality-gates.md
│   ├── edge-types.md       ├── project-manifest.md └── budget-model.md
│   └── reading-note.md
├── oskg/                   # the toolkit (stdlib only)
│   ├── cli.py              # the `oskg` command
│   ├── pipeline.py         # the orchestrator
│   ├── phases/             # one driver per phase, 0-5
│   ├── prompts/            # the stage prompt templates
│   ├── manifest.py         # oskg.yaml
│   ├── budget.py           # ledger, allocation, the hard cap
│   ├── runner.py           # hermes -z + --usage-file
│   ├── state.py            # resumable run state
│   ├── graph.py            # claims and typed edges
│   ├── gates.py            # the programmatic quality gates
│   ├── analysis.py         # the five structural analyses
│   ├── projection.py       # "what will $N buy?"
│   ├── scaffold.py         # new-project templates
│   ├── frontmatter.py      # markdown + frontmatter parsing
│   └── yamlish.py          # the YAML subset, so there are no dependencies
├── bin/oskg                # launcher — no install step needed
├── skills/oskg-pipeline/   # Hermes skill — conversational trigger
└── tests/                  # stdlib unittest, no network
```

## License

MIT — see [LICENSE](LICENSE). The method and the tooling are open. The corpora they build over are not
redistributed: full source text stays in gitignored `_fulltext/` and `_txt/` directories and is never
committed. See [METHODOLOGY.md §5](METHODOLOGY.md#5-copyright-and-fair-use).
