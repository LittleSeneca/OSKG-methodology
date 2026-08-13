---
tags:
  - type/meta
  - methodology
  - oskg
  - oskg-methodology
  - knowledge-graph
  - pipeline
created: 2026-08-12
updated: 2026-08-12
related:
  - "[[README]]"
  - "[[spec/claim-node]]"
  - "[[spec/edge-types]]"
  - "[[spec/quality-gates]]"
---

# METHODOLOGY — The OSKG Method

This is the canonical, domain-agnostic statement of the Open Source Knowledge Graph method. Seven prior
implementations — [OSKG-YahWeh](https://github.com/LittleSeneca/OSKG-YahWeh),
[OSKG-ZeroTrust](https://github.com/LittleSeneca/OSKG-ZeroTrust), OSKG-vCISO, OSKG-DND,
[OSKG-IBD](https://github.com/LittleSeneca/OSKG-IBD),
[OSKG-OnePageRules](https://github.com/LittleSeneca/OSKG-OnePageRules), and OSKG-GrahamBrooks — each
restated the method in their own `METHODOLOGY.md`, each with local drift. This document is the version they
should have been sharing, with the domain-specific parts factored out into a manifest.

Everything here is normative. Where a rule is a *should* rather than a *must*, it says so.

## 1. What an OSKG Is

An **Open Source Knowledge Graph** is a structured, queryable graph of claims extracted from a body of
sources, connected by typed edges, with every claim traceable to the passage that produced it.

Three principles define it:

1. **Structured extraction.** Sources are not summarized. They are decomposed into discrete, individually
   addressable claim nodes carrying explicit metadata — source, confidence, evidence type, topic.
2. **Typed edges.** Claims are connected through semantic relationships — supports, contradicts, extends,
   depends_on — producing a traversable argument graph rather than a flat pile of notes.
3. **Open and reproducible.** Every claim points at its source. Every edge is written down. The pipeline,
   the prompts, and the gates are version-controlled. Anyone with the same sources can reproduce, audit,
   or contest the graph.

The academic antecedent is the **Open Research Knowledge Graph** (ORKG) at Leibniz University Hannover,
which has run the same architecture over scientific literature since ~2019. The OSKG method is ORKG's
architecture at a different operating point: small corpora, high fidelity, one question at a time, and an
agent rather than a curation team.

### The distinction that does the work

A summary tells you what a source said. A claim graph tells you **what is load-bearing**.

That difference is the whole point. A narrative synthesis says "scholars agree that X." A graph says
"16 claims at HIGH+ confidence support X; zero at MEDIUM+ contradict it; and if X falls, 65 downstream
claims lose their support." The first is rhetoric. The second is structure, and it can be recomputed when
a new source arrives.

## 2. The Pipeline

```
topic → sources → reading notes → claims → typed-edge graph → synthesis → capstone
  P0       P0          P1           P2           P3              P4          P5
```

Phase order is fixed and enforced. Do not extract claims from a source you have not read into a note. Do
not build cross-source edges before the claims exist. Each phase boundary is a
[quality gate](spec/quality-gates.md) that must pass before the next phase starts.

| Phase | Name | Input | Output | LLM? |
|---|---|---|---|---|
| 0 | Scoping & Acquisition | topic string | `oskg.yaml`, `SOURCE-GUIDE.md`, `sources/` | yes |
| 1 | Reading Notes | sources | `notes/<domain>/*.md` | yes |
| 2 | Claims Extraction | reading notes | `notes/claims/*.md` | yes |
| 3 | Edge Construction | claims | edges inside claim files + `.oskg/edges.json` | yes |
| 4 | Structural Analysis | the graph | `notes/synthesis/phase*.md` | **analysis: no**, write-up: yes |
| 5 | Capstone | analyses | `notes/synthesis/capstone.md` | yes |

### Phase 0 — Scoping & Acquisition

Turn a topic string into a **scoped research plan**: the question the graph will answer, the domain type,
the tag taxonomy, the edge vocabulary, and a tiered source list.

Sources are tiered by their role in the graph, not by general quality:

| Tier | Role |
|---|---|
| 1 | **Canon.** The texts the graph cannot function without. Establish vocabulary and anchor cross-references. Process first — they are usually short and dense, and every later source references them. |
| 2 | **Core.** Substantive treatments that carry the bulk of the claims. |
| 3 | **Practitioner / community.** Implementation detail, dissent, and the view from the field. |
| 4 | **Adjacent.** Useful frameworks that are not strictly on-topic. Include only if budget allows. |

Tier 1 first is not a nicety. Claims extracted from canon become the edge targets that every later batch
attaches to; extracting them last produces a graph that is dense at the end and sparse at the start.

**Gate:** manifest validates; ≥1 Tier-1 source acquired; every source has provenance.

### Phase 1 — Reading Notes

Each source is read chapter by chapter (or section by section) into a structured note. The note is the
extraction substrate: it holds the author's arguments, evidence, and interactions with other sources, in a
shape that Phase 2 can decompose mechanically.

A reading note is not a summary either. It is an *indexed* rendering of the argument, with the passages
that will become claims already marked. See [spec/reading-note.md](spec/reading-note.md).

**Gate:** every note has valid frontmatter; every note names its source and locator; no note is a bare
abstract (minimum substance threshold).

### Phase 2 — Claims Extraction

Each reading note is decomposed into 5–10 discrete claims. A claim is:

- **atomic** — one assertion, not a paragraph
- **falsifiable in principle** — "Fireball deals 8d6 fire damage" is a claim; "Fireball is good" is not
- **sourced** — book, chapter, page or line
- **rated** — confidence plus the reasoning for that rating
- **standalone** — one file, readable without its neighbours

Claims live one-per-file in `notes/claims/`. The filename **is** the node ID. Every wikilink between claims
uses that filename slug, never the human-readable `claim_id`. This is the single most common failure in
practice and it silently destroys the graph — see [spec/claim-node.md](spec/claim-node.md).

Intra-source edges are added during extraction, while the source's internal argument structure is still in
context. Cross-source edges wait for Phase 3.

**Gate:** frontmatter complete; every wikilink resolves; claims-per-note within range; no claim with an
empty Evidence section.

### Phase 3 — Edge Construction

Cross-source edges in three passes:

1. **Cluster.** Group claims by shared topic tags. Edges are only plausible within a cluster; comparing all
   pairs is quadratic and mostly wasted.
2. **Detect.** For each cluster, propose typed edges. This is the one place where an LLM is genuinely doing
   inference rather than transcription, and it is where the graph earns its value.
3. **Verify.** Every proposed edge is checked: do both endpoints exist, is the type right, is the direction
   right, does the justification actually name the argument rather than restate the slugs?

Edge types are declared per project in the manifest. The base vocabulary is `supports`, `contradicts`,
`extends`, `depends_on`. Domains extend it: prescriptive rule systems add `exception_to` and `replaces`;
contested humanities domains add `challenged_by`; architectural domains add `operationalizes`. See
[spec/edge-types.md](spec/edge-types.md).

**Gate:** no dangling endpoints; no self-edges; `contradicts` is reciprocal; edge density above the floor;
orphan rate below the ceiling.

### Phase 4 — Structural Analysis

**This phase computes; it does not read.** Five analyses run over the parsed graph with no model calls:

| Analysis | Question |
|---|---|
| **Hinge inventory** | Which claims are load-bearing? Rank by transitive dependent count. |
| **Cascade trees** | If a top hinge is false, what else collapses? BFS to depth 4. |
| **Convergence points** | Where do independent sources agree with no live contradiction? |
| **Contradiction clusters** | Where do they genuinely conflict, and who is in each camp? |
| **Structural gaps** | Isolated subgraphs, single-source topics, bridge claims, sparse regions. |

The LLM is then asked to *write up* a computed result, not to discover it. That is the difference between a
synthesis you can audit and a synthesis you have to trust. It also makes Phase 4 nearly free, which matters
under a fixed budget.

**Gate:** analysis JSON produced; every claim referenced in a write-up exists in the graph.

### Phase 5 — Capstone

The culminating document: what does the graph show? What is settled, what is genuinely contested, what does
the architecture reveal about where evidence is thick and where it is thin, and where are the fragilities.

The capstone reports graph structure. It does not summarize sources, and it does not appeal to the
reputation of any author. Every quantitative statement in it must be recomputable from the graph.

## 3. Adaptive Scope Under a Fixed Budget

Prior OSKG projects fixed the scope and let the cost fall where it may. This one inverts that: **the budget
is the constraint and the scope adapts to it.**

The mechanism is measurement. Every model call runs through `hermes -z ... --usage-file`, which reports
actual dollars spent per call. The orchestrator keeps a ledger, and after the first batch of any phase it
knows the real cost per unit of work. It then sizes the remaining work to fit the phase's allocation:

```
affordable_units = phase_remaining_usd / observed_cost_per_unit
```

If the corpus does not fit, the orchestrator trims by tier — Tier 4 first, then Tier 3 — and records what
it dropped. A graph that covers Tiers 1–2 completely is worth more than one that covers all four tiers
badly, and either is worth more than one that stops halfway through Phase 2 with no edges and no synthesis.

Default allocation, as a fraction of the total:

| Phase | Share | Why |
|---|---:|---|
| 0 Scoping | 12% | Sized to acquire about as many sources as Phase 1 can afford to read. Under-fund it and every later phase starves; over-fund it and you buy sources nobody opens. |
| 1 Reading notes | 30% | The largest input-token cost; source text is long. |
| 2 Claims | 28% | The largest output-token cost; many files written. |
| 3 Edges | 16% | Clustered, so sublinear in claim count. |
| 4 Synthesis | 9% | Analysis is free; only the write-up costs. |
| 5 Capstone | 5% | One long call over already-condensed input. |

`oskg build --dry-run` chains these into an end-to-end projection and names the binding constraint,
because the interesting number is not any phase's allowance — it is which phase runs out first.

Unspent allocation rolls forward. A phase that comes in under budget widens every phase after it; a phase
that would exceed its ceiling stops cleanly at a batch boundary and hands the remainder to the next phase
rather than starving it.

**The cap is hard.** When the ledger reaches the total, the run stops, the state file records exactly where,
and `oskg build` resumes from there if the budget is raised.

## 4. Where Judgment Still Belongs to a Human

The pipeline runs unattended, which makes it important to be explicit about what it is *not* doing.

- **It does not adjudicate contested claims.** A `contradicts` edge records that two sources conflict. It
  does not decide who is right, and the synthesis is written not to imply that the better-connected side
  wins.
- **Confidence is the source's, not the graph's.** A HIGH-confidence claim is one the source asserts
  strongly with evidence it names. It is not a claim the graph vouches for.
- **Extraction accuracy is not perfect.** Automated claim extraction runs materially below human accuracy.
  The gates catch structural defects — missing fields, broken links, empty evidence — not misreadings.
  Spot-checking claims against sources is a human job, and the graph is built to make that easy: every
  claim names its locator.
- **Source selection is a judgment call the agent is making on your behalf.** Read `SOURCE-GUIDE.md` before
  trusting a graph. A corpus that omits the strongest counter-position produces a confident, wrong graph,
  and no amount of internal structure will reveal that.

## 5. Copyright and Fair Use

The method requires working with full-text copyrighted sources. The position, which each project restates
against its own corpus:

**Factor 1 — Purpose and character.** Decomposition into atomic claims with typed edges is transformative.
The output serves a different function (structural analysis) than the input (narrative exposition).

**Factor 2 — Nature of the work.** Corpora are predominantly factual, technical, and instructional. Works
of the U.S. government are public domain outright (17 U.S.C. § 105).

**Factor 3 — Amount.** Claims carry short excerpts and locators, not narrative structure or creative
expression. The minimum necessary for the transformative purpose.

**Factor 4 — Market effect.** A claim graph is useless as a substitute for its sources — it presupposes
them. If anything it drives demand toward them.

**Operationally:** full text lives in gitignored `_fulltext/` and `_txt/` directories and is never
committed or redistributed. Only the graph is published. `oskg` writes this `.gitignore` by default and
the Phase 1 gate fails if extracted full text appears outside those paths.

## 6. Relationship to ORKG

| Dimension | ORKG | OSKG |
|---|---|---|
| Scale | Millions of papers | 10–60 sources |
| Granularity | Paper- or finding-level | Chapter-level, 5–10 claims each |
| Extraction | LLM + curator sampling | LLM + programmatic gates + human spot-check |
| Fidelity | Statistical | Every claim carries a locator |
| Edge creation | Cross-paper inference + curator review | Tag clustering → LLM detection → verification pass |
| Query layer | SPARQL over RDF | Filesystem graph: wikilinks are edges, files are nodes |
| Synthesis | Comparative analysis across papers | Hinge/cascade/convergence/contradiction/gap analysis |
| Openness | CC-BY data, open platform | MIT, git-versioned, reproducible pipeline |

The convergence matters. ORKG demonstrates the architecture works for broad coverage; the OSKG projects
demonstrate it works at depth, in contested interpretive domains, and — across biblical studies, security
architecture, medicine, and tabletop game rules — that it is not domain-specific.

The Obsidian-vault-as-graph-database choice is pragmatic, not principled. Wikilinks are edges, files are
nodes, tag filtering is the query language, and the graph view is the visualization layer, all with no
infrastructure to stand up. The tradeoff is that formal queries require tag navigation instead of a query
language. At a few hundred to a few thousand claims this is fine. Past that, a real semantic layer would
earn its keep, and `oskg export` emits the graph as JSON for exactly that reason.

## 7. Key References

1. Jaradeh, M.Y., et al. (2019). "Open Research Knowledge Graph: Next Generation Infrastructure for
   Semantic Scholarly Knowledge." *K-CAP 2019*.
2. Auer, S., D'Souza, J., & Farfar, K. (2025). "Open Research Knowledge Graph: A Large-Scale
   Neuro-Symbolic Knowledge Organization System."
3. Oelen, A., et al. (2025). "Organizing Scholarly Knowledge with the Open Research Knowledge Graph."
   *Nature Scientific Data*.
4. Tan, A. & D'Souza, J. (2026). "Diagnosing structural failures in LLM-based evidence extraction for
   meta-analysis." arXiv:2602.10881.
5. Aggarwal, P. (2026). "Interactive Knowledge Extraction: A Human-in-the-Loop Approach for PDF Structuring
   and Knowledge Graph Integration." Leibniz University Hannover.

## 8. Related Documents

- [README](README.md) — what this repo is and how to run it
- [spec/claim-node.md](spec/claim-node.md) — the claim file format contract
- [spec/edge-types.md](spec/edge-types.md) — edge vocabulary and selection rules
- [spec/reading-note.md](spec/reading-note.md) — the Phase 1 note format
- [spec/tag-taxonomy.md](spec/tag-taxonomy.md) — the four tag layers
- [spec/project-manifest.md](spec/project-manifest.md) — `oskg.yaml` schema
- [spec/quality-gates.md](spec/quality-gates.md) — what must pass at each boundary
- [spec/budget-model.md](spec/budget-model.md) — allocation, rollover, and the hard cap
