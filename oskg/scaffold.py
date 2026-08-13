"""Create a new OSKG project directory.

Everything a build needs before Phase 0 opens its mouth: the manifest, the vault
skeleton, the index notes, and — first, before anything else can be written —
the `.gitignore` that keeps extracted source text out of git.

That ordering is deliberate. `sources/**/_txt/` must be ignored before a single
byte of source text lands there, because the one failure the method cannot
repair after the fact is committing copyrighted full text.
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from pathlib import Path

from . import gitutil
from .manifest import Manifest, default_manifest

__all__ = ["scaffold", "project_name_for", "slug_for", "PROJECT_GITIGNORE"]

PROJECT_GITIGNORE = """\
# ── Copyright control (METHODOLOGY.md §5) ────────────────────────────
# Extracted source text is never committed or redistributed.
sources/**/_fulltext/
sources/**/_txt/
sources/**/_pdfs/
*.pdf
*.epub
*.mobi
*.djvu

# ── Pipeline scratch ─────────────────────────────────────────────────
# state.json, ledger.jsonl, edges.json and analysis.json ARE committed:
# they are the reproducibility record. Prompts and temp files are not.
.oskg/tmp/
.oskg/prompts/

# ── Obsidian workspace (local only) ──────────────────────────────────
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/graph.json
.obsidian/appearance.json
.obsidian/app.json
.obsidian/hotkeys.json
.obsidian/core-plugins.json
.obsidian/community-plugins.json

# ── OS ───────────────────────────────────────────────────────────────
.DS_Store
._*
Thumbs.db
.trash/
"""

_INDEX_DESCRIPTIONS = {
    "claims": "Extracted claim nodes. One claim per file; the filename is the node ID that wikilinks resolve against.",
    "synthesis": "Phase 4 structural analyses and the Phase 5 capstone. Every number in here is recomputable from the graph.",
}


def slug_for(topic: str) -> str:
    """A short, filesystem-safe slug from a free-text topic.

    Stopwords go first so `"the archaeology and interpretation of Göbekli Tepe"`
    becomes `archaeology-gobekli-tepe` rather than `the-archaeology-and`.
    """
    stripped = unicodedata.normalize("NFKD", topic).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", stripped.lower())
    stopwords = {
        "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with",
        "its", "their", "how", "what", "why", "about", "into", "from", "at", "by",
    }
    kept = [w for w in words if w not in stopwords] or words
    slug = "-".join(kept[:4])
    return slug[:48].strip("-") or "graph"


def project_name_for(topic: str, slug: str | None = None) -> str:
    """`OSKG-GobekliTepe` from a topic — matching the sibling repos' naming."""
    parts = (slug or slug_for(topic)).split("-")
    return "OSKG-" + "".join(p.capitalize() for p in parts[:3])


def scaffold(
    parent_dir: Path | str,
    topic: str,
    *,
    budget_usd: float = 20.0,
    project_name: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    git: bool = True,
    exist_ok: bool = True,
) -> tuple[Path, Manifest]:
    """Create (or adopt) a project directory. Returns (path, manifest)."""
    slug = slug_for(topic)
    name = project_name or project_name_for(topic, slug)
    root = Path(parent_dir).expanduser().resolve() / name

    existing = root / "oskg.yaml"
    if existing.exists():
        if not exist_ok:
            raise FileExistsError(f"{root} already holds an OSKG project")
        return root, Manifest.load(root)

    root.mkdir(parents=True, exist_ok=True)

    # Before anything else can write source text into this tree.
    (root / ".gitignore").write_text(PROJECT_GITIGNORE, encoding="utf-8")

    manifest = default_manifest(
        project=name, topic=topic, slug=slug, budget_usd=budget_usd, model=model, provider=provider
    )
    manifest.save(root)

    for sub in ("claims", "synthesis", *manifest.note_domains):
        (root / "notes" / sub).mkdir(parents=True, exist_ok=True)
    for kind in ("books", "papers", "standards"):
        (root / "sources" / kind / "_txt").mkdir(parents=True, exist_ok=True)
    (root / ".oskg" / "phase0").mkdir(parents=True, exist_ok=True)

    _write_docs(root, manifest)
    _write_indexes(root, manifest)

    if git:
        ok, out = gitutil.init(root)
        if ok:
            gitutil.commit(root, f"oskg: scaffold {name}")
    return root, manifest


