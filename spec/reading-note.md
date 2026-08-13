---
tags: [type/spec, oskg-methodology, notes]
created: 2026-08-12
---

# Format contract — Reading note

A reading note is the Phase 1 output for one chapter, section, or document. It is the substrate Phase 2
decomposes, and its job is to make that decomposition mechanical.

A reading note is **not** a summary. A summary compresses; a reading note *indexes*. The passages that will
become claims are already marked, with their locators, before Phase 2 runs.

## Location

`notes/<domain>/<Source Short Name> — <Locator> — <Title>.md`

Domain directories come from `oskg.yaml` (`note_domains`). Typical sets:

- research corpora: `concepts/`, `history/`, `questions/`, `synthesis/`, `evidence-briefs/`
- professional corpora: `grc/`, `secops/`, `devops/`, `architecture/`, `leadership/`
- rules corpora: `rules/`, `classes/`, `spells/`, `monsters/`, `items/`

`notes/claims/` and `notes/synthesis/` always exist and are never used for reading notes.

## Frontmatter

```yaml
---
tags:
  - type/note              # required, exact
  - <project-tag>          # required
  - source/<source-slug>   # required, exactly 1
  - topic/<topic>          # required, ≥1
source_title: "<full work title>"     # required
source_author: "<author(s)>"          # required
source_year: 2020                     # required (or "n.d.")
source_tier: 1                        # required, 1-4
locator: "<Ch 2, pp. 6-19>"           # required
created: 2026-08-12                   # required
claims_status: pending                # required: pending | extracted | partial
claims_count: 0                       # required, set by Phase 2
---
```

`claims_status` is the Phase 2 work queue. The orchestrator selects `pending` notes in tier order, so this
field — not a separate ledger — is the resumable state for extraction.

## Body

```markdown
# <Source Short Name> — <Locator> — <Title>

**Work:** <Author>, *<Title>*, <Publisher>, <Year>
**Tier:** <n> — <role in the graph>
**Locator:** <chapter, pages>

## What This Section Argues

Two to four sentences. The thesis, in the author's terms, not yours.

## Argument Structure

The moves the author makes, in order, with locators. This is the spine Phase 2 walks.

1. **<Move>** (p. N) — what is asserted and on what basis
2. **<Move>** (p. N) — ...

## Candidate Claims

The extraction targets. 5-10 per note. Each becomes one claim file in Phase 2.

### Claim 1: <one-sentence assertion>
- **Locator:** p. N
- **Evidence:** what the author offers
- **Confidence:** <rating> — <why>
- **Type:** <claim_type>

### Claim 2: ...

## Cross-References

Where this section engages other sources in the corpus. These become Phase 3 edge candidates, so name the
source and the nature of the engagement.

| Source | Engagement | Locator |
|---|---|---|
| [[<other note>]] | extends / disputes / assumes | p. N |

## Evidence Types Present

Which `evidence/` tags the claims from this note will carry, and why.

## Open Questions

What this section raises and does not settle. Feeds `notes/questions/`.
```

The **Candidate Claims** section is the contract between phases. Phase 2 does not re-read the source; it
reads this section. If it is thin, the claims are thin, and no downstream phase recovers.

## Depth calibration

**The tier sets the style; the text actually on disk sets the ceiling.** Phase 1 computes the word count of
each source's extracted text and passes a binding budget into the prompt — roughly one note per 3,000 words
and no more than one candidate claim per 400 words.

That ceiling exists because tier alone is not enough. A `partial` acquisition of a Tier-2 monograph can be
a 1,700-word review of it; given Tier-2 treatment ("every substantive chapter, 5-10 claims each") it
produced 37 claims where the full papers yielded 16-29 each. See `spec/quality-gates.md` on `OVER_EXTRACTED`.

Within that ceiling, depth follows tier:

| Tier | Treatment |
|---|---|
| 1 | Every chapter or section. 6-10 candidate claims each. This is the canon; the vocabulary and the edge anchors come from here. |
| 2 | Every substantive chapter. 5-8 candidate claims. Skip prefaces, glossaries, and appendices. |
| 3 | Only chapters carrying new material. 3-6 claims. A practitioner book that restates the canon for 200 pages yields two notes, not twelve. |
| 4 | One note for the whole work, capturing the framework it contributes. |

Reference works — monster catalogs, spell lists, control catalogs — get one index note plus on-demand
extraction. Do not write 400 reading notes for 400 stat blocks.

## Validation

`oskg gate --phase 1` checks:

| Check | Failure |
|---|---|
| Frontmatter parses and all required fields present | `MISSING_FIELDS` |
| `source_tier` in 1-4 | `BAD_TIER` |
| Has a `## Candidate Claims` section | `NO_CANDIDATES` |
| Candidate claim count within the tier's range | `THIN_NOTE` / `BLOATED_NOTE` |
| Every candidate claim has a locator | `NO_LOCATOR` |
| Note body over the substance threshold | `STUB_NOTE` |
| No source full text under `notes/` | `FULLTEXT_LEAK` |

`FULLTEXT_LEAK` is a copyright guard, not a style rule: extracted source text belongs in gitignored
`sources/**/_txt/` and `sources/**/_fulltext/`, never in a committed note.
