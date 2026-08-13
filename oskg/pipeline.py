"""The orchestrator — runs phases 0 through 5 over one project.

Holds what every phase needs (manifest, state, budget, runner, logging, git) and
drives them in order, stopping cleanly when the budget runs out.

The rule that shapes the control flow: **the pipeline always tries to reach
Phase 5.** A 120-claim graph with full edges and a capstone is worth more than a
380-claim pile with neither, so a phase that runs out of allowance stops at a
batch boundary and hands control on rather than consuming the phases after it.
Only a fatal gate failure under `gates.strict` aborts.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from . import gitutil
from .budget import Budget, BudgetExhausted, Ledger
from .gates import GateReport
from .manifest import Manifest
from .phases import PHASE_CLASSES, PhaseOutcome
from .progress import update_progress
from .runner import Runner, RunnerError
from .state import RunState

__all__ = ["Pipeline", "PipelineContext", "Logger", "RunSummary"]


class Logger:
    """Terminal output. Quiet enough to leave running overnight in a tmux pane."""

    def __init__(self, *, verbose: bool = False, stream=None, use_colour: bool | None = None):
        self.verbose = verbose
        self.stream = stream or sys.stdout
        self.colour = self.stream.isatty() if use_colour is None else use_colour
        self.started = time.monotonic()

    def _c(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.colour else text

    def _emit(self, text: str) -> None:
        print(text, file=self.stream, flush=True)

    def plain(self, text: str) -> None:
        self._emit(text)

    def info(self, text: str) -> None:
        self._emit(f"  {text}")

    def warn(self, text: str) -> None:
        self._emit(self._c(f"  ! {text}", "33"))

    def error(self, text: str) -> None:
        self._emit(self._c(f"  ✗ {text}", "31"))

    def phase(self, number: int, name: str) -> None:
        elapsed = int(time.monotonic() - self.started)
        header = f"── Phase {number}: {name} "
        self._emit("")
        self._emit(self._c(header + "─" * max(4, 68 - len(header)) + f" {elapsed // 60}m", "1;36"))

    def batch(self, phase: int, items: Sequence[str], remaining: float) -> None:
        preview = ", ".join(Path(i).name for i in items[:3])
        if len(items) > 3:
            preview += f" +{len(items) - 3}"
        self._emit(f"  → {preview}  {self._c(f'(${remaining:.2f} left in phase)', '90')}")

    def cost(self, call: float, spent: float, total: float) -> None:
        if self.verbose or call > 0:
            self._emit(self._c(f"    ${call:.4f} · ${spent:.2f}/${total:.2f} total", "90"))

    def gate(self, report: GateReport) -> None:
        if report.passed:
            stats = " · ".join(f"{k}={v}" for k, v in report.stats.items())
            self._emit(self._c(f"  ✓ gate {report.phase} passed  {stats}", "32"))
        else:
            self._emit(report.format(verbose=self.verbose))

    def phase_done(self, number: int, outcome: PhaseOutcome) -> None:
        bits = [f"{len(outcome.completed)} done"]
        if outcome.skipped:
            bits.append(f"{len(outcome.skipped)} skipped")
        bits.append(f"${outcome.cost_usd:.2f}")
        self._emit(f"  phase {number}: " + " · ".join(bits))


@dataclass
class PipelineContext:
    """Everything a phase driver needs."""

    project_dir: Path
    manifest: Manifest
    state: RunState
    budget: Budget
    runner: Runner
    log: Logger
    git_enabled: bool = True
    #: Set when `--from-phase` was given. Phases that would otherwise skip
    #: because their output already exists regenerate instead.
    forced: bool = False
    _git_warned: bool = False

    def commit(self, message: str, outcome: PhaseOutcome | None = None) -> None:
        if not self.git_enabled or self.runner.is_dry:
            return
        if not gitutil.is_repo(self.project_dir):
            # Scaffolded with --no-git and resumed without it. That is a choice,
            # not a failure, and repeating it once per phase is just noise.
            if not self._git_warned:
                self._git_warned = True
                self.log.info("not a git repository — skipping per-phase commits")
            return
        detail = ""
        if outcome:
            detail = f"\n\n{len(outcome.completed)} items, ${outcome.cost_usd:.2f}"
            if outcome.skipped:
                detail += f", {len(outcome.skipped)} skipped"
        ok, out = gitutil.commit(self.project_dir, f"oskg: {message}{detail}")
        if not ok and not self._git_warned:
            self._git_warned = True
            self.log.warn(f"git commit failed: {out[:160]}")


@dataclass
class RunSummary:
    project_dir: Path
    outcomes: list[PhaseOutcome] = field(default_factory=list)
    stopped: str = ""
    spent_usd: float = 0.0

    @property
    def reached_phase(self) -> int:
        return max((o.phase for o in self.outcomes), default=-1)

    @property
    def has_capstone(self) -> bool:
        return (self.project_dir / "notes" / "synthesis" / "capstone.md").exists()

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_dir": str(self.project_dir),
            "reached_phase": self.reached_phase,
            "spent_usd": round(self.spent_usd, 4),
            "stopped": self.stopped,
            "capstone": self.has_capstone,
            "phases": [
                {
                    "phase": o.phase,
                    "completed": len(o.completed),
                    "skipped": len(o.skipped),
                    "cost_usd": round(o.cost_usd, 4),
                    "gate_passed": o.gate.passed if o.gate else None,
                    "trimmed": o.trimmed,
                }
                for o in self.outcomes
            ],
        }


class Pipeline:
    def __init__(
        self,
        project_dir: Path | str,
        manifest: Manifest,
        runner: Runner,
        *,
        logger: Logger | None = None,
        git_enabled: bool = True,
        on_phase: Callable[[PhaseOutcome], None] | None = None,
    ):
        self.project_dir = Path(project_dir)
        self.manifest = manifest
        self.state = RunState.load(self.project_dir)
        self.state.project = manifest.project
        self.state.topic = manifest.topic
        self.ledger = Ledger(self.project_dir / ".oskg" / "ledger.jsonl")
        self.budget = Budget.from_manifest(manifest, self.ledger, self.state.completed_phases())
        self.log = logger or Logger()
        self.on_phase = on_phase
        self.ctx = PipelineContext(
            project_dir=self.project_dir,
            manifest=manifest,
            state=self.state,
            budget=self.budget,
            runner=runner,
            log=self.log,
            git_enabled=git_enabled,
        )

    def run(self, *, from_phase: int | None = None, through_phase: int = 5) -> RunSummary:
        summary = RunSummary(project_dir=self.project_dir)
        start = from_phase if from_phase is not None else (self.state.next_phase() or 0)

        if from_phase is not None:
            # "--from-phase 3" means redo edges onward. Clearing the work lists
            # is what makes that happen — leaving them marked done would walk
            # the phases and do nothing.
            self.ctx.forced = True
            for number in range(from_phase, through_phase + 1):
                self.state.reset_phase(number)
            self.budget.completed_phases = {
                n for n in self.state.completed_phases() if n < from_phase
            }

        self.log.plain(
            f"{self.manifest.project} — ${self.manifest.total_usd:.2f} budget, "
            f"${self.budget.spent():.2f} already spent, starting at phase {start}"
        )

        for number in range(start, through_phase + 1):
            if from_phase is None and self.state.is_done(number):
                self.log.info(f"phase {number} already complete — skipping")
                continue

            try:
                outcome = PHASE_CLASSES[number](self.ctx).run()
            except BudgetExhausted as exc:
                summary.stopped = str(exc)
                self.state.stop(str(exc))
                self.log.warn(str(exc))
                break
            except RunnerError as exc:
                summary.stopped = f"runner failed: {exc}"
                self.state.stop(summary.stopped)
                self.log.error(str(exc))
                break
            except KeyboardInterrupt:
                summary.stopped = "interrupted"
                self.state.stop("interrupted by user")
                self.log.warn("interrupted — state saved; `oskg build --resume` picks up here")
                break

            summary.outcomes.append(outcome)
            if self.on_phase:
                self.on_phase(outcome)
            self._write_progress()

            if outcome.stopped:
                summary.stopped = outcome.stopped
                break
            if outcome.gate and outcome.gate.fatal and self.manifest.strict:
                summary.stopped = f"phase {number} gate failed fatally (gates.strict is on)"
                self.state.stop(summary.stopped)
                self.log.error(summary.stopped)
                break

        summary.spent_usd = self.budget.spent()
        self._write_progress()
        self.ctx.commit("progress")
        self._report(summary)
        return summary

    def _write_progress(self) -> None:
        try:
            update_progress(self.project_dir, self.manifest, self.state, self.budget)
        except OSError as exc:
            self.log.warn(f"could not update PROGRESS.md: {exc}")

    def _report(self, summary: RunSummary) -> None:
        self.log.plain("")
        self.log.plain("─" * 72)
        pct = (summary.spent_usd / self.manifest.total_usd * 100) if self.manifest.total_usd else 0
        self.log.plain(
            f"Spent ${summary.spent_usd:.2f} of ${self.manifest.total_usd:.2f} ({pct:.0f}%) "
            f"across {self.ledger.call_count()} calls"
        )
        if summary.stopped:
            self.log.warn(f"stopped: {summary.stopped}")
        if self.state.trims:
            self.log.warn(f"{len(self.state.trims)} scope trims — see PROGRESS.md")
        if summary.has_capstone:
            self.log.plain(f"Capstone: {self.project_dir / 'notes' / 'synthesis' / 'capstone.md'}")
        else:
            nxt = self.state.next_phase()
            if nxt is not None:
                self.log.plain(f"Next: `oskg build --resume` (phase {nxt})")
        self.log.plain(f"Project: {self.project_dir}")
