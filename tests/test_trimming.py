"""Scope trimming — the rule a live run taught.

A seed estimate is a guess; a ledger entry is a fact. Up-front trimming must
only ever act on facts. The first live build proved why: the `notes` seed was
$0.25 against a real $0.047, and Phase 1 cut a third of the corpus before
spending a cent — then finished having used $0.20 of a $1.34 allowance.

Nothing here spends anything; the ledger is written directly.
"""

import io
import tempfile
import unittest
from pathlib import Path

from oskg.budget import Budget, Ledger
from oskg.phases import PHASE_CLASSES
from oskg.pipeline import Logger, PipelineContext
from oskg.runner import FakeRunner
from oskg.state import RunState

from .fixtures import SOURCE_GUIDE, make_project


def context_for(root, manifest) -> PipelineContext:
    ledger = Ledger(Path(root) / ".oskg" / "ledger.jsonl")
    return PipelineContext(
        project_dir=Path(root),
        manifest=manifest,
        state=RunState.load(root),
        budget=Budget.from_manifest(manifest, ledger),
        runner=FakeRunner(),
        log=Logger(stream=io.StringIO(), use_colour=False),
        git_enabled=False,
    )


def wide_source_guide(count: int) -> str:
    """A guide with `count` acquired sources spread across tiers 1-3."""
    rows = []
    for i in range(count):
        tier = 1 if i < 2 else (2 if i < count - 3 else 3)
        rows.append((f"s{i}", tier))
    out = ["---", "tags: [type/meta]", "---", "", "# Source Guide", ""]
    for tier in (1, 2, 3):
        out += [
            f"## Tier {tier} — group",
            "",
            "| slug | title | author | year | tier | role | status |",
            "|---|---|---|---|---|---|---|",
        ]
        out += [
            f"| {slug} | Title {slug} | Author | 2020 | {t} | role | acquired |"
            for slug, t in rows
            if t == tier
        ]
        out.append("")
    return "\n".join(out)


class TestColdRunDoesNotTrim(unittest.TestCase):
    """With no measurements, plan the whole corpus and let the loop stop."""

    def setUp(self):
        self.root, self.manifest = make_project(tempfile.mkdtemp(), budget=4.0)
        (self.root / "SOURCE-GUIDE.md").write_text(wide_source_guide(12), encoding="utf-8")
        self.ctx = context_for(self.root, self.manifest)

    def test_phase_one_plans_every_acquired_source(self):
        planned = PHASE_CLASSES[1](self.ctx).plan()
        self.assertEqual(len(planned), 12)
        self.assertEqual(self.ctx.state.trims, [])

    def test_no_trim_is_recorded_before_anything_is_measured(self):
        PHASE_CLASSES[1](self.ctx).plan()
        self.assertEqual(RunState.load(self.root).trims, [])

    def test_the_manifest_min_tier_is_untouched(self):
        PHASE_CLASSES[1](self.ctx).plan()
        self.assertEqual(self.manifest.min_tier, 1)


class TestWarmRunTrimsOnMeasurement(unittest.TestCase):
    """Once cost is known, trimming is grounded and Tiers 1-2 are protected."""

    def setUp(self):
        self.root, self.manifest = make_project(tempfile.mkdtemp(), budget=20.0)
        (self.root / "SOURCE-GUIDE.md").write_text(wide_source_guide(12), encoding="utf-8")
        self.ctx = context_for(self.root, self.manifest)

    def _observe(self, stage: str, cost: float, times: int = 3) -> None:
        for i in range(times):
            self.ctx.budget.record(phase=1, stage=stage, label=f"m{i}", cost_usd=cost)

    def test_an_expensive_measurement_trims_the_corpus(self):
        self._observe("notes", 1.00)
        planned = PHASE_CLASSES[1](self.ctx).plan()
        self.assertLess(len(planned), 12)
        self.assertTrue(RunState.load(self.root).trims)

    def test_tier_one_survives_the_trim(self):
        self._observe("notes", 1.00)
        planned = PHASE_CLASSES[1](self.ctx).plan()
        self.assertIn("read:s0", planned)
        self.assertIn("read:s1", planned)

    def test_a_cheap_measurement_keeps_the_whole_corpus(self):
        # The live measurement was $0.047; nothing should be dropped at that price.
        self._observe("notes", 0.047)
        self.assertEqual(len(PHASE_CLASSES[1](self.ctx).plan()), 12)
        self.assertEqual(RunState.load(self.root).trims, [])

    def test_the_trim_is_recorded_with_what_it_dropped(self):
        self._observe("notes", 1.00)
        PHASE_CLASSES[1](self.ctx).plan()
        trim = RunState.load(self.root).trims[0]
        self.assertEqual(trim["phase"], 1)
        self.assertTrue(trim["dropped"])
        self.assertIn("Tier", trim["detail"])


class TestObservationTracking(unittest.TestCase):
    def test_has_observations_is_false_until_a_call_is_priced(self):
        root, manifest = make_project(tempfile.mkdtemp())
        budget = context_for(root, manifest).budget
        self.assertFalse(budget.has_observations("notes"))
        budget.record(phase=1, stage="notes", label="a", cost_usd=0.05)
        self.assertTrue(budget.has_observations("notes"))

    def test_a_failed_call_is_not_a_measurement(self):
        # It cost money, but it says nothing about what the work costs.
        root, manifest = make_project(tempfile.mkdtemp())
        budget = context_for(root, manifest).budget
        budget.record(phase=1, stage="notes", label="a", cost_usd=0.05, ok=False)
        self.assertFalse(budget.has_observations("notes"))

    def test_observations_survive_a_resume(self):
        root, manifest = make_project(tempfile.mkdtemp())
        context_for(root, manifest).budget.record(
            phase=1, stage="notes", label="a", cost_usd=0.05
        )
        self.assertTrue(context_for(root, manifest).budget.has_observations("notes"))


if __name__ == "__main__":
    unittest.main()
