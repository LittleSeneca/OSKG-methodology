## Task — write up a computed analysis

**The analysis is already done.** It was computed from the graph structure, not inferred, and it is in
`.oskg/analysis.json`. Your job is to write up **{analysis_name}** — to explain what the computed result
means, not to discover it.

This distinction is the whole reason the pipeline works this way. Every number below is recomputable from
the graph by anyone who has it. Do not produce a number that is not in the analysis, and do not adjust one
because it seems wrong.

### The computed result

{analysis_payload}

### Write

`notes/synthesis/{output_file}` with frontmatter (`tags: [type/synthesis, {tag}, phase4]`, `created`,
`analysis: {analysis_key}`) and this structure:

{output_structure}

### Rules

1. **Every quantitative statement comes from the analysis above.** If you want to say "16 claims support
   this", the analysis must say 16. The gate cross-checks.
2. **Cite claims by their filename slug in wikilinks** — `[[{example_slug}]]`. A slug that is not in the
   analysis fails the gate as a phantom citation, so do not reach for one from memory.
3. **Report structure; do not adjudicate.** Where two sources contradict, the graph records the
   disagreement — it does not settle it. Write "the graph records a live disagreement between X and Y, with
   both sides held at high confidence", not "X is probably right". Connectivity is not correctness: a
   better-connected claim is one more sources engaged with, which is not evidence that it is true.
4. **Say what the structure does not show.** A hinge with many dependents is load-bearing *in this corpus*.
   If the corpus is thin somewhere, the analysis will show it as a gap, and that belongs in the write-up.
5. Length: {target_length}. Dense and specific. No throat-clearing, no restating the methodology.
