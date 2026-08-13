## Task — acquire sources

Acquire the text of these sources so Phase 1 can read them. Work through them in the order given; they are
already sorted by tier.

{source_table}

### Already on disk

{local_matches}

### Configured acquisition command

{fetch_command}

### For each source

1. **Find the full text.** In this order:
   - **a candidate listed above from the local library** — verify it really is the work named (open it and
     check the title page or first lines) before using it; a wrong match attributes claims to a book nobody
     read, which is the worst thing that can happen to this graph
   - open-access or public-domain original (government standards, arXiv, PubMed Central, DOAJ, Internet
     Archive, publisher's own free PDF)
   - the author's or publisher's posted copy
   - an official HTML edition you can extract
   - the configured acquisition command, if there is one
2. **Extract to plaintext** at `sources/{{kind}}/_txt/{{slug}}.txt`, where `kind` is `books`, `papers`, or
   `standards`. Use `pdftotext` if available, otherwise Python. That directory is gitignored — full text is
   never committed. See METHODOLOGY.md §5.
3. **Write a stub record** at `sources/{{kind}}/{{slug}}.md` with frontmatter
   (`tags: [type/source, {tag}, source/{{slug}}]`, title, author, year, tier, acquisition status, and where
   the text came from) and a short paragraph on the work's role in the graph. This file **is** committed;
   it is the provenance record.
4. **Update `SOURCE-GUIDE.md`**: set `status` to `acquired`, `partial`, or `unavailable`.

### When you cannot get the full text

This is normal and expected — do not spend calls fighting it, and do not substitute a different work
without recording that you did.

- **Partial is useful, but say exactly what it is.** A table of contents, a substantial preview, the
  abstract plus a detailed review, or an author's article-length statement of the same argument all support
  real claims. Extract what you have, mark `partial`, and state in the stub record — in its first line —
  **what the text actually is** ("a 1,700-word book review", not "coverage of the book"). Phase 1 reads that
  stub to decide how much to extract, and a `partial` source described vaguely gets treated as if the work
  itself were in hand. In one real build that turned a 1,682-word review into 37 claims, more than any full
  paper in the corpus contributed.
- **Unavailable is honest.** Mark it `unavailable` with a one-line reason. Phase 1 will skip it.
- **Never fabricate.** Do not write a note from what you recall of a book you could not obtain. A claim
  with an invented page number is worse than a missing source, because the graph presents it as traceable.

Paywalled or DRM-protected commercial texts are `unavailable` unless the local library already holds them
or the configured acquisition command retrieves them. Do not attempt to circumvent access controls
yourself, and do not improvise an acquisition route that is not configured here — where a work comes from
is the operator's decision, recorded in `oskg.yaml`, not one to make mid-run.

### Budget

You have roughly {max_sources} sources to attempt in this call. Tier 1 first — the canon sets the
vocabulary every later source is compared against, so a Tier 1 gap costs more than a Tier 3 one. If you run
short, stop cleanly and list what remains in `skipped`.
