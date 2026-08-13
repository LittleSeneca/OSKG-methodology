"""Phase 1 — Reading notes.

One work item per acquired source; the agent decides how to split it into notes,
guided by tier. Tier order is the point: canon first, because the vocabulary the
canon fixes is what every later source gets compared against, and a graph that
learns its vocabulary last connects nothing at the start.

This is where budget pressure first becomes visible, so it is also where the
first trim happens — by tier, from the bottom, never touching Tiers 1-2.
"""

from __future__ import annotations

from typing import Any

from ..gates import parse_source_guide
from .base import Phase, markdown_table

# One Tier-1/2 source per call: they are long, and a batch that shares context
# across two books produces notes that blur them together.
DEEP_TIERS = (1, 2)


class ReadingNotesPhase(Phase):
    number = 1
    name = "Reading notes"
    stage = "notes"
    batch_size = 1
    specs = ("spec/reading-note.md", "spec/tag-taxonomy.md")

    def plan(self) -> list[str]:
        sources = self._readable_sources()
        if not sources:
            self.log.warn("phase 1: no sources were acquired; nothing to read")
            return []

        sources.sort(key=lambda s: (s["tier"], s["slug"]))

        # Trim only against a measured cost. On a cold run the estimate is a
        # seed biased high — acting on it drops sources the budget would have
        # covered easily. The run loop stops cleanly at a batch boundary when
        # the money really does run out, and because this list is already in
        # tier order, the natural stop drops the lowest tiers anyway.
        if self.budget.has_observations(self.stage):
            affordable = self.budget.affordable(1, self.stage)
            if affordable and len(sources) > affordable:
                sources = self._trim_by_tier(sources, affordable)
        return [f"read:{s['slug']}" for s in sources]

    def _readable_sources(self) -> list[dict[str, Any]]:
        sources = [
            s
            for s in parse_source_guide(self.root / "SOURCE-GUIDE.md")
            if s.get("status") in ("acquired", "partial")
            and s.get("tier", 4) >= self.manifest.min_tier
        ]
        if not sources:
            # A build where acquisition reported nothing still has whatever text
            # landed on disk. Trust the filesystem over the bookkeeping.
            found = {p.stem for p in (self.root / "sources").glob("*/_txt/*.txt")}
            sources = [
                s for s in parse_source_guide(self.root / "SOURCE-GUIDE.md") if s["slug"] in found
            ]
        return sources

    def _trim_by_tier(self, sources: list[dict[str, Any]], affordable: int) -> list[dict[str, Any]]:
        """Drop from the bottom tier up until the corpus fits.

        Tiers 1-2 are never dropped: a graph without its canon is not a smaller
        graph, it is a different and much worse one. If even Tiers 1-2 do not
        fit, they are truncated and that is recorded too.
        """
        kept = list(sources)
        for tier in (4, 3):
            if len(kept) <= affordable:
                break
            dropped = [s for s in kept if s["tier"] == tier]
            if not dropped:
                continue
            kept = [s for s in kept if s["tier"] != tier]
            self.state.record_trim(
                1,
                "tier",
                f"dropped Tier {tier} ({len(dropped)} sources) — budget covers ~{affordable} sources",
                dropped=[s["slug"] for s in dropped],
            )
            self.manifest.data.setdefault("scope", {})["min_tier"] = min(tier, 3) if tier > 1 else 1
            self.manifest.save(self.root)

        if len(kept) > affordable:
            dropped = kept[affordable:]
            kept = kept[:affordable]
            self.state.record_trim(
                1,
                "corpus",
                f"truncated to {affordable} sources within Tiers 1-2 — budget is tight",
                dropped=[s["slug"] for s in dropped],
            )
        return kept

    def build_prompt(self, batch: list[str]) -> str:
        wanted = {k.split(":", 1)[1] for k in batch}
        rows = [s for s in parse_source_guide(self.root / "SOURCE-GUIDE.md") if s["slug"] in wanted]
        deep = any(r.get("tier") in DEEP_TIERS for r in rows)
        return self.render(
            "phase1_notes.md",
            source_table=markdown_table(rows, ("slug", "title", "author", "year", "tier", "role", "status")),
            max_notes=self._note_target(rows, deep),
        )

    def _note_target(self, rows: list[dict[str, Any]], deep: bool) -> int:
        """How many notes to ask for, sized to what the phase can still afford."""
        remaining_sources = max(1, len(self.state.phase(1).pending()) or 1)
        budget_notes = self.budget.affordable(1, self.stage)
        fair_share = max(2, budget_notes // remaining_sources) if budget_notes else (8 if deep else 3)
        ceiling = 12 if deep else 4
        return max(1, min(ceiling, fair_share))
