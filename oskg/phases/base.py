"""The `Phase` base class — everything the six phase drivers have in common.

A driver answers two questions: what work is outstanding (`plan`), and how does
one batch of it become a prompt (`build_prompt`). The base owns the rest —
budget admission, prompt rendering, running, gating, repair, state, commits —
so the phase-specific code stays about the phase.

The control flow that matters:

    plan → enqueue → while pending and budget allows:
                         guard → run → record → mark → gate
                     → final gate → repair? → commit → done

Budget exhaustion is not an error. It stops the phase at a batch boundary with
its work recorded, and the pipeline moves on — because a truncated graph that
reached Phase 5 is usable and one that stalled in Phase 2 is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .. import gates as gates_mod
from ..budget import BudgetExhausted
from ..gates import GateReport
from ..runner import RunResult
from ..state import DONE, FAILED, PENDING, SKIPPED

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
METHODOLOGY_DIR = Path(__file__).resolve().parent.parent.parent

# Backstop against a driver bug that enqueues faster than it completes. The
# budget cap is the real bound; this only stops a spin when something is wrong.
MAX_BATCHES_PER_PHASE = 500


@dataclass
class PhaseOutcome:
    phase: int
    ran: int = 0
    completed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    gate: GateReport | None = None
    stopped: str = ""
    trimmed: bool = False

    @property
    def ok(self) -> bool:
        return not self.stopped and (self.gate is None or self.gate.passed)


class Phase:
    """One pipeline phase. Subclasses implement `plan` and `build_prompt`."""

    number: int = -1
    name: str = ""
    stage: str = "generic"
    batch_size: int = 1
    #: Spec files the agent should read for this phase.
    specs: Sequence[str] = ()
    #: Skip the gate when the phase produced nothing (an empty phase is not a
    #: failed one — it is a phase whose inputs were unavailable).
    gate_if_empty: bool = False
    #: Stages the whole run depends on. These are admitted against the total
    #: cap only, never blocked by this phase's share — a run that skips its
    #: scoping call has no corpus, and every later phase is spending against
    #: nothing.
    critical_stages: Sequence[str] = ()

    def __init__(self, ctx):
        self.ctx = ctx
        self.manifest = ctx.manifest
        self.state = ctx.state
        self.budget = ctx.budget
        self.runner = ctx.runner
        self.root = ctx.project_dir
        self.log = ctx.log

    # ── subclass interface ──────────────────────────────────────────────
    def plan(self) -> list[str]:
        """Work item keys for this phase, in the order they should be done."""
        raise NotImplementedError

    def build_prompt(self, batch: list[str]) -> str:
        """The prompt for one batch of work items."""
        raise NotImplementedError

    def on_batch_complete(self, batch: list[str], result: RunResult) -> None:
        """Hook after a successful batch — parse artifacts, update the manifest."""

    def on_phase_complete(self, outcome: PhaseOutcome) -> None:
        """Hook after the final gate passes."""

    def batches(self, pending: list[str]) -> Iterable[list[str]]:
        size = max(1, self.batch_size)
        for i in range(0, len(pending), size):
            yield pending[i : i + size]

    def stage_for(self, batch: list[str]) -> str:
        """The ledger stage this batch bills to.

        A phase with two kinds of work bills them separately, so each keeps its
        own cost estimate. Phase 0 is the case: its scoping call and its
        acquisition calls cost very different amounts, and averaging them
        together mispredicts both.
        """
        return self.stage

    # ── the run loop ────────────────────────────────────────────────────
    def run(self) -> PhaseOutcome:
        outcome = PhaseOutcome(phase=self.number)
        ps = self.state.start_phase(self.number)
        self.log.phase(self.number, self.name)

        try:
            planned = self.plan()
        except BudgetExhausted as exc:
            outcome.stopped = str(exc)
            return self._finish(outcome, status=PENDING)
        ps.enqueue(planned)
        self.state.save()

        if not ps.pending() and not ps.done():
            self.log.warn(f"phase {self.number}: nothing to do")

        # Re-read the queue each pass rather than iterating a snapshot: a batch
        # can enqueue more work. Phase 0's scoping call is the reason — it
        # writes the source list that its own acquisition items are derived
        # from, so those items cannot exist when the phase is first planned.
        for _ in range(MAX_BATCHES_PER_PHASE):
            pending = ps.pending()
            if not pending:
                break
            batch = next(iter(self.batches(pending)), None)
            if not batch:
                break

            stage = self.stage_for(batch)
            critical = self._is_critical(batch)
            ok, reason = self.budget.check(self.number, stage, ignore_phase_cap=critical)
            if not ok:
                self._trim(outcome, ps, pending, reason)
                break

            label = f"p{self.number}-{stage}-{len(outcome.completed) + 1}"
            self.log.batch(self.number, batch, self.budget.phase_remaining(self.number))

            try:
                prompt = self.build_prompt(batch)
            except Exception as exc:  # a driver bug must not lose the run
                self.log.error(f"could not build prompt for {batch}: {exc}")
                for key in batch:
                    ps.mark(key, FAILED)
                self.state.save()
                continue

            result = self._invoke(prompt, label=label, stage=stage, critical=critical)
            outcome.ran += 1
            outcome.cost_usd += result.cost_usd

            if result.ok:
                for key in batch:
                    ps.mark(key, DONE)
                outcome.completed.extend(batch)
                self.on_batch_complete(batch, result)
            else:
                for key in batch:
                    ps.mark(key, FAILED)
                outcome.skipped.extend(batch)
                self.log.error(f"batch failed after retries: {result.error[:200]}")
            self.state.save()

        outcome.gate = self._gate_and_repair(outcome)
        return self._finish(outcome)

    def _is_critical(self, batch: list[str]) -> bool:
        return any(key in self.critical_stages for key in batch)

    def _invoke(self, prompt: str, *, label: str, stage: str, critical: bool = False) -> RunResult:
        self.budget.guard(self.number, stage, ignore_phase_cap=critical)
        model, provider = self.manifest.model_for_phase(self.number)
        result = self.runner.run(
            prompt,
            label=label,
            phase=self.number,
            stage=stage,
            model=model,
            provider=provider,
        )
        if self.runner.is_dry:
            # A dry run must not touch the ledger. Writing to it would corrupt a
            # later real run's spend total and seed its cost estimates with
            # numbers no provider ever charged.
            return result
        self.budget.record(
            phase=self.number,
            stage=stage,
            label=label,
            cost_usd=result.cost_usd,
            ok=result.ok,
            attempt=result.attempts,
            usage=result.usage,
            note=result.error[:200] if result.error else "",
        )
        self.log.cost(result.cost_usd, self.budget.spent(), self.budget.total_usd)
        return result

    def _trim(self, outcome: PhaseOutcome, ps, remaining: list[str], reason: str) -> None:
        """Budget ran out mid-phase: record what was dropped and stop cleanly."""
        for key in remaining:
            ps.mark(key, SKIPPED)
        outcome.skipped.extend(remaining)
        outcome.trimmed = True
        self.state.record_trim(
            self.number,
            "budget",
            f"{len(remaining)} item(s) not processed — {reason}",
            dropped=remaining[:50],
        )
        if outcome.completed:
            self.log.warn(
                f"phase {self.number}: stopping at batch boundary, "
                f"{len(remaining)} item(s) unprocessed ({reason})"
            )
            return
        # Nothing at all ran. This phase did not produce a partial result, it
        # produced none — every later phase would be working from nothing, so
        # the run stops here rather than walking through them.
        outcome.stopped = f"phase {self.number} could not start: {reason}"
        self.log.error(outcome.stopped)

    # ── gates ───────────────────────────────────────────────────────────
    def _gate_and_repair(self, outcome: PhaseOutcome) -> GateReport | None:
        if self.runner.is_dry:
            # A dry run writes nothing, so every gate would fail on an empty
            # project — noise that buries the plan the user asked for.
            return None
        if not outcome.completed and not self.state.phase(self.number).done() and not self.gate_if_empty:
            return None

        report = gates_mod.run_gate(self.root, self.number, self.manifest)
        self.log.gate(report)
        if report.passed:
            return report

        if not outcome.completed:
            # The phase produced nothing, so the gate is reporting absence, not
            # malformation. A repair pass here would improvise the phase's own
            # output — which looks like success and is not.
            self.log.warn(
                f"gate {self.number} failed but the phase produced nothing; "
                "not repairing (repair fixes work, it does not do it)"
            )
            return report

        attempts = int(self.manifest.gates.get("repair_attempts", 1))
        for attempt in range(1, attempts + 1):
            ok, _ = self.budget.check(self.number, "repair")
            if not ok:
                self.log.warn("no budget left for repair; recording failures and continuing")
                break
            self.log.info(f"gate {self.number} failed — repair pass {attempt}/{attempts}")
            result = self._invoke(
                self._repair_prompt(report), label=f"p{self.number}-repair-{attempt}", stage="repair"
            )
            outcome.cost_usd += result.cost_usd
            report = gates_mod.run_gate(self.root, self.number, self.manifest)
            self.log.gate(report)
            if report.passed:
                break

        if not report.passed:
            self.state.phase(self.number).notes.append(
                f"gate failed: {len(report.fatal)} fatal, {len(report.errors)} errors"
            )
        return report

    def _repair_prompt(self, report: GateReport) -> str:
        return self.render("repair.md", phase=self.number, failures=report.repair_brief())

    # ── completion ──────────────────────────────────────────────────────
    def _finish(self, outcome: PhaseOutcome, status: str | None = None) -> PhaseOutcome:
        if status is None:
            gate = outcome.gate
            fatal = bool(gate and gate.fatal)
            status = FAILED if (fatal and self.manifest.strict) else DONE
            if outcome.stopped:
                status = PENDING
            elif self._work_remains():
                # Budget stopped this phase short. Leaving it PENDING is what
                # makes `--resume --budget 35` come back and finish it; the
                # pipeline still moves on now, because reaching Phase 5 with a
                # smaller graph beats stalling here with none.
                status = PENDING
        if status == DONE:
            self.budget.mark_phase_complete(self.number)
            self.on_phase_complete(outcome)
        self.state.finish_phase(self.number, status)
        self.ctx.commit(f"phase {self.number}: {self.name.lower()}", outcome)
        self.log.phase_done(self.number, outcome)
        return outcome

    def _work_remains(self) -> bool:
        return any(v in (PENDING, SKIPPED) for v in self.state.phase(self.number).items.values())

    # ── prompt rendering ────────────────────────────────────────────────
    def render(self, template: str, **fields: Any) -> str:
        """Render `prompts/<template>` with the phase preamble prepended.

        `str.format` rather than a template engine, so literal braces in a
        prompt must be doubled — the JSON examples in the templates do this, and
        `tests/test_prompts.py` renders every template to catch the ones that
        forget.
        """
        context = {**self._common_fields(), **fields}
        preamble = _read_prompt("_preamble.md").format(**context, spec_refs=self._spec_refs())
        body = _read_prompt(template).format(**context)
        return f"{preamble}\n\n---\n\n{body}\n"

    def _spec_refs(self) -> str:
        if not self.specs:
            return "- (none required for this stage)"
        return "\n".join(f"- `{s}`" for s in self.specs)

    def _common_fields(self) -> dict[str, Any]:
        m = self.manifest
        return {
            "project": m.project,
            "topic": m.topic,
            "question": m.question,
            "project_dir": self.root,
            "methodology_dir": METHODOLOGY_DIR,
            "phase": self.number,
            "phase_name": self.name,
            "tag": m.tag,
            "slug_prefix": m.slug_prefix or "(no prefix)",
            "topics": ", ".join(m.topics) or "(none seeded yet)",
            "claim_types": ", ".join(m.claim_types),
            "evidence_types": ", ".join(m.evidence_types),
            "edge_types": ", ".join(m.edge_types),
            "note_domains": ", ".join(m.note_domains),
            "confidence_levels": ", ".join(_confidence_levels()),
            "claims_min": m.claims_per_note[0],
            "claims_max": m.claims_per_note[1],
        }


_PROMPT_CACHE: dict[str, str] = {}


def _read_prompt(name: str) -> str:
    if name not in _PROMPT_CACHE:
        _PROMPT_CACHE[name] = (PROMPT_DIR / name).read_text(encoding="utf-8")
    return _PROMPT_CACHE[name]


def _confidence_levels() -> tuple[str, ...]:
    from ..manifest import CONFIDENCE_LEVELS

    return CONFIDENCE_LEVELS


def markdown_table(rows: list[dict[str, Any]], columns: Sequence[str], limit: int = 60) -> str:
    """A pipe table for embedding in a prompt. Empty rows yield '(none)'."""
    if not rows:
        return "_(none)_"
    head = "| " + " | ".join(columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = [
        "| " + " | ".join(str(r.get(c, "")).replace("|", "\\|").replace("\n", " ") for c in columns) + " |"
        for r in rows[:limit]
    ]
    out = "\n".join([head, rule, *body])
    if len(rows) > limit:
        out += f"\n\n_({len(rows) - limit} more not shown)_"
    return out


def bullet_list(items: Iterable[str], limit: int = 200) -> str:
    items = list(items)
    if not items:
        return "_(none)_"
    out = "\n".join(f"- {i}" for i in items[:limit])
    if len(items) > limit:
        out += f"\n- _({len(items) - limit} more)_"
    return out
