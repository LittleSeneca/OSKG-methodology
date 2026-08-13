"""Phase 0 — Scoping and acquisition.

Two stages in one phase, because they answer one question: what is this graph
about, and what will it be built from.

`scope` is the highest-leverage call in the pipeline. It fixes the vocabulary
every later phase uses and the corpus every later dollar is spent reading, and
it costs pennies. Getting it wrong wastes the other $19.

`sources` then acquires what it can. Failure here is normal and survivable —
`partial` and `unavailable` are recorded, and Phase 1 skips what it cannot read.
Fabricating a source it could not obtain is the one outcome that is not
survivable, which is why the prompt says so three times.
"""

from __future__ import annotations

import json
from typing import Any

from ..gates import parse_source_guide
from ..runner import RunResult
from .base import Phase, markdown_table

_EXTRA_EDGE_TYPES = ("challenged_by", "operationalizes", "exception_to", "replaces", "cites")

# Sources per acquisition call. Each source may need several searches and a text
# extraction, so a large batch runs out of tool calls before it runs out of list.
ACQUIRE_BATCH = 6


class ScopingPhase(Phase):
    number = 0
    name = "Scoping and acquisition"
    stage = "scope"
    batch_size = 1
    specs = ("spec/project-manifest.md", "spec/tag-taxonomy.md")
    gate_if_empty = True
    critical_stages = ("scope",)

    def plan(self) -> list[str]:
        items = ["scope"]
        if self._plan_file().exists():
            items.extend(self._acquisition_items())
        return items

    def batches(self, pending):
        # `scope` must run alone and first: it writes the source list that the
        # acquisition items are derived from.
        if "scope" in pending:
            yield ["scope"]
            pending = [p for p in pending if p != "scope"]
        for i in range(0, len(pending), ACQUIRE_BATCH):
            yield pending[i : i + ACQUIRE_BATCH]

    def stage_for(self, batch: list[str]) -> str:
        return "scope" if batch == ["scope"] else "sources"

    def build_prompt(self, batch: list[str]) -> str:
        if batch == ["scope"]:
            return self._scope_prompt()
        return self._acquire_prompt(batch)

    # ── scope ───────────────────────────────────────────────────────────
    def _scope_prompt(self) -> str:
        target_sources = int(self.manifest.scope.get("target_sources") or 0) or self._size_corpus()
        return self.render(
            "phase0_scope.md",
            target_sources=target_sources,
            target_notes=max(target_sources * 2, 12),
            allowed_extra_edges=", ".join(_EXTRA_EDGE_TYPES),
        )

    def _size_corpus(self) -> int:
        """Corpus size the budget can actually read.

        Sized off Phase 1's allowance rather than a fixed target: a $5 build that
        plans 30 sources produces 30 stubs, and a $50 build that plans 12 leaves
        money unspent.
        """
        notes_budget = self.budget.phase_ceiling(1)
        per_note = self.budget.estimate("notes")
        affordable_notes = int(notes_budget / per_note) if per_note else 20
        return max(6, min(40, affordable_notes // 2))

    # ── acquisition ─────────────────────────────────────────────────────
    def _acquisition_items(self) -> list[str]:
        sources = self._sources()
        return [f"acquire:{s['slug']}" for s in sources if s.get("status") in ("", "pending")]

    def _acquire_prompt(self, batch: list[str]) -> str:
        wanted = {k.split(":", 1)[1] for k in batch}
        rows = [s for s in self._sources() if s["slug"] in wanted]
        return self.render(
            "phase0_sources.md",
            source_table=markdown_table(rows, ("slug", "title", "author", "year", "tier", "role")),
            max_sources=len(rows),
            local_matches=self._local_matches(rows),
            fetch_command=self._fetch_command_block(),
        )

    def _local_matches(self, rows: list[dict[str, Any]]) -> str:
        """Candidate files already on disk, for the agent to confirm.

        Offered, never auto-accepted: a wrong match attributes claims to a work
        nobody read, which is the worst failure this pipeline can produce.
        """
        roots = self.manifest.local_library
        if not roots:
            return (
                "_No `acquisition.local_library` configured. Set it in `oskg.yaml` to point at "
                "directories of texts you already hold, and they will be searched before the web._"
            )
        from ..library import index_library, match_sources

        files = index_library(roots)
        if not files:
            return f"_`acquisition.local_library` is set to {roots} but no readable files were found there._"

        matches = match_sources(rows, files)
        if not matches:
            return f"_{len(files):,} local files searched; no candidate matched these sources._"

        lines = [
            f"{len(files):,} files searched in {roots}. **Candidates — verify each is really the work "
            f"named before using it**, then extract it and mark the source `acquired`:",
            "",
        ]
        for slug, found in sorted(matches.items()):
            for m in found:
                lines.append(f"- `{slug}` → `{m.path}`  _(match: {m.reason})_")
        return "\n".join(lines)

    def _fetch_command_block(self) -> str:
        command = self.manifest.fetch_command
        if not command:
            return (
                "_No `acquisition.fetch_command` configured. Set one in `oskg.yaml` to run your own "
                "acquisition tool for sources that are neither local nor open-access._"
            )
        return (
            f"An acquisition command is configured:\n\n```\n{command}\n```\n\n"
            "Run it for any source you could not find locally or open-access, substituting `{{slug}}`, "
            "`{{title}}`, `{{author}}`, `{{year}}` and `{{out}}` (the target `.txt` path). If it produces a "
            "file, extract and mark the source `acquired`, and record in the stub that it came from this "
            "command. If it does not, mark the source `unavailable` and move on."
        )

    def _sources(self) -> list[dict[str, Any]]:
        return parse_source_guide(self.root / "SOURCE-GUIDE.md")

    # ── plan ingestion ──────────────────────────────────────────────────
    def _plan_file(self):
        return self.root / ".oskg" / "phase0" / "plan.json"

    def on_batch_complete(self, batch: list[str], result: RunResult) -> None:
        if batch != ["scope"]:
            return
        plan = self._load_plan(result)
        if plan:
            self._apply_plan(plan)
        else:
            self.log.warn("phase 0: no usable plan.json — keeping the default vocabulary")

        # The source list only exists now, so this is the first moment the
        # acquisition queue can be built. The run loop re-reads the queue each
        # pass, which is what lets these run in the same invocation.
        items = self._acquisition_items()
        if items:
            self.state.phase(0).enqueue(items)
            self.state.save()
            self.log.info(f"phase 0: {len(items)} sources queued for acquisition")

    def _load_plan(self, result: RunResult) -> dict[str, Any] | None:
        path = self._plan_file()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self.log.warn(f"phase 0: plan.json is unreadable ({exc}); falling back to the response")
        payload = result.json()
        return payload if isinstance(payload, dict) and payload.get("claim_types") else None

    def _apply_plan(self, plan: dict[str, Any]) -> None:
        """Fold the agent's plan into the manifest, keeping it valid.

        Every field is validated before it lands: an invented edge type or a
        `note_domains: [claims]` would break the pipeline in a phase where the
        cause is no longer visible.
        """
        m = self.manifest
        data = m.data

        if plan.get("question"):
            data["question"] = str(plan["question"])
        if plan.get("slug_prefix") is not None:
            data["slug_prefix"] = str(plan["slug_prefix"]).strip()
        if plan.get("domain_type") in ("domain", "person", "corpus"):
            data["domain_type"] = plan["domain_type"]

        for key in ("claim_types", "evidence_types", "topics"):
            values = _clean_list(plan.get(key))
            if values:
                data[key] = values

        domains = [d for d in _clean_list(plan.get("note_domains")) if d not in ("claims", "synthesis")]
        if domains:
            data["note_domains"] = domains

        extra = [
            e for e in _clean_list(plan.get("edge_types_extra"), sep="_") if e in _EXTRA_EDGE_TYPES
        ]
        if extra:
            data["edge_types"] = list(m.edge_types) + [e for e in extra if e not in m.edge_types]

        sources = plan.get("sources") or []
        if isinstance(sources, list) and sources:
            scope = dict(data.get("scope") or {})
            scope["target_sources"] = len(sources)
            scope["target_notes"] = int(plan.get("estimated_notes") or len(sources) * 2)
            data["scope"] = scope

        problems = m.validate()
        if problems:
            self.log.warn(f"phase 0: plan produced an invalid manifest, reverting the bad fields: {problems}")
            self._revert_invalid(problems)
        m.save(self.root)
        self._ensure_note_dirs()
        self.log.info(
            f"scoped: {len(m.claim_types)} claim types · {len(m.topics)} topics · "
            f"{len(m.note_domains)} note domains · {m.scope.get('target_sources', 0)} sources"
        )

    def _revert_invalid(self, problems: list[str]) -> None:
        from ..manifest import default_manifest

        fallback = default_manifest(
            project=self.manifest.project, topic=self.manifest.topic, slug=self.manifest.slug
        )
        for problem in problems:
            for key in ("claim_types", "evidence_types", "note_domains", "edge_types", "topics"):
                if key.upper() in problem or key in problem:
                    self.manifest.data[key] = fallback.data[key]

    def _ensure_note_dirs(self) -> None:
        for domain in self.manifest.note_domains + ["claims", "synthesis"]:
            (self.root / "notes" / domain).mkdir(parents=True, exist_ok=True)

    def on_phase_complete(self, outcome) -> None:
        acquired = [
            s for s in self._sources() if s.get("status") in ("acquired", "partial")
        ]
        self.log.info(f"phase 0: {len(acquired)}/{len(self._sources())} sources acquired")


def _clean_list(value: Any, sep: str = "-") -> list[str]:
    """Lowercase, de-duplicated, order preserved.

    `sep` is what whitespace becomes: `-` for tags and type names, `_` for edge
    types, which are written `depends_on` throughout the spec. Existing `-` and
    `_` are left alone — normalising them to each other would turn
    `challenged_by` into a type the manifest does not recognise.
    """
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        s = sep.join(str(item).strip().lower().split())
        s = "".join(ch for ch in s if ch.isalnum() or ch in "-_/")
        if s and s not in out:
            out.append(s)
    return out
