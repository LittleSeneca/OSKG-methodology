"""Invoking Hermes, and paying for it.

One-shot mode (`hermes -z`) is the only mode that reports what a call cost, via
`--usage-file`. That report is written even when the run fails, which is what
makes the ledger total rather than approximate.

The tradeoff, worth knowing before you go looking for it: `-z` also ignores
`--skills`, so nothing is preloaded. Prompts therefore point the agent at the
spec file it needs (`Read spec/claim-node.md and follow it`) instead of relying
on a skill being installed — which keeps a generated project self-contained.

`Runner` is an interface with three implementations: `HermesRunner` spends money,
`DryRunner` prices a plan without spending any, and `FakeRunner` (tests) replays
scripted responses.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

__all__ = ["Runner", "HermesRunner", "DryRunner", "FakeRunner", "RunResult", "RunnerError"]

DEFAULT_TIMEOUT = 1800  # 30 minutes; a Tier-1 extraction batch is the long pole
RETRY_BACKOFF = (5, 30)  # seconds before attempt 2, then attempt 3

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)
_JSON_MARKER_RE = re.compile(r"===OSKG-JSON===\s*(.*?)\s*===END-OSKG-JSON===", re.DOTALL)


class RunnerError(RuntimeError):
    """The agent could not be run at all — binary missing, timeout, killed."""


@dataclass
class RunResult:
    """One completed (or failed) agent invocation."""

    ok: bool
    text: str
    cost_usd: float
    usage: dict[str, Any] = field(default_factory=dict)
    attempts: int = 1
    error: str = ""
    duration_s: float = 0.0

    def json(self) -> Any | None:
        """Structured payload from the response text, if the agent emitted one.

        Phases prefer artifacts on disk — a file the agent wrote is unambiguous
        and survives a truncated response. This is the fallback for when it
        answered inline instead.
        """
        return extract_json(self.text)


def extract_json(text: str) -> Any | None:
    """Pull a JSON object out of agent output: markers, then fence, then bare."""
    if not text:
        return None
    for pattern in (_JSON_MARKER_RE, _JSON_FENCE_RE):
        for m in pattern.finditer(text):
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    stripped = text.strip()
    if stripped[:1] in "{[":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    # Last resort: the outermost brace-delimited span. Models like to wrap JSON
    # in a sentence of explanation no matter how the prompt is worded.
    start, end = stripped.find("{"), stripped.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


class Runner:
    """Interface: run a prompt, get text and a cost."""

    def run(
        self,
        prompt: str,
        *,
        label: str,
        phase: int,
        stage: str,
        model: str | None = None,
        provider: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> RunResult:
        raise NotImplementedError

    @property
    def is_dry(self) -> bool:
        return False


class HermesRunner(Runner):
    """Runs `hermes -z` in the project directory and prices every call."""

    def __init__(
        self,
        project_dir: Path | str,
        *,
        binary: str = "hermes",
        retries: int = 2,
        on_event: Callable[[str, dict], None] | None = None,
        keep_prompts: bool = True,
    ):
        self.project_dir = Path(project_dir)
        self.binary = binary
        self.retries = max(0, retries)
        self.on_event = on_event or (lambda *_: None)
        self.keep_prompts = keep_prompts
        self.tmp_dir = self.project_dir / ".oskg" / "tmp"

    def preflight(self) -> None:
        """Fail before spending anything if the environment cannot run a build."""
        if shutil.which(self.binary) is None:
            raise RunnerError(
                f"{self.binary!r} not found on PATH. Install Hermes, or pass --runner dry "
                f"to plan without running anything."
            )
        if not self.project_dir.is_dir():
            raise RunnerError(f"project directory does not exist: {self.project_dir}")

    def run(
        self,
        prompt: str,
        *,
        label: str,
        phase: int,
        stage: str,
        model: str | None = None,
        provider: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> RunResult:
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", label)[:80] or "call"
        usage_path = self.tmp_dir / f"{safe}.usage.json"
        prompt_path = self.tmp_dir / f"{safe}.prompt.txt"
        if self.keep_prompts:
            prompt_path.write_text(prompt, encoding="utf-8")

        cmd = [self.binary, "-z", prompt, "--usage-file", str(usage_path)]
        if model:
            cmd += ["-m", model]
            # hermes rejects --provider without --model: carrying a configured
            # model to a provider that may not host it fails at request time.
            if provider:
                cmd += ["--provider", provider]

        last: RunResult | None = None
        for attempt in range(1, self.retries + 2):
            self.on_event("call_start", {"label": label, "stage": stage, "attempt": attempt})
            result = self._invoke(cmd, usage_path, timeout, attempt)
            self.on_event(
                "call_end",
                {
                    "label": label,
                    "stage": stage,
                    "attempt": attempt,
                    "ok": result.ok,
                    "cost_usd": result.cost_usd,
                    "error": result.error,
                },
            )
            if result.ok:
                result.attempts = attempt
                return result
            last = result
            if attempt <= self.retries:
                time.sleep(RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)])

        assert last is not None
        last.attempts = self.retries + 1
        return last

    def _invoke(self, cmd: list[str], usage_path: Path, timeout: int, attempt: int) -> RunResult:
        if usage_path.exists():
            usage_path.unlink()  # never report a stale run's cost as this one's

        env = dict(os.environ)
        env["HERMES_ACCEPT_HOOKS"] = "1"  # unattended: a hook prompt would hang forever

        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
            stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            stdout, stderr, code = "", f"timed out after {timeout}s", 124
        except OSError as exc:
            raise RunnerError(f"could not execute {cmd[0]!r}: {exc}") from exc

        duration = time.monotonic() - started
        usage = _read_usage(usage_path)
        cost = float(usage.get("estimated_cost_usd") or 0.0)

        # A run that failed still spent money, and the usage file is written on
        # failure precisely so it can be charged. Never discard a nonzero cost.
        ok = code == 0 and not usage.get("failed", False)
        error = "" if ok else (usage.get("failure") or stderr.strip() or f"exit {code}")[:500]
        return RunResult(
            ok=ok,
            text=stdout.strip(),
            cost_usd=cost,
            usage=usage,
            attempts=attempt,
            error=error,
            duration_s=duration,
        )


def _read_usage(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # No usage file means hermes died before writing one. Cost is unknown;
        # reporting zero is the only honest option, and the ledger records the
        # failure so a run of unknown-cost failures is still visible.
        return {}


class DryRunner(Runner):
    """Prices a plan without calling anything. `--dry-run`."""

    def __init__(self, estimator: Callable[[str], float] | None = None):
        self.calls: list[dict[str, Any]] = []
        self._estimator = estimator or (lambda _stage: 0.15)

    @property
    def is_dry(self) -> bool:
        return True

    def run(
        self,
        prompt: str,
        *,
        label: str,
        phase: int,
        stage: str,
        model: str | None = None,
        provider: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> RunResult:
        cost = self._estimator(stage)
        self.calls.append(
            {
                "label": label,
                "phase": phase,
                "stage": stage,
                "estimated_usd": cost,
                "prompt_chars": len(prompt),
            }
        )
        return RunResult(
            ok=True,
            text="",
            cost_usd=cost,
            usage={"estimated_cost_usd": cost, "model": model or "", "dry_run": True},
        )


class FakeRunner(Runner):
    """Scripted responses for tests. No subprocess, no network, no spend."""

    def __init__(self, responses: list[RunResult] | Callable[[str, str], RunResult] | None = None):
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def run(
        self,
        prompt: str,
        *,
        label: str,
        phase: int,
        stage: str,
        model: str | None = None,
        provider: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> RunResult:
        self.calls.append({"label": label, "phase": phase, "stage": stage, "prompt": prompt})
        if callable(self._responses):
            return self._responses(stage, prompt)
        if isinstance(self._responses, list) and self._responses:
            return self._responses.pop(0)
        return RunResult(ok=True, text="", cost_usd=0.01, usage={"estimated_cost_usd": 0.01})
