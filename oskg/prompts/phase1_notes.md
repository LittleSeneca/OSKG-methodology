## Task — write reading notes

Read these sources into structured notes. **Read `{methodology_dir}/spec/reading-note.md` first** — the
format is normative and the gate checks it.

{source_table}

Source text is in `sources/*/_txt/<slug>.txt` where acquisition succeeded. If a source's text is missing or
marked `unavailable` in `SOURCE-GUIDE.md`, skip it and say so — do not write a note from memory.

### For each source

1. **Survey it.** Find the chapter or section structure. Do not read it end to end into context — locate
   the substantive parts and read those.
2. **Split it by tier**, then write one note per unit into `notes/{{domain}}/`:

| Tier | Units | Candidate claims each |
|---|---|---|
| 1 | every chapter or section | 6-12 |
| 2 | every substantive chapter; skip prefaces, glossaries, appendices | 5-10 |
| 3 | only chapters carrying new material | 3-8 |
| 4 | one note for the whole work | 2-6 |

   Reference material — catalogs, tables, stat blocks, control lists — gets **one index note**, not one
   note per entry.

   **The tier sets the style; the text you actually have sets the ceiling.** These are binding:

{length_budget}

   Do not exceed them. A source whose acquisition came back `partial` may be a short review or summary of
   the work rather than the work itself — read its stub in `sources/` before you start. If that is what it
   is, say so in the note's opening line, extract only what the text in front of you actually states, and
   never write a claim about the work that the text you have does not support. A thin source that yields
   three careful claims is worth more than one that yields thirty inflated ones, because in the finished
   graph those thirty outvote a full monograph.

3. **Filename:** `<Source Short Name> — <Locator> — <Title>.md`. Pick the `{{domain}}` from
   `{note_domains}` by subject matter.

4. **The `## Candidate Claims` section is the contract with Phase 2.** Phase 2 does not re-read the source;
   it reads that section. Each candidate needs a one-sentence assertion, a **Locator** (page or section),
   the evidence the author offers, a confidence rating with a reason, and a claim type from
   `{claim_types}`. Thin candidates here produce thin claims later, and no downstream phase recovers.

5. **Fill in `## Cross-References`.** Where this source engages another source in the corpus, name it and
   say how — extends, disputes, assumes. Those rows become Phase 3's edge candidates, and Phase 3 is much
   worse without them.

### Rules

- Set `claims_status: pending` and `claims_count: 0` in frontmatter. Phase 2 updates them.
- Tag with `type/note`, `{tag}`, `source/<slug>`, and topic tags drawn from `{topics}`. Add a new topic
  tag only when nothing existing fits — a synonym of an existing tag splits a cluster in two, and Phase 3
  will never join it back up.
- Notes are analysis, not transcription. Quote only where exact wording carries the argument. A note that
  reads as a transcript fails the gate as a copyright leak.

### Budget

Roughly **{max_notes} notes** in this call. Depth beats coverage: better six good notes than fourteen
stubs. List anything you did not reach in `skipped`.
