## Task — build cross-source edges

Connect claims that come from different sources. The clustering is already done: these claims share topic
tags, which is why they are in front of you together. **Read `{methodology_dir}/spec/edge-types.md`
first.**

**Cluster {cluster_name}** — {claim_count} claims across {source_count} sources.

{claim_table}

### What to do

Read the claim files listed above from `notes/claims/`. For each pair that is genuinely related, add an
edge to the **source** claim's `## Edges` section under the right subheading.

Work down this list and take the first type that fits:

1. Does A **supersede** B by authority — errata, later edition? → `replaces`
2. Is A a **carve-out** from B's general case? → `exception_to`
3. Would A be **incoherent** if B were false? → `depends_on`
4. Do A and B make **incompatible** assertions about the same thing? → `contradicts`
5. Is A the **mechanism** for abstract B? → `operationalizes`
6. Does A **weaken** B without asserting its negation? → `challenged_by`
7. Does A **add detail** to B while agreeing? → `extends`
8. Does A give **reason to believe** B? → `supports`

Only types in `{edge_types}` are legal here.

The `supports` / `depends_on` distinction is the one that matters most. `supports` is evidential — A makes
B more credible. `depends_on` is logical — if B is false, A is meaningless. The hinge analysis is built on
`depends_on`, so getting this wrong overstates fragility across the whole graph.

`contradicts` is **reciprocal**: add it to both claim files, in both directions. The gate fails a one-sided
contradiction. Every other type is directional — never mirror one.

### What you are looking for

**Cross-source edges above all.** Two claims from the same source connected to each other organize one
book; two claims from different sources connected to each other are what the graph is for. Prioritize
pairs whose `source/` tags differ.

**Vocabulary mismatches.** The same idea under two names in two sources is the most valuable edge you can
find and the easiest to miss. "Control plane / data plane" and "PDP/PEP" are the same architecture; "Late
Bronze collapse" and "Sea Peoples event" may be the same referent. Look for these deliberately.

**Real contradictions.** Sources rarely say "X is wrong". They say "X's reading is possible but the
evidence favours another". That is `challenged_by` if it is available, `contradicts` only when the two
assertions genuinely cannot both hold.

### Restraint

**Do not connect everything to everything.** A graph where every claim supports every other claim has no
load-bearing structure, and the whole point of Phase 4 is to find load-bearing structure. If a claim ends
up with more than about eight outbound edges, most of them should not be there.

Aim for **{target_edges} new edges** from this cluster. Fewer, better-justified edges beat more edges.

### Before you finish

Verify every `[[link]]` you added resolves to a real file in `notes/claims/`. Use the filename slug, never
the `claim_id`.
