"""Run state — what is done, what is pending, where to resume.

`.oskg/state.json` is the answer to "what happens if this is killed at 3am". It
records phase status and a per-item work list, so a resumed build re-does no
completed work and, more importantly, skips no pending work.

Written after every meaningful step, atomically (temp file + replace), because
the failure mode this file exists to survive is a process dying mid-write.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

__all__ = ["RunState", "PhaseState", "PENDING", "RUNNING", "DONE", "FAILED", "SKIPPED"]

PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
SKIPPED = "skipped"

STATE_VERSION = 1


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class PhaseState:
    status: str = PENDING
    started: str = ""
    finished: str = ""
    items: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "started": self.started,
            "finished": self.finished,
            "items": dict(self.items),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PhaseState":
        return cls(
            status=str(d.get("status") or PENDING),
            started=str(d.get("started") or ""),
            finished=str(d.get("finished") or ""),
            items={str(k): str(v) for k, v in (d.get("items") or {}).items()},
            notes=[str(n) for n in (d.get("notes") or [])],
        )

    # ── work list ───────────────────────────────────────────────────────
    def enqueue(self, keys: Iterable[str]) -> None:
        """Add keys as pending. Never resets one that already has a status —
        re-planning a phase must not un-complete finished work."""
        for k in keys:
            self.items.setdefault(str(k), PENDING)

    def pending(self) -> list[str]:
        return [k for k, v in self.items.items() if v == PENDING]

    def done(self) -> list[str]:
        return [k for k, v in self.items.items() if v == DONE]

    def mark(self, key: str, status: str) -> None:
        self.items[str(key)] = status

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.items.values():
            out[v] = out.get(v, 0) + 1
        return out


@dataclass
class RunState:
    """Full pipeline state, persisted to `.oskg/state.json`."""

    path: Path
    version: int = STATE_VERSION
    project: str = ""
    topic: str = ""
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    current_phase: int = 0
    phases: dict[int, PhaseState] = field(default_factory=dict)
    trims: list[dict[str, Any]] = field(default_factory=list)
    stopped_reason: str = ""

    # ── persistence ─────────────────────────────────────────────────────
    @classmethod
    def load(cls, project_dir: Path | str) -> "RunState":
        path = Path(project_dir) / ".oskg" / "state.json"
        if not path.exists():
            return cls(path=path)
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A corrupt state file must not strand a project. Starting from
            # scratch re-derives phase status from what is on disk, and the
            # ledger — which is append-only — still has the spend.
            return cls(path=path)
        return cls(
            path=path,
            version=int(d.get("version") or STATE_VERSION),
            project=str(d.get("project") or ""),
            topic=str(d.get("topic") or ""),
            created=str(d.get("created") or _now()),
            updated=str(d.get("updated") or _now()),
            current_phase=int(d.get("current_phase") or 0),
            phases={int(k): PhaseState.from_dict(v) for k, v in (d.get("phases") or {}).items()},
            trims=list(d.get("trims") or []),
            stopped_reason=str(d.get("stopped_reason") or ""),
        )

    def save(self) -> None:
        self.updated = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "project": self.project,
            "topic": self.topic,
            "created": self.created,
            "updated": self.updated,
            "current_phase": self.current_phase,
            "phases": {str(k): v.to_dict() for k, v in sorted(self.phases.items())},
            "trims": self.trims,
            "stopped_reason": self.stopped_reason,
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a kill mid-write leaves the old file

    # ── phase access ────────────────────────────────────────────────────
    def phase(self, n: int) -> PhaseState:
        return self.phases.setdefault(int(n), PhaseState())

    def start_phase(self, n: int) -> PhaseState:
        ps = self.phase(n)
        if ps.status in (PENDING, FAILED):
            ps.status = RUNNING
            ps.started = ps.started or _now()
        # A fresh invocation retries what failed and what the budget skipped.
        # A transient API error should not permanently strand an item, and
        # `oskg build --resume --budget 35` is supposed to pick up exactly the
        # work the smaller budget could not reach. Called once per phase per
        # run, so a failure inside this run is not retried until the next one,
        # and the cap bounds how many times that can happen.
        for key, status in list(ps.items.items()):
            if status in (FAILED, SKIPPED):
                ps.items[key] = PENDING
        self.current_phase = int(n)
        self.save()
        return ps

    def reset_phase(self, n: int) -> PhaseState:
        """Forget a phase entirely, so `--from-phase` genuinely redoes it."""
        self.phases[int(n)] = PhaseState()
        self.save()
        return self.phases[int(n)]

    def finish_phase(self, n: int, status: str = DONE) -> None:
        ps = self.phase(n)
        ps.status = status
        ps.finished = _now()
        self.save()

    def completed_phases(self) -> set[int]:
        return {n for n, ps in self.phases.items() if ps.status == DONE}

    def is_done(self, n: int) -> bool:
        return self.phase(n).status == DONE

    def next_phase(self) -> int | None:
        """Lowest phase 0-5 not yet done, or None when the pipeline is finished."""
        for n in range(6):
            if not self.is_done(n):
                return n
        return None

    # ── scope trims ─────────────────────────────────────────────────────
    def record_trim(self, phase: int, kind: str, detail: str, dropped: Any = None) -> None:
        """Record scope removed under budget pressure.

        A graph that silently covered less than it claimed is worse than a small
        graph that says so. Every trim also lands in PROGRESS.md.
        """
        self.trims.append(
            {"ts": _now(), "phase": phase, "kind": kind, "detail": detail, "dropped": dropped}
        )
        self.phase(phase).notes.append(f"TRIM [{kind}] {detail}")
        self.save()

    def stop(self, reason: str) -> None:
        self.stopped_reason = reason
        self.save()

    # ── reporting ───────────────────────────────────────────────────────
    def summary(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "topic": self.topic,
            "current_phase": self.current_phase,
            "updated": self.updated,
            "stopped_reason": self.stopped_reason,
            "phases": {
                n: {"status": ps.status, "items": ps.counts()} for n, ps in sorted(self.phases.items())
            },
            "trims": len(self.trims),
        }
