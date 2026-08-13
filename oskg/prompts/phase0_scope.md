## Task — scope the graph

Turn the topic into a research plan. This one call determines what every later dollar buys, so think about
the corpus before you write it down.

### Step 1 — Sharpen the question

The topic is `{topic}`. Restate it as a single question the finished graph will answer. Good questions are
answerable from evidence and admit disagreement: *"What does the weight of evidence show about how X
works?"* — not *"Everything about X"*.

### Step 2 — Choose the vocabulary

Pick the domain-specific vocabulary this graph needs.

- **claim_types** (4-8): the kinds of assertion this domain makes. Historical corpora need
  `definitional / causal / chronological / interpretive`; technical corpora need
  `architectural / implementation / threat / governance`; rule systems need `rule / exception / definition`.
- **evidence_types** (4-8): the kinds of warrant. `archaeological / textual / inscriptional` for ancient
  history; `rct / observational / mechanistic` for medicine; `primary-standard / empirical / vendor` for
  technical domains. Include a type for commercially or ideologically motivated sources if the corpus has
  any — a reader needs to weight those differently.
- **note_domains** (3-6): subdirectories of `notes/`. Never `claims` or `synthesis` — those are reserved.
- **topics** (10-20): the seed topic tags. These drive Phase 3 clustering, so they must partition the
  subject matter, not just label it. Lowercase, hyphenated.
- **edge_types_extra** (0-3, from `{allowed_extra_edges}`): only if the base four genuinely cannot carry a
  distinction this domain makes. Read `spec/edge-types.md` before adding any.
- **slug_prefix**: 2-4 characters prefixed to every claim slug, e.g. `zt-`. Or empty.

### Step 3 — Build the tiered source list

Target **{target_sources} sources**, tiered by their role in the graph rather than by general quality:

| Tier | Role |
|---|---|
| 1 | Canon. The graph cannot function without these. Standards, foundational texts, primary sources. Short and dense wherever possible — they set the vocabulary every later source is compared against. |
| 2 | Core. The substantive treatments that carry most of the claims. |
| 3 | Practitioner / community. Implementation detail, dissent, the view from the field. |
| 4 | Adjacent. Useful frameworks not strictly on topic. |

Research this properly — search, check publisher catalogs and citation counts, look at what practitioners
and scholars in the field actually cite. Do not generate a plausible-looking bibliography from memory:
every entry must be a real work you have confirmed exists, with a real author and year.

**Include the strongest counter-position.** A corpus that omits the best argument against the mainstream
view produces a confident, wrong graph, and no amount of internal structure will reveal that. If the field
is contested, Tier 1 or 2 must contain at least one source arguing the minority side.

For each source record: slug (lowercase-hyphenated, author-year or document ID), title, author, year, tier,
one-sentence role in the graph, and how it could be acquired (`open-access`, `web`, `library`, `purchase`).

### Step 4 — Write two files

**`.oskg/phase0/plan.json`** — exactly this shape:

```json
{{
  "question": "...",
  "domain_type": "domain",
  "slug_prefix": "xx-",
  "claim_types": ["..."],
  "evidence_types": ["..."],
  "note_domains": ["..."],
  "topics": ["..."],
  "edge_types_extra": [],
  "estimated_notes": 40,
  "sources": [
    {{"slug": "author-2020", "title": "...", "author": "...", "year": 2020, "tier": 1,
      "role": "...", "acquisition": "open-access", "url": ""}}
  ]
}}
```

**`SOURCE-GUIDE.md`** — the human-readable reading list. A `## Tier N` heading per tier, each followed by a
pipe table with columns exactly `| slug | title | author | year | tier | role | status |`. Set `status` to
`pending` for every source. Above the tables, write 2-3 paragraphs on why this corpus and not another,
including what you deliberately left out and why — that paragraph is what a reader checks before trusting
the graph.

Aim for a corpus of about {target_sources} sources and roughly {target_notes} reading notes total.
