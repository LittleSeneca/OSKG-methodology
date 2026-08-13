"""`oskg` — the command line.

    oskg build "<topic>" --budget 20      scaffold and run the whole pipeline
    oskg build --resume                   continue where a run left off
    oskg status                           phase, spend, remaining
    oskg gate --phase 2                   run a quality gate by hand
    oskg analyze                          recompute the structural analysis (free)
    oskg export --format json             the graph, for a real query layer
    oskg validate                         check oskg.yaml

`build` defaults to `--dry-run`-able and never publishes: a generated project is
local until `--github` says otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__, gitutil
from .analysis import analyze, format_summary, write_analysis
from .budget import Budget, Ledger
from .gates import run_gate, run_gates
from .graph import load_graph
from .manifest import Manifest, ManifestError
from .pipeline import Logger, Pipeline
from .runner import DryRunner, HermesRunner, RunnerError
from .scaffold import scaffold
from .state import RunState

DEFAULT_BUDGET = 20.0
EXIT_OK, EXIT_ERROR, EXIT_FATAL, EXIT_NOPROJECT = 0, 1, 2, 3


# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="oskg",
        description="Build an Open Source Knowledge Graph from one prompt, under a budget.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  oskg build "the Bronze Age collapse" --budget 20 --dry-run
  oskg build "the Bronze Age collapse" --budget 20
  oskg build --resume --budget 35
  oskg status --ledger
  oskg gate --phase 2 --fix
  oskg analyze
""",
    )
    p.add_argument("--version", action="version", version=f"oskg {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="scaffold and run the pipeline")
    b.add_argument("topic", nargs="?", help="what the graph should be about")
    b.add_argument("--budget", type=float, default=None, help=f"USD cap (default {DEFAULT_BUDGET})")
    b.add_argument("--project", help="project directory name (default: derived from the topic)")
    b.add_argument("--parent", default=None, help="where to create it (default: alongside this repo)")
    b.add_argument("--resume", action="store_true", help="continue an existing project")
    b.add_argument("--dry-run", action="store_true", help="plan and price it; make no calls")
    b.add_argument("--from-phase", type=int, choices=range(6), help="restart at this phase")
    b.add_argument("--through-phase", type=int, choices=range(6), default=5, help="stop after this phase")
    b.add_argument("--model", help="model override (passed to hermes -m)")
    b.add_argument("--provider", help="provider override (requires --model)")
    b.add_argument("--strict", action="store_true", help="abort on a fatal gate failure")
    b.add_argument("--no-git", action="store_true", help="do not create or commit to a git repo")
    b.add_argument("--github", action="store_true", help="also create a private GitHub repo and push")
    b.add_argument("--public", action="store_true", help="with --github, make it public")
    b.add_argument("-v", "--verbose", action="store_true")

    s = sub.add_parser("status", help="phase, spend, remaining")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--ledger", action="store_true", help="every call")
    s.add_argument("--json", action="store_true")

    g = sub.add_parser("gate", help="run quality gates")
    g.add_argument("project", nargs="?", default=".")
    g.add_argument("--phase", type=int, choices=range(6), help="one phase (default: all so far)")
    g.add_argument("--fix", action="store_true", help="run one LLM repair pass on failures")
    g.add_argument("--json", action="store_true")
    g.add_argument("-v", "--verbose", action="store_true", help="include warnings")

    a = sub.add_parser("analyze", help="recompute the structural analysis (free)")
    a.add_argument("project", nargs="?", default=".")
    a.add_argument("--json", action="store_true")

    e = sub.add_parser("export", help="export the graph")
    e.add_argument("project", nargs="?", default=".")
    e.add_argument("--format", choices=("json", "edges", "dot"), default="json")
    e.add_argument("-o", "--output", help="write here instead of stdout")

    v = sub.add_parser("validate", help="check oskg.yaml")
    v.add_argument("project", nargs="?", default=".")

    sc = sub.add_parser("scaffold", help="create a project without running the pipeline")
    sc.add_argument("topic")
    sc.add_argument("--budget", type=float, default=DEFAULT_BUDGET)
    sc.add_argument("--project")
    sc.add_argument("--parent", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = {
        "build": cmd_build,
        "status": cmd_status,
        "gate": cmd_gate,
        "analyze": cmd_analyze,
        "export": cmd_export,
        "validate": cmd_validate,
        "scaffold": cmd_scaffold,
    }[args.command]
    try:
        return handler(args)
    except ManifestError as exc:
        print(f"oskg: {exc}", file=sys.stderr)
        return EXIT_FATAL
    except RunnerError as exc:
        print(f"oskg: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\noskg: interrupted — state saved", file=sys.stderr)
        return EXIT_ERROR


# ─────────────────────────────────────────────────────────────────────────────
# build
# ─────────────────────────────────────────────────────────────────────────────


def cmd_build(args) -> int:
    log = Logger(verbose=args.verbose)

    if args.resume or not args.topic:
        found = _find_project(Path(args.project or ".").expanduser())
        if found is None:
            print(
                "oskg: no project here to resume. Give a topic:\n"
                '  oskg build "the Bronze Age collapse" --budget 20',
                file=sys.stderr,
            )
            return EXIT_NOPROJECT
        root = found
        manifest = Manifest.load(root)
        log.plain(f"Resuming {manifest.project} at {root}")
    else:
        parent = Path(args.parent).expanduser() if args.parent else _default_parent()
        root, manifest = scaffold(
            parent,
            args.topic,
            budget_usd=args.budget if args.budget is not None else DEFAULT_BUDGET,
            project_name=args.project,
            model=args.model,
            provider=args.provider,
            git=not args.no_git,
        )
        log.plain(f"Created {manifest.project} at {root}")

    _apply_overrides(manifest, args)
    manifest.save(root)

    runner = _make_runner(root, manifest, args, log)
    if isinstance(runner, HermesRunner):
        runner.preflight()

    pipeline = Pipeline(root, manifest, runner, logger=log, git_enabled=not args.no_git)
    summary = pipeline.run(from_phase=args.from_phase, through_phase=args.through_phase)

    if args.dry_run:
        _print_dry_run(runner, manifest, pipeline.budget, log)
        return EXIT_OK

    if args.github and not args.no_git:
        _publish(root, manifest, args, log)

    if summary.stopped and not summary.has_capstone:
        return EXIT_ERROR
    return EXIT_OK


def _apply_overrides(manifest: Manifest, args) -> None:
    if getattr(args, "budget", None) is not None:
        manifest.data.setdefault("budget", {})["total_usd"] = float(args.budget)
    if getattr(args, "model", None):
        manifest.data.setdefault("model", {})["default"] = args.model
    if getattr(args, "provider", None):
        manifest.data.setdefault("model", {})["provider"] = args.provider
    if getattr(args, "strict", False):
        manifest.data.setdefault("gates", {})["strict"] = True
    problems = manifest.validate()
    if problems:
        raise ManifestError(problems)


def _make_runner(root: Path, manifest: Manifest, args, log: Logger):
    if args.dry_run:
        ledger = Ledger(root / ".oskg" / "ledger.jsonl")
        budget = Budget.from_manifest(manifest, ledger)
        log.plain("DRY RUN — planning only, no calls and no spend")
        return DryRunner(estimator=budget.estimate)
    return HermesRunner(root, on_event=_event_logger(log) if args.verbose else None)


def _event_logger(log: Logger):
    def handler(event: str, data: dict) -> None:
        if event == "call_start" and data.get("attempt", 1) > 1:
            log.warn(f"retry {data['attempt']} for {data['label']}")
    return handler


def _print_dry_run(runner, manifest: Manifest, budget: Budget, log: Logger) -> None:
    """What the plan actually cost, then what the budget would buy overall.

    The walked plan stops early on a fresh project — Phases 1-5 need a source
    list Phase 0 has not written — so the projection is what answers the
    question the user asked by running `--dry-run` at all.
    """
    from .projection import format_projection, project_run

    calls = getattr(runner, "calls", [])
    log.plain("")
    if calls:
        total = sum(c["estimated_usd"] for c in calls)
        log.plain(f"Walked plan: {len(calls)} calls, ~${total:.2f}")
        by_phase: dict[int, list[Any]] = {}
        for call in calls:
            by_phase.setdefault(call["phase"], []).append(call)
        for phase, items in sorted(by_phase.items()):
            cost = sum(i["estimated_usd"] for i in items)
            log.plain(f"  phase {phase}: {len(items)} calls  ~${cost:.2f}")
        log.plain("")
    log.plain(format_projection(project_run(manifest, budget)))


def _publish(root: Path, manifest: Manifest, args, log: Logger) -> None:
    """Create a GitHub repo. Only ever reached behind an explicit --github."""
    log.plain("")
    ok, out = gitutil.create_github_repo(
        root,
        manifest.project,
        private=not args.public,
        description=f"OSKG: {manifest.topic}"[:350],
    )
    if ok:
        log.plain(f"Published: {out.strip().splitlines()[-1] if out.strip() else manifest.project}")
    else:
        log.error(f"could not create the GitHub repo: {out[:300]}")


# ─────────────────────────────────────────────────────────────────────────────
# status
# ─────────────────────────────────────────────────────────────────────────────


def cmd_status(args) -> int:
    root = _require_project(args.project)
    if root is None:
        return EXIT_NOPROJECT
    manifest = Manifest.load(root, validate=False)
    state = RunState.load(root)
    ledger = Ledger(root / ".oskg" / "ledger.jsonl")
    budget = Budget.from_manifest(manifest, ledger, state.completed_phases())

    if args.json:
        print(json.dumps({"state": state.summary(), "budget": budget.summary()}, indent=2))
        return EXIT_OK

    from .progress import PHASE_NAMES

    print(f"{manifest.project} — {manifest.topic}")
    print(f"  {root}")
    print()
    spent, total = budget.spent(), manifest.total_usd
    pct = (spent / total * 100) if total else 0
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    print(f"  Budget  {bar}  ${spent:.2f} / ${total:.2f} ({pct:.0f}%)")
    print(f"  Calls   {ledger.call_count()} ({ledger.failure_count()} failed)")
    print()
    for number, name in PHASE_NAMES.items():
        ps = state.phases.get(number)
        status = ps.status if ps else "pending"
        counts = ps.counts() if ps else {}
        detail = " · ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        mark = {"done": "✓", "running": "◐", "failed": "✗", "pending": "·"}.get(status, "·")
        print(
            f"  {mark} {number}. {name:26} ${ledger.spent_in_phase(number):6.2f}"
            + (f"   {detail}" if detail else "")
        )
    if state.trims:
        print()
        print(f"  ! {len(state.trims)} scope trims — see PROGRESS.md")
        for trim in state.trims[-3:]:
            print(f"      phase {trim['phase']}: {trim['detail']}")
    if state.stopped_reason:
        print()
        print(f"  stopped: {state.stopped_reason}")

    if args.ledger:
        print()
        print("  ts                    phase  stage      cost      label")
        for e in ledger.entries:
            flag = "" if e.ok else "  FAILED"
            print(f"  {e.ts}  {e.phase:^5}  {e.stage:<9}  ${e.cost_usd:7.4f}  {e.label}{flag}")
    return EXIT_OK


# ─────────────────────────────────────────────────────────────────────────────
# gate / analyze / export / validate / scaffold
# ─────────────────────────────────────────────────────────────────────────────


def cmd_gate(args) -> int:
    root = _require_project(args.project)
    if root is None:
        return EXIT_NOPROJECT
    manifest = Manifest.load(root, validate=False)

    if args.phase is not None:
        reports = [run_gate(root, args.phase, manifest)]
    else:
        state = RunState.load(root)
        through = max(state.completed_phases(), default=0)
        reports = run_gates(root, manifest, through)

    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    else:
        for report in reports:
            print(report.format(verbose=args.verbose))

    worst = max((r.exit_code() for r in reports), default=EXIT_OK)
    if args.fix and worst != EXIT_OK:
        return _repair(root, manifest, reports, args)
    return worst


def _repair(root: Path, manifest: Manifest, reports, args) -> int:
    """One targeted LLM repair pass over the failures, then re-gate."""
    from .phases.base import Phase

    failing = [r for r in reports if not r.passed]
    if not failing:
        return EXIT_OK

    log = Logger(verbose=args.verbose)
    state = RunState.load(root)
    ledger = Ledger(root / ".oskg" / "ledger.jsonl")
    budget = Budget.from_manifest(manifest, ledger, state.completed_phases())
    runner = HermesRunner(root)
    runner.preflight()

    from .pipeline import PipelineContext

    ctx = PipelineContext(root, manifest, state, budget, runner, log)
    for report in failing:
        driver = _driver_for(report.phase, ctx)
        log.plain(f"Repairing phase {report.phase} ({len(report.errors)} errors)…")
        result = driver._invoke(  # deliberate: the repair path is the base class's
            driver._repair_prompt(report), label=f"gate-fix-p{report.phase}", stage="repair"
        )
        if not result.ok:
            log.error(f"repair failed: {result.error[:200]}")
        again = run_gate(root, report.phase, manifest)
        log.gate(again)
    return EXIT_OK


def _driver_for(phase: int, ctx):
    from .phases import PHASE_CLASSES

    return PHASE_CLASSES[phase](ctx)


def cmd_analyze(args) -> int:
    root = _require_project(args.project)
    if root is None:
        return EXIT_NOPROJECT
    manifest = Manifest.load(root, validate=False)
    graph = load_graph(root, manifest.edge_types)
    if not graph.claims:
        print("oskg: no claims to analyze", file=sys.stderr)
        return EXIT_ERROR

    result = analyze(graph)
    write_analysis(root, result)
    graph.write_edge_index(root / ".oskg" / "edges.json")
    print(json.dumps(result, indent=2) if args.json else format_summary(result))
    return EXIT_OK


def cmd_export(args) -> int:
    root = _require_project(args.project)
    if root is None:
        return EXIT_NOPROJECT
    manifest = Manifest.load(root, validate=False)
    graph = load_graph(root, manifest.edge_types)

    if args.format == "json":
        text = json.dumps(graph.export(), indent=2)
    elif args.format == "edges":
        text = json.dumps(graph.edge_index(), indent=2)
    else:
        text = _to_dot(graph, manifest)

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return EXIT_OK


def _to_dot(graph, manifest: Manifest) -> str:
    styles = {
        "supports": 'color="#2a7"',
        "contradicts": 'color="#d33" style=bold',
        "extends": 'color="#37a"',
        "depends_on": 'color="#333" style=dashed',
    }
    lines = [f'digraph "{manifest.project}" {{', "  rankdir=LR;", "  node [shape=box, fontsize=9];"]
    for slug, claim in sorted(graph.active_claims.items()):
        label = (claim.statement or slug).replace('"', "'")[:60]
        lines.append(f'  "{slug}" [label="{label}", tooltip="{claim.source}"];')
    for e in graph.edges:
        lines.append(f'  "{e.source}" -> "{e.target}" [{styles.get(e.type, "")} label="{e.type}"];')
    lines.append("}")
    return "\n".join(lines)


def cmd_validate(args) -> int:
    root = _require_project(args.project)
    if root is None:
        return EXIT_NOPROJECT
    manifest = Manifest.load(root, validate=False)
    problems = manifest.validate()
    if not problems:
        print(f"oskg.yaml is valid — {manifest.project}, ${manifest.total_usd:.2f} budget")
        return EXIT_OK
    print(f"oskg.yaml has {len(problems)} problem(s):", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    return EXIT_FATAL


def cmd_scaffold(args) -> int:
    parent = Path(args.parent).expanduser() if args.parent else _default_parent()
    root, manifest = scaffold(parent, args.topic, budget_usd=args.budget, project_name=args.project)
    print(f"Created {manifest.project} at {root}")
    print(f"  oskg build --resume   # from inside {root.name}/")
    return EXIT_OK


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _default_parent() -> Path:
    """Sibling of this repo, matching how the other OSKG projects are laid out."""
    return Path(__file__).resolve().parent.parent.parent


def _find_project(start: Path) -> Path | None:
    """Nearest ancestor holding an `oskg.yaml`."""
    start = start.expanduser().resolve()
    for candidate in (start, *start.parents):
        if (candidate / "oskg.yaml").exists():
            return candidate
    return None


def _require_project(path: str) -> Path | None:
    root = _find_project(Path(path))
    if root is None:
        print(
            f"oskg: no oskg.yaml in {Path(path).expanduser().resolve()} or any parent.\n"
            '  Create one with: oskg build "<topic>"',
            file=sys.stderr,
        )
    return root


if __name__ == "__main__":
    sys.exit(main())
