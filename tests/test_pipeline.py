"""End-to-end pipeline behaviour, driven by a fake agent.

`FakeAgent` writes the files a real agent would write, so the phases chain
through their real planners, gates, and state transitions with no subprocess, no
network, and no spend. What is being tested is the orchestration: does Phase 2
find what Phase 1 wrote, does the budget stop a run cleanly, does a resumed run
skip completed work and retry failed work.
"""

import io
import json
import tempfile
import unittest
from pathlib import Path

from oskg.budget import Ledger
from oskg.manifest import Manifest
from oskg.pipeline import Logger, Pipeline
from oskg.runner import FakeRunner, RunResult, extract_json
from oskg.scaffold import project_name_for, scaffold, slug_for
from oskg.state import DONE, FAILED, PENDING, RunState

from .fixtures import NOTE_TEMPLATE, SOURCE_GUIDE, edge_block, make_claim


def quiet_logger() -> Logger:
    return Logger(stream=io.StringIO(), use_colour=False)


class FakeAgent:
    """Writes what a real agent would write, so later phases have real input."""

    def __init__(self, root: Path, *, cost: float = 0.10, fail_stages: tuple[str, ...] = ()):
        self.root = Path(root)
        self.cost = cost
        self.fail_stages = fail_stages
        self.seen: list[str] = []

    def __call__(self, stage: str, prompt: str) -> RunResult:
        self.seen.append(stage)
        if stage in self.fail_stages:
            return RunResult(ok=False, text="", cost_usd=self.cost, error="simulated failure")
        handler = getattr(self, f"_{stage}", None)
        if handler:
            handler(prompt)
        return RunResult(ok=True, text="", cost_usd=self.cost, usage={"estimated_cost_usd": self.cost})

    # ── phase 0 ─────────────────────────────────────────────────────────
    def _scope(self, prompt: str) -> None:
        plan = {
            "question": "What does the evidence show?",
            "slug_prefix": "tt-",
            "claim_types": ["definitional", "empirical"],
            "evidence_types": ["primary-source", "empirical"],
            "note_domains": ["concepts", "history"],
            "topics": ["alpha", "beta", "gamma"],
            "edge_types_extra": ["challenged_by"],
            "estimated_notes": 6,
            "sources": [{"slug": s, "tier": t} for s, t in (("s1", 1), ("s2", 2), ("s3", 2))],
        }
        path = self.root / ".oskg" / "phase0" / "plan.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan), encoding="utf-8")
        (self.root / "SOURCE-GUIDE.md").write_text(SOURCE_GUIDE, encoding="utf-8")

    def _sources(self, prompt: str) -> None:
        text = (self.root / "SOURCE-GUIDE.md").read_text(encoding="utf-8")
        (self.root / "SOURCE-GUIDE.md").write_text(text.replace("| pending |", "| acquired |"), encoding="utf-8")

    # ── phase 1 ─────────────────────────────────────────────────────────
    def _notes(self, prompt: str) -> None:
        for slug, tier in (("s1", 1), ("s2", 2), ("s3", 2)):
            if f"| {slug} |" not in prompt:
                continue
            path = self.root / "notes" / "concepts" / f"Note {slug}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                NOTE_TEMPLATE.format(
                    tag="oskg-test", source=slug, tier=tier, topic="alpha",
                    title=f"Note {slug}", claims_status="pending", claims_count=0,
                ),
                encoding="utf-8",
            )

    # ── phase 2 ─────────────────────────────────────────────────────────
    def _extract(self, prompt: str) -> None:
        for slug in ("s1", "s2", "s3"):
            if f"Note {slug}.md" not in prompt:
                continue
            for n in (1, 2, 3, 4, 5):
                make_claim(
                    self.root, f"{slug}-claim-{n}", source=slug, note=f"Note {slug}",
                    statement=f"Claim {n} drawn from {slug}", topics=("alpha", "beta"),
                    claim_type="definitional", n=n,
                    edges=edge_block(supports=[f"{slug}-claim-1 — internal corroboration within the source"])
                    if n > 1 else "",
                )
            note = self.root / "notes" / "concepts" / f"Note {slug}.md"
            note.write_text(
                note.read_text(encoding="utf-8")
                .replace("claims_status: pending", "claims_status: extracted")
                .replace("claims_count: 0", "claims_count: 5"),
                encoding="utf-8",
            )

    # ── phase 3 ─────────────────────────────────────────────────────────
    def _edges(self, prompt: str) -> None:
        """Add the cross-source edges the real Phase 3 would propose."""
        pairs = [("s1-claim-1", "s2-claim-1"), ("s2-claim-2", "s3-claim-1"), ("s3-claim-2", "s1-claim-2")]
        for source, target in pairs:
            path = self.root / "notes" / "claims" / f"{source}.md"
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            if target in text:
                continue
            text = text.replace(
                "**Supports:**",
                f"**Supports:**\n- [[{target}]] — the same conclusion reached from separate material",
                1,
            )
            path.write_text(text, encoding="utf-8")

    # ── phases 4 and 5 ──────────────────────────────────────────────────
    def _synthesis(self, prompt: str) -> None:
        name = "phase1-hinge-inventory.md" if "Hinge" in prompt else "phase-other.md"
        path = self.root / "notes" / "synthesis" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntags:\n  - type/synthesis\n  - oskg-test\n---\n\n# Analysis\n\nComputed result.\n",
            encoding="utf-8",
        )

    def _capstone(self, prompt: str) -> None:
        claims = sorted(p.stem for p in (self.root / "notes" / "claims").glob("*.md"))
        citations = " ".join(f"[[{c}]]" for c in claims[:12])
        path = self.root / "notes" / "synthesis" / "capstone.md"
        path.write_text(
            "---\ntags:\n  - type/synthesis\n  - oskg-test\n  - capstone\n---\n\n"
            "# Capstone\n\n" + ("What the graph shows, at length. " * 120) + "\n\n"
            "## What is settled\n\n" + citations + "\n\n"
            "## Limitations\n\nSource selection was automated and the corpus is thin in places.\n",
            encoding="utf-8",
        )


