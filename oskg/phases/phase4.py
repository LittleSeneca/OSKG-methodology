"""Phase 4 — Structural analysis.

The analysis runs first, in Python, over the parsed graph. No model calls, no
cost, no judgment. Only then is the model asked to write up each computed
result — which is the difference between a synthesis you can audit and one you
have to trust, and the reason this phase costs almost nothing.

If the budget runs out here, the write-ups stop but `.oskg/analysis.json` is
already on disk. The computed graph structure survives even a build that could
not afford to describe it.
"""

from __future__ import annotations

import json
from typing import Any

from ..analysis import analyze, format_summary, write_analysis
from ..graph import load_graph
from .base import Phase

# Payload cap per write-up. The full analysis of a large graph will not fit in a
# prompt, and the top of each ranked list is where the meaning is.
PAYLOAD_LIMIT = 14

WRITEUPS: dict[str, dict[str, Any]] = {
    "hinges": {
        "name": "Hinge inventory",
        "file": "phase1-hinge-inventory.md",
        "length": "800-1,400 words",
        "structure": """1. **What a hinge is** — a claim whose falsity would leave others unsupported, and how the
   ranking was computed (size of the transitive collapse set over depends_on / extends /
   operationalizes edges).
2. **The ranked table** — rank, slug, statement, dependent count, source, confidence, contested flag.
3. **What the top five carry** — a paragraph each: what rests on it and why the corpus put it there.
4. **Contested hinges** — hinges that are both load-bearing and directly contradicted. These are where
   the graph is most fragile, and they deserve naming individually.
5. **What the shape says** — is load concentrated in a few claims or spread thin? Concentration means a
   corpus with a strong spine and a single point of failure; dispersion means many small arguments and
   no clear centre.""",
    },
    "cascades": {
        "name": "Cascade trees",
        "file": "phase2-cascade-trees.md",
        "length": "900-1,600 words",
        "structure": """1. **Method** — breadth-first traversal of inbound collapse edges from each top hinge, to four levels.
2. **One section per hinge** — the level-by-level tree, the total collapse radius, and what specifically
   would need rebuilding.
3. **Critical children** — claims deep in a chain that are *also* directly contradicted. Call these out;
   they are load-bearing and disputed at once.
4. **Comparison** — which hinge has the widest radius, which the deepest, and what that difference means
   about how the corpus is argued.""",
    },
    "convergence": {
        "name": "Convergence points",
        "file": "phase3-convergence.md",
        "length": "700-1,200 words",
        "structure": """1. **Method** — claims with support from multiple *independent* sources and no confident
   contradiction. Explain why source independence is the requirement: three supports from one source is
   one source repeating itself.
2. **The convergence table** — claim, supporting source count, total supports, confidence.
3. **What the corpus agrees on** — a paragraph per top convergence, naming the sources.
4. **What agreement does and does not establish** — convergence in a corpus is convergence among the
   sources someone selected. Point at `SOURCE-GUIDE.md` and say what a different corpus might change.""",
    },
    "contradictions": {
        "name": "Contradiction clusters",
        "file": "phase4-contradictions.md",
        "length": "900-1,600 words",
        "structure": """1. **Method** — connected components of the `contradicts` subgraph; a cluster where both sides are
   held at medium-high or above is a **genuine unknown**.
2. **One section per cluster** — the positions, who holds each, the confidence on each side, the topics
   involved. Present both sides at their strongest.
3. **Genuine unknowns** — the disputes where confident sources disagree. State plainly that the graph
   records these and does not resolve them.
4. **Fault lines** — do the disputes cluster around one underlying question? Often several surface
   disagreements share a single load-bearing assumption; if so, name it.""",
    },
    "gaps": {
        "name": "Structural gaps",
        "file": "phase5-structural-gaps.md",
        "length": "700-1,200 words",
        "structure": """1. **Orphans** — claims with no edges. Idiosyncratic, or under-clustered?
2. **Isolated components** — small subgraphs disconnected from the main one. Usually a vocabulary
   mismatch Phase 3 could not bridge; say which vocabularies.
3. **Single-source topics** — subject areas resting on one source. These are the graph's thinnest points.
4. **Fragile bridges** — a single edge is the only link between two sources' claims. Removing it splits
   the graph.
5. **What to acquire next** — a concrete, ordered list of sources that would fix the biggest gaps. This
   section is the next build's input.""",
    },
}


class SynthesisPhase(Phase):
    number = 4
    name = "Structural analysis"
    stage = "synthesis"
    batch_size = 1
    specs = ("spec/quality-gates.md",)

    def plan(self) -> list[str]:
        graph = load_graph(self.root, self.manifest.edge_types)
        if not graph.claims:
            self.log.warn("phase 4: no claims to analyze")
            return []

        # Free, and it runs before any spend — so even a build that exhausts its
        # budget here still leaves the computed structure behind.
        result = analyze(graph)
        path = write_analysis(self.root, result)
        self.log.info(f"analysis computed → {path.relative_to(self.root)} (no model calls)")
        self.log.plain(format_summary(result))
        self._result = result

        return [k for k in WRITEUPS if _has_content(result, k)]

    def build_prompt(self, batch: list[str]) -> str:
        key = batch[0]
        spec = WRITEUPS[key]
        result = getattr(self, "_result", None) or json.loads(
            (self.root / ".oskg" / "analysis.json").read_text(encoding="utf-8")
        )
        return self.render(
            "phase4_synthesis.md",
            analysis_name=spec["name"],
            analysis_key=key,
            output_file=spec["file"],
            output_structure=spec["structure"],
            target_length=spec["length"],
            analysis_payload=_payload(result, key),
            example_slug=_example_slug(result),
        )


def _has_content(result: dict[str, Any], key: str) -> bool:
    value = result.get(key)
    if isinstance(value, dict):
        # `gaps` is always a dict and effectively always has something to say.
        return any(v for v in value.values())
    return bool(value)


def _payload(result: dict[str, Any], key: str) -> str:
    """The slice of the analysis this write-up needs, as fenced JSON."""
    value = result.get(key)
    if isinstance(value, list):
        value = value[:PAYLOAD_LIMIT]
    elif isinstance(value, dict):
        value = {k: (v[:PAYLOAD_LIMIT] if isinstance(v, list) else v) for k, v in value.items()}
    block = json.dumps({"metrics": result.get("metrics", {}), key: value}, indent=2)
    if len(block) > 60_000:
        block = block[:60_000] + "\n... (truncated; read .oskg/analysis.json for the rest)"
    return f"```json\n{block}\n```"


def _example_slug(result: dict[str, Any]) -> str:
    hinges = result.get("hinges") or []
    return hinges[0]["slug"] if hinges else "claim-slug"
