---
tags: [type/spec, oskg-methodology, tags]
created: 2026-08-12
---

# Format contract — Tag taxonomy

Tags are the query language. Obsidian has no `WHERE` clause, so a consistent tag layer is what makes
"every HIGH-confidence archaeological claim that supports the Asherah position" answerable at all.

## The four layers

Every node carries tags from four layers. Namespaced prefixes keep them sortable, greppable, and
non-colliding.

| Layer | Prefix | Cardinality | Example |
|---|---|---|---|
| **Type** | `type/` | exactly 1 | `type/claim`, `type/note`, `type/synthesis`, `type/index`, `type/meta` |
| **Source** | `source/` | exactly 1 | `source/nist-sp-800-207`, `source/gilman-barth-2017` |
| **Evidence** | `evidence/` | ≥1 | `evidence/archaeological`, `evidence/primary-standard` |
| **Topic** | `topic/` | ≥1, target ≥3 | `topic/zt-architecture`, `topic/risk-management` |

Plus one **project tag**, unprefixed, on every file: `oskg-zerotrust`, `oskg-dnd`. It is what makes a vault
holding several graphs separable.

### Type

Fixed and closed. Analysis dispatches on it, so an invented value makes a file invisible.

`type/claim` · `type/note` · `type/synthesis` · `type/index` · `type/meta` · `type/question` · `type/source`

### Source

One per file, derived from the source slug in `SOURCE-GUIDE.md`. Author-year for books
(`source/gilman-barth-2017`), document identifier for standards (`source/nist-sp-800-207`), publisher-work
for rulebooks (`source/wotc-phb-2014`).

This tag computes `cross_source` on every edge, which is the graph's headline quality metric. It must be
exactly one — a claim drawn from two sources is two claims.

### Evidence

What *kind* of warrant backs the claim. Domain-specific, declared in `oskg.yaml`. This is the layer that
lets a reader weight claims without knowing the literature.

| Domain | Vocabulary |
|---|---|
| Humanities / history | `textual`, `archaeological`, `inscriptional`, `comparative`, `iconographic`, `onomastic` |
| Security / technical | `primary-standard`, `empirical`, `architectural`, `practitioner`, `vendor`, `regulatory` |
| Medical | `rct`, `observational`, `meta-analysis`, `case-report`, `mechanistic`, `clinical-guideline` |
| Rules / prescriptive | `rules-text`, `errata`, `designer-statement`, `community-consensus` |

`evidence/vendor` earns its place: a commercially motivated claim is not disqualified, but it must be
weightable. The same is true of `evidence/practitioner` — experience-based assertion, not measurement.

### Topic

The open layer, and the one that does the real work. Topic tags drive Phase 3 clustering: claims are only
compared for edges within a shared topic, so topic sparsity means edge sparsity.

Seeded in Phase 0 from the scoping pass, then grown in Phase 2. The target is ≥3 topic tags per claim.
Below that, claims cluster with nothing and the graph fragments.

**Enrichment.** Claims that finish extraction with ≤2 topic tags are enriched programmatically:

1. Compute the topic co-occurrence matrix across all claims.
2. For each thin claim, rank candidate tags by co-occurrence affinity with the tags it already has.
3. Accept a candidate only if the claim's own body text contains one of that tag's keywords.

The keyword check is what stops affinity from hallucinating. Co-occurrence alone will happily add
`topic/compliance` to every claim that mentions a framework; requiring a literal keyword hit keeps it
honest. `oskg enrich-tags` implements this, and it is free — no model calls.

## Hierarchical topics

Topics may nest with `/`: `topic/iam/authentication`, `topic/iam/authorization`. Obsidian treats
`topic/iam` as a prefix match over both, so nesting buys a coarse and a fine view of the same claim for
free. Do not nest more than two levels; past that, filtering costs more than it returns.

## Value tiers

Corpora with a natural ordinal — spell level, monster CR, item price, control baseline — get a `tier-`
layer with a **flat, grep-friendly** shape:

```
tier-cantrip, tier-1st … tier-9th
tier-cr-0-4, tier-cr-5-10, tier-cr-11-16, tier-cr-17-plus
tier-gp-0-50, tier-gp-51-500 …
```

Flat rather than nested so that one `grep tier-cr-` finds every CR-banded note across every domain
directory. OSKG-DND is the precedent.

## Rules

1. **Lowercase, hyphen-separated, ASCII.** `topic/risk-management`, never `topic/Risk_Management`.
2. **Singular.** `topic/control`, not `topic/controls`.
3. **Prefix everything except the project tag.** An unprefixed tag is a future collision.
4. **Never rename a tag by hand.** `oskg retag <old> <new>` rewrites every occurrence; a partial rename
   silently splits a cluster in two and Phase 3 will never join them.
5. **New topic tags need a home.** Add to `oskg.yaml` `topics:` when a batch introduces one, so later
   batches reuse it instead of coining a synonym.

Rule 5 is the one that decays without enforcement. Synonym drift — `topic/iam` in batch 1,
`topic/identity` in batch 4 — produces two clusters that should be one and edges that never get proposed.
`oskg gate --phase 2` reports topic tags appearing on fewer than 3 claims as suspected synonyms.
