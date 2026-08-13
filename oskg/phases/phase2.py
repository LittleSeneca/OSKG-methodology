"""Phase 2 — Claims extraction.

Work item = one reading note. Batches of three, which is where the prior OSKG
projects landed after hitting both walls: smaller batches pay the ~$0.01
per-call overhead too often, larger ones degrade — later notes in a batch get
visibly thinner treatment than the first, a failure those projects checked for
by name.

The existing-claims list handed to each batch is what keeps the graph connected
as it grows. A batch that cannot see what came before writes an island.
"""

from __future__ import annotations

from ..frontmatter import Document, read
from ..gates import iter_reading_notes
from ..graph import load_graph
from .base import Phase, bullet_list

# Existing claims shown to each batch. Enough to attach to, few enough that the
# list does not crowd out the notes being extracted.
EXISTING_CLAIM_SAMPLE = 120


class ClaimsPhase(Phase):
    number = 2
    name = "Claims extraction"
    stage = "extract"
    batch_size = 3
    specs = ("spec/claim-node.md", "spec/edge-types.md", "spec/tag-taxonomy.md")

    def plan(self) -> list[str]:
        notes = [d for d in iter_reading_notes(self.root, self.manifest) if not d.error]
        pending = [d for d in notes if str(d.meta.get("claims_status", "pending")) != "extracted"]
        if not pending:
            self.log.warn("phase 2: every reading note is already extracted")
            return []

        # Tier order again: canon claims become the edge targets everything else
        # attaches to, so extracting them first compounds across the phase.
        pending.sort(key=lambda d: (int(d.meta.get("source_tier") or 4), d.path.name))

        # As in Phase 1: only trim against a measured cost, never a seed.
        if self.budget.has_observations(self.stage):
            affordable = self.budget.affordable(2, self.stage) * self.batch_size
            if affordable and len(pending) > affordable:
                dropped = pending[affordable:]
                pending = pending[:affordable]
                self.state.record_trim(
                    2,
                    "notes",
                    f"{len(dropped)} reading notes not extracted — budget covers ~{affordable}",
                    dropped=[d.path.name for d in dropped],
                )
        return [str(d.path.relative_to(self.root)) for d in pending]

    def build_prompt(self, batch: list[str]) -> str:
        docs = [read(self.root / rel) for rel in batch]
        return self.render(
            "phase2_claims.md",
            note_list=bullet_list(self._describe(d, rel) for d, rel in zip(docs, batch)),
            existing_claims=self._existing_claims(),
        )

    def _describe(self, doc: Document, rel: str) -> str:
        title = doc.meta.get("source_title") or doc.path.stem
        locator = doc.meta.get("locator") or ""
        tier = doc.meta.get("source_tier", "?")
        return f"`{rel}` — {title} {locator} (Tier {tier})"

    def _existing_claims(self) -> str:
        """Slugs already in the graph, so new claims edge into it rather than beside it."""
        graph = load_graph(self.root, self.manifest.edge_types)
        if not graph.claims:
            return "_No claims yet — this is the first batch. Edges will be within this batch only._"

        by_source: dict[str, list[str]] = {}
        for slug, claim in sorted(graph.claims.items()):
            by_source.setdefault(claim.source or "(unattributed)", []).append(slug)

        lines = [f"{len(graph.claims)} claims exist. Edge into them where the argument connects.", ""]
        shown = 0
        for source, slugs in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
            if shown >= EXISTING_CLAIM_SAMPLE:
                break
            take = slugs[: max(4, EXISTING_CLAIM_SAMPLE // max(1, len(by_source)))]
            shown += len(take)
            lines.append(f"**{source}** — " + ", ".join(f"`{s}`" for s in take))
        if shown < len(graph.claims):
            lines.append("")
            lines.append(
                f"_({len(graph.claims) - shown} more — list `notes/claims/` if you need the full set.)_"
            )
        return "\n".join(lines)