# ─────────────────────────────────────────────────────────────────────────────
# Documents
# ─────────────────────────────────────────────────────────────────────────────


def _write_docs(root: Path, m: Manifest) -> None:
    today = _dt.date.today().isoformat()
    (root / "README.md").write_text(_readme(m, today), encoding="utf-8")
    (root / "Home.md").write_text(_home(m, today), encoding="utf-8")
    (root / "METHODOLOGY.md").write_text(_methodology(m, today), encoding="utf-8")
    (root / "SOURCE-GUIDE.md").write_text(_source_guide(m, today), encoding="utf-8")


def _readme(m: Manifest, today: str) -> str:
    return f"""# {m.project}

An **Open Source Knowledge Graph** on {m.topic}.

> {m.question}

Built with the [OSKG method](https://github.com/LittleSeneca/OSKG-methodology): sources are decomposed
into discrete claim nodes, connected by typed edges, and synthesized from graph structure rather than
from impressions. Every claim is traceable to its source; every edge is written down.

## Pipeline

```
sources → reading notes → claims → typed-edge graph → structural analysis → capstone
```

| Phase | Output |
|---|---|
| 0 Scoping | [`SOURCE-GUIDE.md`](SOURCE-GUIDE.md), `oskg.yaml` |
| 1 Reading notes | `notes/{{{",".join(m.note_domains)}}}/` |
| 2 Claims | `notes/claims/` — one claim per file |
| 3 Edges | typed edges in claim files, indexed at `.oskg/edges.json` |
| 4 Analysis | `notes/synthesis/phase*.md` — computed, not inferred |
| 5 Capstone | `notes/synthesis/capstone.md` |

Run state and spend: [`PROGRESS.md`](PROGRESS.md). Method: [`METHODOLOGY.md`](METHODOLOGY.md).

## Reading this graph

Start with the capstone, then the synthesis documents, then follow wikilinks into individual claims.
In Obsidian, open the vault at this directory: wikilinks are edges, files are nodes, and the graph view
is the visualization layer.

**Before trusting it**, read [`SOURCE-GUIDE.md`](SOURCE-GUIDE.md) — source selection was automated, and
a corpus that omits the strongest counter-position produces a confident, wrong graph. Read the
limitations section of the capstone, and `PROGRESS.md` for anything cut under budget.

## Copyright

Extracted source text lives in gitignored `sources/**/_txt/` and is never committed or redistributed.
Only the graph is published. See [`METHODOLOGY.md`](METHODOLOGY.md).

---

*Generated {today} by `oskg`.*
"""


def _home(m: Manifest, today: str) -> str:
    return f"""---
tags:
  - oskg/root
  - {m.tag}
created: {today}
aliases:
  - "{m.project} Home"
pinned: true
---

# {m.project}

> {m.question}

The home note for **{m.project}** — an Open Source Knowledge Graph on {m.topic}.

## Structure

- **[[SOURCE-GUIDE]]** — the corpus, tiered, and what was deliberately left out
- **[[notes/claims/Claims Index|Claims]]** — extracted claim nodes
- **[[notes/synthesis/Synthesis Index|Synthesis]]** — structural analyses and the capstone
- **[[METHODOLOGY]]** — how this graph was built
- **[[PROGRESS]]** — run state, spend, and scope trims

## Approach

1. **Claims, not summaries.** Every unit of knowledge is a discrete, individually addressable assertion.
2. **Typed edges.** Relationships carry explicit semantics: {", ".join(m.edge_types)}.
3. **Source-grounded.** Every claim names the passage that produced it.
4. **Synthesis from structure.** What is load-bearing is computed from the graph, not asserted.

## Status

Scaffolded {today}. See [[PROGRESS]] for where the build got to.

---

*This is a living document.*
"""


