## Task — acquire sources

Acquire the text of these sources so Phase 1 can read them. Work through them in the order given; they are
already sorted by tier.

{source_table}

### For each source

1. **Find a legitimate full text.** In this order:
   - open-access or public-domain original (government standards, arXiv, PubMed Central, DOAJ, Internet
     Archive, publisher's own free PDF)
   - the author's or publisher's posted copy
   - an official HTML edition you can extract
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

- **Partial is useful.** A table of contents, a substantial preview, the abstract plus a detailed review,
  or an author's article-length statement of the same argument all support real claims. Extract what you
  have, mark `partial`, and note in the stub record exactly what the coverage is so Phase 2 does not
  overreach.
- **Unavailable is honest.** Mark it `unavailable` with a one-line reason. Phase 1 will skip it.
- **Never fabricate.** Do not write a note from what you recall of a book you could not obtain. A claim
  with an invented page number is worse than a missing source, because the graph presents it as traceable.

Paywalled or DRM-protected commercial texts you cannot legitimately obtain are `unavailable`. Do not
attempt to circumvent access controls.

### Budget

You have roughly {max_sources} sources to attempt in this call. Tier 1 first — the canon sets the
vocabulary every later source is compared against, so a Tier 1 gap costs more than a Tier 3 one. If you run
short, stop cleanly and list what remains in `skipped`.