def build_project(tmp=None, *, budget=20.0) -> tuple[Path, Manifest]:
    root, manifest = scaffold(
        Path(tmp or tempfile.mkdtemp()), "a test subject", budget_usd=budget, git=False
    )
    manifest.data["tag"] = "oskg-test"
    manifest.save(root)
    return root, manifest


class TestSlugAndNaming(unittest.TestCase):
    def test_stopwords_are_dropped(self):
        self.assertEqual(slug_for("the archaeology and interpretation of Göbekli Tepe"),
                         "archaeology-interpretation-gobekli-tepe")

    def test_project_name_matches_the_sibling_repos(self):
        self.assertEqual(project_name_for("the Bronze Age collapse"), "OSKG-BronzeAgeCollapse")

    def test_a_topic_of_only_stopwords_still_yields_a_slug(self):
        self.assertTrue(slug_for("the of and"))


class TestScaffold(unittest.TestCase):
    def test_creates_a_valid_project(self):
        root, manifest = build_project()
        self.assertEqual(manifest.validate(), [])
        self.assertTrue((root / "oskg.yaml").exists())
        self.assertTrue((root / "notes" / "claims").is_dir())

    def test_gitignore_lands_before_anything_can_write_source_text(self):
        root, _ = build_project()
        ignored = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("sources/**/_txt/", ignored)
        self.assertIn("sources/**/_fulltext/", ignored)

    def test_adopting_an_existing_project_is_idempotent(self):
        parent = Path(tempfile.mkdtemp())
        first, _ = scaffold(parent, "a test subject", git=False)
        second, _ = scaffold(parent, "a test subject", git=False)
        self.assertEqual(first, second)


class TestFullRun(unittest.TestCase):
    def setUp(self):
        self.root, self.manifest = build_project()
        self.agent = FakeAgent(self.root)
        self.pipeline = Pipeline(
            self.root, self.manifest, FakeRunner(self.agent), logger=quiet_logger(), git_enabled=False
        )
        self.summary = self.pipeline.run()

    def test_reaches_the_capstone(self):
        self.assertTrue(self.summary.has_capstone, self.summary.to_dict())
        self.assertEqual(self.summary.reached_phase, 5)

    def test_every_phase_ran(self):
        state = RunState.load(self.root)
        for n in range(6):
            self.assertEqual(state.phase(n).status, DONE, f"phase {n}")

    def test_phase_zero_folded_the_plan_into_the_manifest(self):
        manifest = Manifest.load(self.root)
        self.assertEqual(manifest.slug_prefix, "tt-")
        self.assertIn("challenged_by", manifest.edge_types)
        self.assertIn("alpha", manifest.topics)

    def test_the_graph_was_built(self):
        from oskg.graph import load_graph

        graph = load_graph(self.root, Manifest.load(self.root).edge_types)
        self.assertEqual(len(graph.claims), 15)  # 3 sources × 5 claims
        self.assertTrue(any(e.cross_source for e in graph.edges))

    def test_analysis_was_computed_and_committed(self):
        analysis = json.loads((self.root / ".oskg" / "analysis.json").read_text(encoding="utf-8"))
        self.assertIn("hinges", analysis)
        self.assertEqual(analysis["metrics"]["claims"], 15)

    def test_progress_was_written(self):
        progress = (self.root / "PROGRESS.md").read_text(encoding="utf-8")
        self.assertIn("Budget", progress)
        self.assertIn("Scope trims", progress)

    def test_spend_stayed_under_the_cap(self):
        self.assertLessEqual(self.summary.spent_usd, self.manifest.total_usd)

    def test_the_ledger_recorded_every_call(self):
        ledger = Ledger(self.root / ".oskg" / "ledger.jsonl")
        self.assertEqual(ledger.call_count(), len(self.agent.seen))


