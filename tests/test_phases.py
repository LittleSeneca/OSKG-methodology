"""Phase-driver behaviour that the end-to-end run does not pin down.

These are the rules the live runs taught: scoping is a precondition and cannot
be blocked by a phase share, a phase that produced nothing must not be
"repaired" into looking successful, and Phase 0's two kinds of work bill
separately.
"""

import io
import tempfile
import unittest
from pathlib import Path

from oskg.budget import Budget, Ledger
from oskg.pipeline import Logger, PipelineContext
from oskg.phases import PHASE_CLASSES
from oskg.runner import FakeRunner, RunResult
from oskg.state import RunState

from .fixtures import make_graph_project, make_note, make_project


def context_for(root, manifest, runner=None) -> PipelineContext:
    ledger = Ledger(Path(root) / ".oskg" / "ledger.jsonl")
    return PipelineContext(
        project_dir=Path(root),
        manifest=manifest,
        state=RunState.load(root),
        budget=Budget.from_manifest(manifest, ledger),
        runner=runner or FakeRunner(),
        log=Logger(stream=io.StringIO(), use_colour=False),
        git_enabled=False,
    )


class TestPhaseZero(unittest.TestCase):
    def test_scoping_bills_separately_from_acquisition(self):
        # Averaging a $0.05 scoping call with a $0.08 acquisition call
        # mispredicts both.
        root, manifest = make_project(tempfile.mkdtemp())
        driver = PHASE_CLASSES[0](context_for(root, manifest))
        self.assertEqual(driver.stage_for(["scope"]), "scope")
        self.assertEqual(driver.stage_for(["acquire:s1", "acquire:s2"]), "sources")

    def test_scoping_is_admitted_against_the_total_cap(self):
        # A tiny phase-0 share must not skip the call the whole run depends on.
        root, manifest = make_project(tempfile.mkdtemp(), budget=3.0)
        manifest.data["budget"]["allocation"] = {
            "phase0": 0.01, "phase1": 0.40, "phase2": 0.31,
            "phase3": 0.16, "phase4": 0.07, "phase5": 0.05,
        }
        ctx = context_for(root, manifest)
        driver = PHASE_CLASSES[0](ctx)
        self.assertTrue(driver._is_critical(["scope"]))
        blocked, _ = ctx.budget.check(0, "scope")
        allowed, _ = ctx.budget.check(0, "scope", ignore_phase_cap=True)
        self.assertFalse(blocked)
        self.assertTrue(allowed)

    def test_acquisition_is_not_critical(self):
        root, manifest = make_project(tempfile.mkdtemp())
        driver = PHASE_CLASSES[0](context_for(root, manifest))
        self.assertFalse(driver._is_critical(["acquire:s1"]))

    def test_acquisition_queues_after_the_scope_call(self):
        # The source list only exists once scoping has run, so acquisition
        # items cannot be planned up front.
        root, manifest = make_project(tempfile.mkdtemp())
        ctx = context_for(root, manifest)
        driver = PHASE_CLASSES[0](ctx)
        (root / ".oskg" / "phase0").mkdir(parents=True, exist_ok=True)
        (root / ".oskg" / "phase0" / "plan.json").write_text("{}", encoding="utf-8")
        driver.on_batch_complete(["scope"], RunResult(ok=True, text="", cost_usd=0.0))
        queued = ctx.state.phase(0).pending()
        self.assertTrue(any(k.startswith("acquire:") for k in queued), queued)

    def test_an_invalid_plan_does_not_corrupt_the_manifest(self):
        root, manifest = make_project(tempfile.mkdtemp())
        driver = PHASE_CLASSES[0](context_for(root, manifest))
        driver._apply_plan(
            {
                "note_domains": ["claims", "synthesis"],  # both reserved
                "edge_types_extra": ["invented_type"],
                "claim_types": ["definitional", "empirical"],
            }
        )
        self.assertEqual(manifest.validate(), [])
        self.assertNotIn("claims", manifest.note_domains)
        self.assertNotIn("invented_type", manifest.edge_types)

    def test_edge_type_extensions_keep_their_underscores(self):
        # `challenged_by` normalised to `challenged-by` would fail the
        # allow-list and vanish silently.
        root, manifest = make_project(tempfile.mkdtemp())
        driver = PHASE_CLASSES[0](context_for(root, manifest))
        driver._apply_plan({"edge_types_extra": ["challenged_by", "Exception To"]})
        self.assertIn("challenged_by", manifest.edge_types)
        self.assertIn("exception_to", manifest.edge_types)


