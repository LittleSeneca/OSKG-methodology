## Task — repair gate failures

The Phase {phase} quality gate found structural defects. Fix exactly these, and nothing else.

{failures}

### What each failure means

| Check | Fix |
|---|---|
| `BROKEN_LINK` / `DANGLING_EDGE` | A `[[link]]` points at no file. Wikilinks use the **filename slug**, not `claim_id`. List `notes/claims/`, find the right slug, and correct the link — or remove the edge if no such claim exists. |
| `MISSING_FIELDS` | Add the named frontmatter fields. See `{methodology_dir}/spec/claim-node.md`. |
| `BAD_CONFIDENCE` | Use one of `{confidence_levels}`. |
| `BAD_CLAIM_TYPE` | Use one of `{claim_types}`. |
| `BAD_SOURCE_TAG` | Exactly one `source/<slug>` tag. A claim drawn from two sources is two claims. |
| `THIN_EVIDENCE` | The `## Evidence` section needs real structured content from the source note — bullets or a table, not a sentence of paraphrase. |
| `SELF_EDGE` | Remove it. |
| `ASYMMETRIC_CONTRADICTION` | `contradicts` is reciprocal. Add the matching edge to the other claim file. |
| `DEPENDENCY_CYCLE` | Claims cannot circularly depend on each other. Re-type the weakest link in the cycle as `supports` or `extends`. |
| `UNKNOWN_EDGE_TYPE` | Only `{edge_types}` are legal. Re-type or remove. |
| `PHANTOM_CITATION` | A synthesis document cites a claim slug that does not exist. Replace it with a real one from `notes/claims/`, or drop the sentence. |
| `BROKEN_SOURCE_NOTE` | `source_note` must wikilink a real reading note under `notes/`. |
| `SPARSE_GRAPH` / `ISOLATED_SOURCES` | Not a per-file fix: add cross-source edges between claims that share topic tags but come from different sources. |

### Rules

- **Repair only. Do not rewrite.** Anything not named above is fine as it is; changing it costs another
  gate pass and risks breaking what already works.
- Never fix a broken link by deleting the claim it points from.
- After fixing, re-verify: list `notes/claims/` and confirm every `[[link]]` in every file you touched
  resolves to a real file.
