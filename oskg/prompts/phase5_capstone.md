## Task — write the capstone

The culminating document: **what does this graph show?**

Everything you need has been computed. Read:

- `.oskg/analysis.json` — the five structural analyses
- `notes/synthesis/*.md` — the write-ups of each
- `SOURCE-GUIDE.md` — the corpus, and what was deliberately left out
- `PROGRESS.md` — including any scope trims made under budget pressure

### Graph at a glance

{metrics_block}

### Write `notes/synthesis/capstone.md`

Frontmatter: `tags: [type/synthesis, {tag}, capstone, phase5]`, `created`, `question`.

Structure:

1. **The question** — what the graph was built to answer, in one paragraph.
2. **What is settled** — convergences: claims multiple independent sources support with no confident
   contradiction. Name them, with the source counts. This is the graph's strongest output.
3. **What is genuinely contested** — the fault lines where both sides are held at high confidence. Present
   each as a disagreement with two positions, not as a question you resolve. Name who is in each camp.
4. **What the graph rests on** — the hinges, and what collapses if each is wrong. Give the cascade sizes.
   This is the section that tells a reader where the whole picture is fragile.
5. **Where the evidence is thin** — orphans, single-source topics, isolated components, fragile bridges.
   Say what a next build should acquire to fix each.
6. **What this graph cannot tell you** — the limitations, stated plainly:
   - source selection was automated; the corpus reflects choices recorded in `SOURCE-GUIDE.md`
   - confidence ratings are the *sources'* strength of assertion, not the graph's endorsement
   - claim extraction was automated and spot-checking against sources is a human job
   - any scope trimmed under budget, named specifically from `PROGRESS.md`
   - contradiction edges record disagreement and do not resolve it
7. **How to use and extend this** — the queries that pay off, and the sources to add next.

### Rules

1. **Report structure, not reputation.** Not "the consensus among scholars is X" but "N claims at high
   confidence support X, from M independent sources, with no confident contradiction".
2. Every number traces to `.oskg/analysis.json`. Every `[[slug]]` is a real claim file — the gate fails a
   citation that resolves to nothing, and inventing a plausible slug is the characteristic failure here.
3. Cite at least 10 distinct claims. A capstone that names no claims is an essay, not a synthesis.
4. **Do not pick winners in the contested section.** The graph makes disagreement visible; that is its
   contribution. A reader who wants a verdict can weigh the evidence themselves — the graph gives them the
   shape of it.
5. Length: 1,800-3,500 words. Written for someone who knows the domain but has not read the corpus.
