"""The budget governor: ledger, per-phase allocation, and the hard cap.

Every model call is priced by Hermes (`--usage-file`) and appended to an
append-only ledger. The governor answers three questions:

  * may this call proceed?         `check()` / `guard()`
  * how much can this phase spend?  `phase_ceiling()`
  * how many more units fit?        `affordable()`

The cap is hard. `estimate` is deliberately biased high, because overshooting
the cap is worse than stopping one batch early — a graph that is one batch short
is still a graph, and a build that quietly spends double is a build nobody runs
unattended again.

See spec/budget-model.md.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

__all__ = ["Budget", "BudgetExhausted", "LedgerEntry", "Ledger"]

# Seed estimates in USD per call, used before any call of that stage has been
# observed.
#
# Anchored on a measured baseline: a real Phase 0 call on deepseek-v4-pro via
# Hermes (13 API calls, 64k input, 16k output, substantial web research) cost
# $0.044. These sit at roughly 2-4x that, scaled by how input-heavy each stage
# is, which keeps them biased high without being absurd — overshooting the cap
# is worse than stopping a batch early, and the EWMA corrects a bad seed
# downward within one batch.
#
# See spec/budget-model.md.
SEED_ESTIMATES: dict[str, float] = {
    "scope": 0.12,     # heavy web research, but one call
    "sources": 0.20,   # search, download, extract, per batch of ~6 sources
    "notes": 0.25,     # long source text in, 1-4 reading notes out
    "extract": 0.25,   # 3 notes in, 15-30 claim files out — output-heavy
    "cluster": 0.05,
    "edges": 0.12,     # one topic cluster
    "verify": 0.08,
    "synthesis": 0.08, # write-up over an already-computed result
    "capstone": 0.15,  # long, but over condensed input
    "repair": 0.06,    # targeted at named failures
}
DEFAULT_SEED = 0.15

# Weight on the newest observation. Early batches run against a near-empty graph
# and mispredict later ones, so recent evidence dominates — but not completely,
# or one anomalous batch would set the estimate for the rest of the run.
EWMA_ALPHA = 0.4

# Multiplier applied to the estimate when deciding whether a call may proceed.
# Buys headroom for a call that runs longer than its predecessors.
SAFETY_FACTOR = 1.25


class BudgetExhausted(RuntimeError):
    """The cap would be exceeded. The run stops; state records where."""

    def __init__(self, spent: float, estimate: float, total: float, scope: str = "run"):
        self.spent, self.estimate, self.total, self.scope = spent, estimate, total, scope
        super().__init__(
            f"{scope} budget exhausted: spent ${spent:.4f} + est ${estimate:.4f} "
            f"would exceed ${total:.2f}"
        )


@dataclass
class LedgerEntry:
    ts: str
    phase: int
    stage: str
    label: str
    cost_usd: float
    ok: bool = True
    attempt: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    api_calls: int = 0
    model: str = ""
    provider: str = ""
    session_id: str = ""
    note: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LedgerEntry":
        known = {k: d.get(k, getattr(cls, k, None)) for k in cls.__annotations__}
        known["cost_usd"] = float(known.get("cost_usd") or 0.0)
        known["phase"] = int(known.get("phase") or 0)
        known["ok"] = bool(known.get("ok", True))
        for k in ("attempt", "input_tokens", "output_tokens", "api_calls"):
            known[k] = int(known.get(k) or 0)
        for k in ("stage", "label", "model", "provider", "session_id", "note", "ts"):
            known[k] = str(known.get(k) or "")
        return cls(**known)


class Ledger:
    """Append-only spend record at `.oskg/ledger.jsonl`.

    Append-only and never rewritten: a crashed run's spend must still count on
    resume, or a loop of crashes becomes a loop of free retries.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._entries: list[LedgerEntry] | None = None

    def append(self, entry: LedgerEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(entry.to_json() + "\n")
        if self._entries is not None:
            self._entries.append(entry)

    @property
    def entries(self) -> list[LedgerEntry]:
        if self._entries is None:
            self._entries = list(self._read())
        return self._entries

    def _read(self) -> Iterable[LedgerEntry]:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield LedgerEntry.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError):
                # A torn final line from a killed process. Skipping it
                # under-counts by one call; refusing to read the ledger at all
                # would under-count by the whole run.
                continue

    def reload(self) -> None:
        self._entries = None

    # ── aggregates ──────────────────────────────────────────────────────
    def spent(self) -> float:
        return sum(e.cost_usd for e in self.entries)

    def spent_in_phase(self, phase: int) -> float:
        return sum(e.cost_usd for e in self.entries if e.phase == phase)

    def observations(self, stage: str) -> list[float]:
        return [e.cost_usd for e in self.entries if e.stage == stage and e.ok]

    def by_phase(self) -> dict[int, float]:
        out: dict[int, float] = {}
        for e in self.entries:
            out[e.phase] = out.get(e.phase, 0.0) + e.cost_usd
        return out

    def call_count(self) -> int:
        return len(self.entries)

    def failure_count(self) -> int:
        return sum(1 for e in self.entries if not e.ok)

    def totals(self) -> dict[str, Any]:
        return {
            "calls": self.call_count(),
            "failures": self.failure_count(),
            "spent_usd": round(self.spent(), 6),
            "input_tokens": sum(e.input_tokens for e in self.entries),
            "output_tokens": sum(e.output_tokens for e in self.entries),
            "api_calls": sum(e.api_calls for e in self.entries),
            "by_phase": {k: round(v, 6) for k, v in sorted(self.by_phase().items())},
        }


