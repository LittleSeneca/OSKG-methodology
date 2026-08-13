"""The budget governor — the thing that makes an unattended run safe."""

import tempfile
import unittest
from pathlib import Path

from oskg.budget import EWMA_ALPHA, SAFETY_FACTOR, Budget, BudgetExhausted, Ledger
from oskg.manifest import default_manifest


def make_budget(total=20.0, reserve=0.5, tmp=None) -> Budget:
    root = Path(tmp or tempfile.mkdtemp())
    manifest = default_manifest(project="P", topic="t", slug="s", budget_usd=total)
    manifest.data["budget"]["reserve_usd"] = reserve
    return Budget.from_manifest(manifest, Ledger(root / "ledger.jsonl"))


class TestLedger(unittest.TestCase):
    def test_append_and_read_back(self):
        budget = make_budget()
        budget.record(phase=1, stage="notes", label="a", cost_usd=0.25)
        budget.record(phase=1, stage="notes", label="b", cost_usd=0.35)
        budget.ledger.reload()
        self.assertAlmostEqual(budget.ledger.spent(), 0.60)
        self.assertEqual(budget.ledger.call_count(), 2)

    def test_survives_a_torn_final_line(self):
        # A killed process can leave half a JSON line. Skipping it under-counts
        # by one call; refusing to read the file would under-count by the run.
        budget = make_budget()
        budget.record(phase=0, stage="scope", label="a", cost_usd=1.0)
        with budget.ledger.path.open("a", encoding="utf-8") as fh:
            fh.write('{"phase": 1, "cost_us')
        budget.ledger.reload()
        self.assertAlmostEqual(budget.ledger.spent(), 1.0)

    def test_failed_calls_still_cost(self):
        budget = make_budget()
        budget.record(phase=1, stage="notes", label="a", cost_usd=0.4, ok=False)
        self.assertAlmostEqual(budget.spent(), 0.4)
        self.assertEqual(budget.ledger.failure_count(), 1)


class TestAllocation(unittest.TestCase):
    def test_pool_excludes_the_reserve(self):
        budget = make_budget(total=20.0, reserve=0.5)
        self.assertAlmostEqual(budget.pool, 19.5)

    def test_phase_five_can_draw_on_the_reserve(self):
        # The reserve exists so a capstone always gets written.
        budget = make_budget(total=20.0, reserve=0.5)
        self.assertAlmostEqual(budget.phase_base(5), 0.05 * 19.5 + 0.5)

    def test_rollover_widens_later_phases(self):
        budget = make_budget(total=20.0, reserve=0.5)
        base_phase1 = budget.phase_base(1)
        budget.record(phase=0, stage="scope", label="a", cost_usd=0.10)
        budget.mark_phase_complete(0)
        self.assertGreater(budget.phase_ceiling(1), base_phase1)

    def test_rollover_can_be_disabled(self):
        budget = make_budget()
        budget.rollover = False
        budget.record(phase=0, stage="scope", label="a", cost_usd=0.10)
        budget.mark_phase_complete(0)
        self.assertAlmostEqual(budget.phase_ceiling(1), budget.phase_base(1))

    def test_ceiling_never_exceeds_what_is_left(self):
        budget = make_budget(total=20.0)
        budget.record(phase=0, stage="scope", label="a", cost_usd=19.0)
        self.assertLessEqual(budget.phase_ceiling(3), budget.remaining() + 1e-9)


class TestAdmissionControl(unittest.TestCase):
    def test_hard_cap_blocks_the_call_that_would_exceed_it(self):
        budget = make_budget(total=1.0, reserve=0.0)
        budget.record(phase=1, stage="notes", label="a", cost_usd=0.95)
        ok, reason = budget.check(1, "notes")
        self.assertFalse(ok)
        self.assertIn("total cap", reason)
        with self.assertRaises(BudgetExhausted):
            budget.guard(1, "notes")

    def test_phase_allowance_blocks_before_the_total_does(self):
        budget = make_budget(total=100.0, reserve=0.0)
        budget.record(phase=0, stage="scope", label="a", cost_usd=11.9)
        ok, reason = budget.check(0, "scope")
        self.assertFalse(ok)
        self.assertIn("phase 0", reason)
        self.assertGreater(budget.remaining(), 50)  # plenty left overall

    def test_estimates_carry_a_safety_margin(self):
        budget = make_budget(total=20.0)
        estimate = budget.estimate("notes")
        self.assertGreater(estimate * SAFETY_FACTOR, estimate)

    def test_affordable_counts_calls_that_fit(self):
        budget = make_budget(total=20.0)
        n = budget.affordable(1, "notes")
        unit = budget.estimate("notes") * SAFETY_FACTOR
        self.assertLessEqual(n * unit, budget.phase_remaining(1) + 1e-9)
        self.assertGreater(n, 0)


class TestEstimation(unittest.TestCase):
    def test_observation_moves_the_estimate_toward_reality(self):
        budget = make_budget()
        seed = budget.estimate("notes")
        budget.record(phase=1, stage="notes", label="a", cost_usd=seed * 3)
        self.assertGreater(budget.estimate("notes"), seed)

    def test_ewma_weights_the_newest_observation(self):
        budget = make_budget()
        seed = budget.estimate("extract")
        budget.observe("extract", 1.0)
        self.assertAlmostEqual(budget.estimate("extract"), EWMA_ALPHA * 1.0 + (1 - EWMA_ALPHA) * seed)

    def test_estimate_replays_a_resumed_ledger(self):
        # A resumed run must not re-seed from scratch and re-learn what the
        # previous run already paid to find out.
        tmp = tempfile.mkdtemp()
        first = make_budget(tmp=tmp)
        for _ in range(3):
            first.record(phase=1, stage="notes", label="x", cost_usd=1.0)
        second = make_budget(tmp=tmp)
        self.assertGreater(second.estimate("notes"), first.estimate("notes") * 0.8)

    def test_unknown_stage_falls_back_to_a_default(self):
        self.assertGreater(make_budget().estimate("no-such-stage"), 0)


class TestSummary(unittest.TestCase):
    def test_summary_covers_every_phase(self):
        budget = make_budget()
        budget.record(phase=2, stage="extract", label="a", cost_usd=0.5)
        summary = budget.summary()
        self.assertEqual(set(summary["phases"]), {f"phase{n}" for n in range(6)})
        self.assertAlmostEqual(summary["spent_usd"], 0.5)
        self.assertAlmostEqual(summary["phases"]["phase2"]["spent_usd"], 0.5)


if __name__ == "__main__":
    unittest.main()
