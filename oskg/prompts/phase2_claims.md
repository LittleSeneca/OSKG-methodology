## Task — extract claims

Decompose these reading notes into claim files. **Read `{methodology_dir}/spec/claim-node.md` first** — the
format is normative, and the single most expensive mistake in this pipeline is made here.

Notes to process in this batch:
{note_list}

### Existing claims

{existing_claims}

Read that list before you start. New claims must edge into the existing graph, not sit beside it — a batch
that connects to nothing is a batch that has to be reworked in Phase 3 at higher cost.

### For each note

1. Read the note from `notes/`, especially its `## Candidate Claims` section. That section is the
   extraction target; you do not need the original source text.
2. Write **{claims_min}-{claims_max} claim files** into `notes/claims/`, one claim per file.
3. **Filename = the node ID.** Lowercase, hyphenated, 3-12 words describing the assertion, with the slug
   prefix `{slug_prefix}` — e.g. `pdp-pep-is-the-reference-model`, never `claim-047`.
4. Frontmatter exactly as `spec/claim-node.md` specifies: `claim_id`, `statement`, `confidence` (from
   `{confidence_levels}`), `confidence_rationale`, `claim_type` (from `{claim_types}`), `source_note`,
   `source_locator`, `created`, `status: active`, and tags — `type/claim`, `{tag}`, exactly one
   `source/<slug>`, at least one `evidence/<type>` from `{evidence_types}`, and **three or more**
   `topic/<topic>` from `{topics}`.
5. Body sections in order: The Claim · Evidence · Confidence · Stakes · Disagreement · Edges · Assessment.
   Every edge type in `{edge_types}` gets its bold subheading under `## Edges`, present even when empty.
6. Update the source note: set `claims_status: extracted` and `claims_count: N`, and replace its
   `## Candidate Claims` section with a compact list of wikilinks to the claim files you wrote.

### What makes a claim

- **Atomic** — one assertion. If it needs an "and", it is two claims.
- **Falsifiable in principle** — *"Fireball deals 8d6 fire damage"* is a claim; *"Fireball is good"* is not.
- **Sourced** — `source_locator` names the page or section. Never invent one; if the note does not give a
  locator, say so in the locator field rather than guessing.
- **Standalone** — readable without its neighbours.
- **Evidenced** — the `## Evidence` section is structured bullets or a table with real content. An empty or
  hand-waving Evidence section fails the gate.

### Edges in this phase

Add edges **within this batch** and **into the existing claims listed above**. Cross-source edge
construction across the whole graph is Phase 3's job; do not try to do it here.

**The slug rule, once more, because it is the failure that silently destroys graphs:** every `[[link]]`
between claims uses the *filename* you just wrote, not the `claim_id`. Obsidian renders a bad link as a
dead link rather than an error, so a batch that gets this wrong looks fine in the vault and produces an
empty graph in analysis. **Before you finish, list `notes/claims/` and verify every wikilink you wrote
resolves to a file that is actually there.** Do not report the batch complete until you have checked.

Every edge line is `- [[target-slug]] — justification`, and the justification names the argument. `— supports
[[x]]` restates the link and is rejected; `— the airport-checkpoint model is the same control/data split
under a different name` is a justification.

### Consistency

Later claims in a batch tend to get thinner treatment than earlier ones. Before you finish, re-read the
last claim you wrote against the first. If it is noticeably thinner, fix it.