@dataclass
class Budget:
    """Allocation, rollover, and the hard cap over a `Ledger`."""

    total_usd: float
    allocation: dict[str, float]
    ledger: Ledger
    reserve_usd: float = 0.5
    rollover: bool = True
    completed_phases: set[int] = field(default_factory=set)
    _estimates: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest, ledger: Ledger, completed_phases: Iterable[int] = ()) -> "Budget":
        return cls(
            total_usd=manifest.total_usd,
            allocation=manifest.allocation,
            ledger=ledger,
            reserve_usd=manifest.reserve_usd,
            rollover=manifest.rollover,
            completed_phases=set(completed_phases),
        )

    # ── totals ──────────────────────────────────────────────────────────
    def spent(self) -> float:
        return self.ledger.spent()

    def remaining(self) -> float:
        return max(0.0, self.total_usd - self.spent())

    @property
    def pool(self) -> float:
        """Spendable by phases 0-4. The reserve is held for the capstone."""
        return max(0.0, self.total_usd - self.reserve_usd)

    # ── per-phase ───────────────────────────────────────────────────────
    def phase_share(self, phase: int) -> float:
        return float(self.allocation.get(f"phase{phase}", 0.0))

    def phase_base(self, phase: int) -> float:
        # Phase 5 draws on the reserve as well: the whole point of holding it
        # back is that a capstone always gets written.
        base = self.phase_share(phase) * self.pool
        return base + self.reserve_usd if phase == 5 else base

    def phase_ceiling(self, phase: int) -> float:
        """This phase's allowance, including rollover from completed phases."""
        ceiling = self.phase_base(phase)
        if self.rollover:
            for done in sorted(self.completed_phases):
                if done < phase:
                    unspent = self.phase_base(done) - self.ledger.spent_in_phase(done)
                    ceiling += max(0.0, unspent)
        return min(ceiling, self.remaining() + self.ledger.spent_in_phase(phase))

    def phase_remaining(self, phase: int) -> float:
        return max(0.0, min(self.phase_ceiling(phase) - self.ledger.spent_in_phase(phase), self.remaining()))

    def mark_phase_complete(self, phase: int) -> None:
        self.completed_phases.add(phase)

    # ── estimation ──────────────────────────────────────────────────────
    def estimate(self, stage: str) -> float:
        """Expected cost of one `stage` call: EWMA over observations, seeded."""
        if stage in self._estimates:
            return self._estimates[stage]
        seed = SEED_ESTIMATES.get(stage, DEFAULT_SEED)
        observed = self.ledger.observations(stage)
        if not observed:
            self._estimates[stage] = seed
            return seed
        value = seed
        for cost in observed:
            value = EWMA_ALPHA * cost + (1 - EWMA_ALPHA) * value
        self._estimates[stage] = value
        return value

    def observe(self, stage: str, cost: float) -> None:
        current = self.estimate(stage)
        self._estimates[stage] = EWMA_ALPHA * cost + (1 - EWMA_ALPHA) * current

    # ── admission control ───────────────────────────────────────────────
    def check(
        self, phase: int, stage: str, *, count: int = 1, ignore_phase_cap: bool = False
    ) -> tuple[bool, str]:
        """May `count` calls of `stage` run in `phase`? (ok, reason).

        `ignore_phase_cap` is for a stage the whole run depends on — Phase 0's
        scoping call, which every later dollar is spent against. Letting a
        per-phase share block it produces a run that limps on with no corpus,
        which is worse than either finishing or stopping. Such a call is still
        bounded by the total cap.
        """
        need = self.estimate(stage) * count * SAFETY_FACTOR
        if self.spent() + need > self.total_usd:
            return False, (
                f"total cap: ${self.spent():.4f} spent + ${need:.4f} est > ${self.total_usd:.2f}"
            )
        if not ignore_phase_cap and need > self.phase_remaining(phase):
            return False, (
                f"phase {phase} allowance: ${self.phase_remaining(phase):.4f} left, "
                f"${need:.4f} needed"
            )
        return True, ""

    def guard(self, phase: int, stage: str, *, count: int = 1, ignore_phase_cap: bool = False) -> None:
        ok, reason = self.check(phase, stage, count=count, ignore_phase_cap=ignore_phase_cap)
        if not ok:
            scope = "run" if "total cap" in reason else f"phase {phase}"
            raise BudgetExhausted(self.spent(), self.estimate(stage) * count, self.total_usd, scope)

    def affordable(self, phase: int, stage: str) -> int:
        """How many more `stage` calls fit in this phase's remaining allowance."""
        unit = self.estimate(stage) * SAFETY_FACTOR
        if unit <= 0:
            return 0
        return max(0, int(self.phase_remaining(phase) // unit))

    # ── recording ───────────────────────────────────────────────────────
    def record(
        self,
        *,
        phase: int,
        stage: str,
        label: str,
        cost_usd: float,
        ok: bool = True,
        attempt: int = 1,
        usage: dict[str, Any] | None = None,
        note: str = "",
    ) -> LedgerEntry:
        usage = usage or {}
        entry = LedgerEntry(
            ts=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            phase=phase,
            stage=stage,
            label=label,
            cost_usd=float(cost_usd or 0.0),
            ok=ok,
            attempt=attempt,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            api_calls=int(usage.get("api_calls") or 0),
            model=str(usage.get("model") or ""),
            provider=str(usage.get("provider") or ""),
            session_id=str(usage.get("session_id") or ""),
            note=note,
        )
        self.ledger.append(entry)
        if ok:
            self.observe(stage, entry.cost_usd)
        return entry

    # ── reporting ───────────────────────────────────────────────────────
    def summary(self) -> dict[str, Any]:
        return {
            "total_usd": round(self.total_usd, 4),
            "reserve_usd": round(self.reserve_usd, 4),
            "spent_usd": round(self.spent(), 4),
            "remaining_usd": round(self.remaining(), 4),
            "phases": {
                f"phase{p}": {
                    "share": self.phase_share(p),
                    "ceiling_usd": round(self.phase_ceiling(p), 4),
                    "spent_usd": round(self.ledger.spent_in_phase(p), 4),
                    "remaining_usd": round(self.phase_remaining(p), 4),
                    "complete": p in self.completed_phases,
                }
                for p in sorted(int(k.replace("phase", "")) for k in self.allocation)
            },
            **self.ledger.totals(),
        }