class TestPhaseOne(unittest.TestCase):
    def test_only_acquired_sources_are_planned(self):
        root, manifest = make_project(tempfile.mkdtemp())
        planned = PHASE_CLASSES[1](context_for(root, manifest)).plan()
        # The fixture guide has s1-s3 acquired and s4 pending.
        self.assertEqual(sorted(planned), ["read:s1", "read:s2", "read:s3"])

    def test_canon_is_read_first(self):
        # Tier-1 claims become the edge targets every later batch attaches to.
        root, manifest = make_project(tempfile.mkdtemp())
        self.assertEqual(PHASE_CLASSES[1](context_for(root, manifest)).plan()[0], "read:s1")

    def test_a_tight_budget_trims_from_the_bottom_tier(self):
        root, manifest = make_project(tempfile.mkdtemp(), budget=1.2)
        ctx = context_for(root, manifest)
        planned = PHASE_CLASSES[1](ctx).plan()
        self.assertLessEqual(len(planned), 3)
        self.assertIn("read:s1", planned)  # Tier 1 is never dropped


class TestPhaseThree(unittest.TestCase):
    def test_only_multi_source_clusters_are_planned(self):
        # A single-source cluster yields intra-source edges, which organize one
        # book and connect nothing.
        root, manifest = make_project(tempfile.mkdtemp())
        from .fixtures import make_claim

        make_note(root, "Note One")
        for i in range(5):
            make_claim(root, f"solo-{i}", source="s1", topics=("lonely",))
        self.assertEqual(PHASE_CLASSES[3](context_for(root, manifest)).plan(), [])

    def test_a_multi_source_cluster_is_planned(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.assertIn("alpha", PHASE_CLASSES[3](context_for(root, manifest)).plan())

    def test_edge_target_is_a_range_not_a_quota(self):
        # A hard number invites edge spam to fill it.
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.assertIn("-", PHASE_CLASSES[3](context_for(root, manifest))._target_edges(20, 3))


class TestPhaseFour(unittest.TestCase):
    def test_analysis_is_computed_during_planning_before_any_spend(self):
        # So a build that exhausts its budget here still leaves the computed
        # structure behind.
        root, manifest = make_graph_project(tempfile.mkdtemp())
        PHASE_CLASSES[4](context_for(root, manifest)).plan()
        self.assertTrue((root / ".oskg" / "analysis.json").exists())

    def test_only_analyses_with_content_are_written_up(self):
        root, manifest = make_project(tempfile.mkdtemp())
        self.assertEqual(PHASE_CLASSES[4](context_for(root, manifest)).plan(), [])


class TestPhaseFive(unittest.TestCase):
    def test_no_analysis_means_no_capstone(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        self.assertEqual(PHASE_CLASSES[5](context_for(root, manifest)).plan(), [])

    def test_an_existing_capstone_is_not_rewritten(self):
        root, manifest = make_graph_project(tempfile.mkdtemp())
        from oskg.analysis import analyze, write_analysis
        from oskg.graph import load_graph

        write_analysis(root, analyze(load_graph(root, manifest.edge_types)))
        (root / "notes" / "synthesis" / "capstone.md").write_text("# Capstone\n", encoding="utf-8")
        ctx = context_for(root, manifest)
        self.assertEqual(PHASE_CLASSES[5](ctx).plan(), [])

        ctx.forced = True  # --from-phase 5
        self.assertEqual(PHASE_CLASSES[5](ctx).plan(), ["capstone"])


class TestRepairPolicy(unittest.TestCase):
    def test_repair_does_not_run_when_the_phase_produced_nothing(self):
        # Otherwise the repair pass improvises the phase's own output, which
        # looks like success and is not.
        root, manifest = make_project(tempfile.mkdtemp())
        (root / "SOURCE-GUIDE.md").unlink()
        runner = FakeRunner()
        ctx = context_for(root, manifest, runner)
        ctx.budget.total_usd = 0.0001  # nothing can run

        outcome = PHASE_CLASSES[0](ctx).run()
        self.assertEqual(outcome.completed, [])
        self.assertEqual(runner.calls, [])
        self.assertTrue(outcome.stopped)


if __name__ == "__main__":
    unittest.main()