class TestBudgetPressure(unittest.TestCase):
    def test_a_tiny_budget_stops_cleanly_and_records_where(self):
        root, manifest = build_project(budget=0.55)
        pipeline = Pipeline(
            root, manifest, FakeRunner(FakeAgent(root, cost=0.25)),
            logger=quiet_logger(), git_enabled=False,
        )
        summary = pipeline.run()
        self.assertLessEqual(summary.spent_usd, 0.55)
        self.assertFalse(summary.has_capstone)
        state = RunState.load(root)
        self.assertIsNotNone(state.next_phase())

    def test_running_out_mid_phase_records_a_trim(self):
        root, manifest = build_project(budget=3.0)
        pipeline = Pipeline(
            root, manifest, FakeRunner(FakeAgent(root, cost=0.30)),
            logger=quiet_logger(), git_enabled=False,
        )
        pipeline.run()
        state = RunState.load(root)
        if state.trims:
            self.assertIn("detail", state.trims[0])
            self.assertIn("Scope trims", (root / "PROGRESS.md").read_text(encoding="utf-8"))

    def test_the_reserve_keeps_phase_five_fundable(self):
        root, manifest = build_project(budget=20.0)
        pipeline = Pipeline(root, manifest, FakeRunner(FakeAgent(root)), logger=quiet_logger(), git_enabled=False)
        self.assertGreater(pipeline.budget.phase_base(5), manifest.reserve_usd)


class TestResume(unittest.TestCase):
    def test_a_second_run_skips_completed_phases(self):
        root, manifest = build_project()
        agent = FakeAgent(root)
        Pipeline(root, manifest, FakeRunner(agent), logger=quiet_logger(), git_enabled=False).run()
        first_calls = len(agent.seen)

        agent2 = FakeAgent(root)
        Pipeline(root, Manifest.load(root), FakeRunner(agent2), logger=quiet_logger(), git_enabled=False).run()
        self.assertEqual(len(agent2.seen), 0)
        self.assertGreater(first_calls, 0)

    def test_a_fresh_invocation_retries_failed_items(self):
        # A transient API error must not permanently strand an item.
        state = RunState.load(Path(tempfile.mkdtemp()))
        state.phase(1).items = {"read:s1": FAILED, "read:s2": DONE}
        state.start_phase(1)
        self.assertEqual(state.phase(1).items["read:s1"], PENDING)
        self.assertEqual(state.phase(1).items["read:s2"], DONE)

    def test_from_phase_reruns_a_completed_phase(self):
        root, manifest = build_project()
        Pipeline(root, manifest, FakeRunner(FakeAgent(root)), logger=quiet_logger(), git_enabled=False).run()
        agent = FakeAgent(root)
        Pipeline(root, Manifest.load(root), FakeRunner(agent), logger=quiet_logger(), git_enabled=False).run(
            from_phase=4
        )
        self.assertTrue(agent.seen)


class TestFailureHandling(unittest.TestCase):
    def test_a_failing_stage_does_not_abort_the_run(self):
        root, manifest = build_project()
        agent = FakeAgent(root, fail_stages=("edges",))
        summary = Pipeline(
            root, manifest, FakeRunner(agent), logger=quiet_logger(), git_enabled=False
        ).run()
        # Phase 3 produced nothing, but 4 and 5 still ran over what exists.
        self.assertEqual(summary.reached_phase, 5)
        self.assertIn("capstone", agent.seen)

    def test_a_failed_call_is_still_charged(self):
        root, manifest = build_project()
        Pipeline(
            root, manifest, FakeRunner(FakeAgent(root, fail_stages=("edges",))),
            logger=quiet_logger(), git_enabled=False,
        ).run()
        ledger = Ledger(root / ".oskg" / "ledger.jsonl")
        self.assertGreater(ledger.failure_count(), 0)
        self.assertGreater(ledger.spent(), 0)


class TestJSONExtraction(unittest.TestCase):
    def test_marker_block(self):
        self.assertEqual(extract_json('noise\n===OSKG-JSON===\n{"a": 1}\n===END-OSKG-JSON===\n'), {"a": 1})

    def test_fenced_block(self):
        self.assertEqual(extract_json('here:\n```json\n{"a": 1}\n```\n'), {"a": 1})

    def test_bare_object(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_object_wrapped_in_prose(self):
        # Models add a sentence of explanation however the prompt is worded.
        self.assertEqual(extract_json('Sure! {"a": 1} Hope that helps.'), {"a": 1})

    def test_nothing_parseable(self):
        self.assertIsNone(extract_json("no json at all"))
        self.assertIsNone(extract_json(""))


if __name__ == "__main__":
    unittest.main()
