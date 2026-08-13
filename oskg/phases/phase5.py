"""Phase 5 — Capstone.

One call, over already-condensed input, drawing on the reserve that was held out
of the pool from the start. That reserve is the reason this phase exists at all
in a tight build: a run that spent its last dollar on edge construction and could
not write a conclusion has produced nothing a human can read.

The capstone reports graph structure. It does not summarize sources and it does
not pick winners — where the graph records a live disagreement, the capstone
records it too. Making disagreement visible is the contribution; resolving it
would be the graph pretending to an authority it does not have.
"""

from __future__ import annotations

import json
from typing import Any

from ..graph import load_graph
from .base import Phase


class CapstonePhase(Phase):
    number = 5
    name = "Capstone"
    stage = "capstone"
    batch_size = 1
    specs = ()

    def plan(self) -> list[str]:
        analysis = self.root / ".oskg" / "analysis.json"
        if not analysis.exists():
            self.log.warn("phase 5: no analysis to write a capstone from")
            return []
        if (self.root / "notes" / "synthesis" / "capstone.md").exists() and not self.ctx.forced:
            self.log.info("phase 5: capstone already written (`--from-phase 5` rewrites it)")
            return []
        return ["capstone"]

    def build_prompt(self, batch: list[str]) -> str:
        return self.render("phase5_capstone.md", metrics_block=self._metrics_block())

    def _metrics_block(self) -> str:
        graph = load_graph(self.root, self.manifest.edge_types)
        metrics = graph.metrics()
        analysis = self._analysis()
        gaps = analysis.get("gaps", {})
        contradictions = analysis.get("contradictions", [])
        lines = [
            f"- **{metrics['claims']} claims** from **{metrics['sources']} sources** across "
            f"**{metrics['topics']} topics**",
            f"- **{metrics['edges']} edges** ({metrics['edges_per_claim']} per claim, "
            f"{int(metrics['cross_source_ratio'] * 100)}% cross-source)",
            f"- **{len(analysis.get('hinges', []))} hinges** ranked; top carries "
            f"{_top_hinge_load(analysis)} dependent claims",
            f"- **{len(analysis.get('convergence', []))} convergence points** "
            f"(multi-source agreement, uncontested)",
            f"- **{len(contradictions)} contradiction clusters**, "
            f"{sum(1 for c in contradictions if c.get('genuine_unknown'))} of them genuine unknowns",
            f"- **{gaps.get('orphan_count', 0)} orphan claims**, "
            f"{len(gaps.get('single_source_topics', []))} single-source topics, "
            f"{len(gaps.get('fragile_bridges', []))} fragile bridges",
        ]
        trims = self.state.trims
        if trims:
            lines.append(
                f"- **{len(trims)} scope trims** were made under budget pressure — see PROGRESS.md, "
                f"and name them in the limitations section"
            )
        return "\n".join(lines)

    def _analysis(self) -> dict[str, Any]:
        try:
            return json.loads((self.root / ".oskg" / "analysis.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}


def _top_hinge_load(analysis: dict[str, Any]) -> int:
    hinges = analysis.get("hinges") or []
    return hinges[0].get("dependents", 0) if hinges else 0
