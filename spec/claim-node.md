---
tags: [type/spec, oskg-methodology, claims]
created: 2026-08-12
---

# Format contract — Claim node

A claim node is one markdown file in `notes/claims/`. One claim per file, no exceptions.

## The slug rule

**The filename is the node ID.** Every wikilink that points at a claim uses the filename stem — never the
human-readable `claim_id`.

```
✅ [[claim-el-and-yahweh-originally-distinct]]     ← filename stem
❌ [[claim-kaufmann-ri-8.4]]                        ← claim_id; resolves to nothing
```

This is the single most common defect in practice. A `claim_id` looks like an identifier, so extraction
reaches for it, and the resulting wikilinks silently point at nothing. Obsidian renders them as unresolved
links rather than erroring, the graph looks populated, and every downstream analysis is quietly wrong. The
Phase 2 gate fails the batch on a single unresolved claim wikilink for this reason.

Slug rules:

- lowercase, ASCII, hyphen-separated
- 3–12 words, descriptive of the assertion — `zt-pdp-pep-model`, not `claim-047`
- prefixed with the project's `slug_prefix` from `oskg.yaml` when one is set
- stable once written; renaming a claim means rewriting every inbound wikilink

## Frontmatter

```yaml
---
tags:
  - type/claim              # required, exact
  - <project-tag>           # required, from oskg.yaml `tag`
  - evidence/<kind>         # required, ≥1
  - source/<source-slug>    # required, exactly 1
  - topic/<topic>           # required, ≥1 (≥3 after enrichment)
claim_id: "<source-abbrev>-<locator>.<n>"   # required, human-readable, NOT the link target
statement: "<one sentence, the assertion itself>"   # required
confidence: "<very-low|low|low-medium|medium|medium-high|high|very-high>"   # required
confidence_rationale: "<why that rating>"   # required
claim_type: "<from oskg.yaml claim_types>"  # required
source_note: "[[<reading note filename stem>]]"  # required
source_locator: "<book/chapter/page or section/line>"  # required
created: 2026-08-12         # required
updated: 2026-08-12         # optional
status: active              # required: active | superseded | retracted
---
```

`status` is load-bearing: analysis skips anything that is not `active`, so a claim can be retired without
being deleted and without orphaning its inbound edges.

## Body

```markdown
# <claim_id>: <statement>

**Source:** [[<reading note>]] — <Author>, *<Work>*, <year>, <locator>

## The Claim

The assertion in full, in the source's terms. Quote where the exact wording matters.

## Evidence

What the source offers in support. Structured — bullets or a table, not one undifferentiated paragraph.
An empty or hand-waving Evidence section fails the Phase 2 gate.

## Confidence

**Rating:** <HIGH>
**Rationale:** Why this rating. What would raise it, what would lower it.

## Stakes

What follows if this is true. What breaks if it is false. Why the claim is worth having as a node.

## Disagreement

**Who disagrees:** Named sources and their counter-argument, or `_None identified._`
**Alternative reading:** A different reading of the same evidence, or `_None identified._`

## Edges

**Depends on:**
- [[other-claim-slug]] — why the dependency holds

**Supports:**
- [[other-claim-slug]] — what this contributes

**Contradicts:**

**Challenged by:**

**Extends:**

## Assessment

Your read. Where this sits relative to the rest of the graph.
```

Edge headings for every type in the project's `edge_types` are always present, empty when unused. Fixed
headings make the parser total and stop the LLM from inventing a heading it likes better.

## Edge lines

```markdown
- [[target-slug]] — <justification naming the argument>
```

The justification is required and must name the substance. `— supports [[zt-pdp-pep-model]]` restates the
link and tells a later reader nothing; `— the airport-checkpoint model is the same control/data split
Gilman & Barth argue for under a different name` is a justification. The Phase 3 verification pass rejects
justifications that only restate slugs.

## Worked example

```markdown
---
tags:
  - type/claim
  - oskg-zerotrust
  - evidence/primary-standard
  - source/nist-sp-800-207
  - topic/zt-architecture
  - topic/zt-policy
claim_id: "nist207-ch2.4"
statement: "The PDP/PEP model is the abstract architecture underlying all ZTA deployments"
confidence: "high"
confidence_rationale: "Appears in every implementation surveyed — Google's Access Proxy, ZTNA products, SDP controller/gateway splits. NIST states it as the reference model rather than one option among several."
claim_type: "architectural"
source_note: "[[NIST 800-207 — Ch2 — Zero Trust Basics]]"
source_locator: "NIST SP 800-207, §2, pp. 6-9"
created: 2026-07-24
status: active
---

# nist207-ch2.4: The PDP/PEP model is the abstract architecture underlying all ZTA deployments

**Source:** [[NIST 800-207 — Ch2 — Zero Trust Basics]] — Rose, Borchert, Mitchell & Connelly, *NIST SP 800-207*, 2020, §2

## The Claim

Access is granted through a Policy Decision Point and a Policy Enforcement Point. Every subject passes
through this gateway, and the implicit trust zone behind it must be kept as small as possible.

## Evidence

- The airport-security analogy: all passengers pass the checkpoint (PDP/PEP); the boarding area is the
  implicit trust zone.
- A PDP/PEP cannot apply policy beyond its position in the traffic flow (§2, p. 8).
- Moving PDP/PEPs closer to resources shrinks the implicit trust zone.

## Confidence

**Rating:** HIGH
**Rationale:** NIST presents this as the reference model, and every deployment surveyed in §3 instantiates
it. Lowered from very-high because NIST does not survey non-inline enforcement designs.

## Stakes

If PDP/PEP is the only model, ZTA requires an inline enforcement point per resource — a scalability
problem. Alternatives (service-mesh-distributed enforcement) exist but are out of scope here.

## Disagreement

**Who disagrees:** Gilman & Barth describe the same split as control plane / data plane. The concepts are
equivalent; the terminology is not, which matters for cross-source edge construction.
**Alternative reading:** _None identified._

## Edges

**Depends on:**

**Supports:**
- [[zt-control-data-plane-split]] — PDP/PEP is the same separation NIST states in standards vocabulary

**Contradicts:**

**Challenged by:**

**Extends:**

## Assessment

The most important architectural concept in 800-207. Everything in §3 elaborates it, which makes this a
hinge candidate — expect high transitive dependent count.
```

## Validation

`oskg gate --phase 2` checks, per claim file:

| Check | Failure |
|---|---|
| Frontmatter parses | `YAML_PARSE_ERROR` |
| All required fields present and non-empty | `MISSING_FIELDS` |
| `confidence` in the allowed set | `BAD_CONFIDENCE` |
| `claim_type` in the manifest's set | `BAD_CLAIM_TYPE` |
| ≥1 `topic/` and ≥1 `evidence/` tag | `THIN_TAGS` |
| Exactly one `source/` tag | `BAD_SOURCE_TAG` |
| Every claim wikilink resolves to a file in `notes/claims/` | `BROKEN_LINK` |
| Evidence section over the substance threshold | `THIN_EVIDENCE` |
| No self-edge | `SELF_EDGE` |
| `source_note` resolves to a real reading note | `BROKEN_SOURCE_NOTE` |