def _methodology(m: Manifest, today: str) -> str:
    return f"""---
tags:
  - type/meta
  - methodology
  - {m.tag}
created: {today}
---

# METHODOLOGY — {m.project}

This project applies the **OSKG method**. The canonical, domain-agnostic statement of the method and its
format contracts lives at [OSKG-methodology](https://github.com/LittleSeneca/OSKG-methodology); this
document records only what is specific to this graph.

## Question

> {m.question}

## Domain vocabulary

| Dimension | This project |
|---|---|
| **Domain type** | {m.domain_type} |
| **Edge types** | {", ".join(f"`{e}`" for e in m.edge_types)} |
| **Claim types** | {", ".join(f"`{c}`" for c in m.claim_types)} |
| **Evidence types** | {", ".join(f"`{e}`" for e in m.evidence_types)} |
| **Note domains** | {", ".join(f"`{d}`" for d in m.note_domains)} |
| **Project tag** | `{m.tag}` |
| **Claim slug prefix** | `{m.slug_prefix or "(none)"}` |

Full vocabulary and gate thresholds: [`oskg.yaml`](oskg.yaml).

## Pipeline

```
sources → reading notes → claims → typed-edge graph → structural analysis → capstone
```

Phase 4 is computed, not written: the hinge inventory, cascade trees, convergence points, contradiction
clusters, and structural gaps are all derived from graph structure with no model calls. The write-ups
explain a computed result rather than discovering one, which is what makes them auditable — every number
in the synthesis is recomputable by anyone with this repository.

## What this graph does not do

- **It does not adjudicate.** A `contradicts` edge records that two sources conflict; it does not decide
  who is right.
- **Confidence is the source's.** A HIGH-confidence claim is one its source asserts strongly with evidence
  it names — not one this graph vouches for.
- **Extraction was automated.** The gates check form: fields present, links resolving, evidence non-empty.
  They cannot catch a misreading. Every claim carries a locator so spot-checking is quick.
- **Source selection was automated.** See [`SOURCE-GUIDE.md`](SOURCE-GUIDE.md) for the corpus and its
  deliberate omissions, and `PROGRESS.md` for anything cut under budget.

## Copyright and fair use

Decomposition into atomic claims with typed edges is transformative: the output (a claim graph) serves a
different function than the input (narrative exposition), carries only short excerpts with locators, and
is useless as a substitute for its sources. Extracted full text lives in gitignored `sources/**/_txt/` and
is never committed or redistributed. Government works are public domain (17 U.S.C. § 105).

---

*Method: [OSKG-methodology](https://github.com/LittleSeneca/OSKG-methodology).*
"""


def _source_guide(m: Manifest, today: str) -> str:
    return f"""---
tags:
  - type/meta
  - source-guide
  - {m.tag}
created: {today}
---

# {m.project} — Source Guide

*Phase 0 replaces this file with the researched corpus. The tables below are the format contract:
`## Tier N` headings, then a pipe table with exactly these columns.*

## Why this corpus

_(Phase 0 writes 2-3 paragraphs here on why these sources and not others, including what was
deliberately left out and why. This is the paragraph a reader checks before trusting the graph.)_

## Tier 1 — Canon

The graph cannot function without these. They set the vocabulary every later source is compared against.

| slug | title | author | year | tier | role | status |
|---|---|---|---|---|---|---|

## Tier 2 — Core

Substantive treatments carrying the bulk of the claims.

| slug | title | author | year | tier | role | status |
|---|---|---|---|---|---|---|

## Tier 3 — Practitioner and community

Implementation detail, dissent, the view from the field.

| slug | title | author | year | tier | role | status |
|---|---|---|---|---|---|---|

## Tier 4 — Adjacent

Useful frameworks not strictly on topic. Processed only if budget allows.

| slug | title | author | year | tier | role | status |
|---|---|---|---|---|---|---|

---

**status:** `pending` · `acquired` · `partial` · `unavailable`
"""


def _write_indexes(root: Path, m: Manifest) -> None:
    today = _dt.date.today().isoformat()
    for sub in ("claims", "synthesis", *m.note_domains):
        title = sub.replace("-", " ").title()
        path = root / "notes" / sub / f"{title} Index.md"
        if path.exists():
            continue
        description = _INDEX_DESCRIPTIONS.get(
            sub, f"Reading notes for the **{title.lower()}** domain."
        )
        path.write_text(
            f"""---
tags:
  - type/index
  - {m.tag}
  - {sub}
created: {today}
---

# {title} Index

{description}

_(Populated as the pipeline runs.)_
""",
            encoding="utf-8",
        )

    (root / "notes" / "Notes Index.md").write_text(
        f"""---
tags:
  - type/index
  - {m.tag}
created: {today}
---

# Notes Index

| Directory | Contents |
|---|---|
"""
        + "\n".join(
            f"| [[{sub}/{sub.replace('-', ' ').title()} Index\\|{sub}/]] | "
            f"{_INDEX_DESCRIPTIONS.get(sub, 'Reading notes.')} |"
            for sub in ("claims", "synthesis", *m.note_domains)
        )
        + "\n",
        encoding="utf-8",
    )
