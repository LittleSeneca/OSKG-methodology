"""The CLI surface, plus the projection and PROGRESS.md rendering.

No command here spends anything: `build` is only exercised via `--dry-run`, and
everything else is read-only over a fixture project.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from oskg.budget import Budget, Ledger
from oskg.cli import EXIT_FATAL, EXIT_NOPROJECT, EXIT_OK, main
from oskg.progress import render as render_progress
from oskg.projection import format_projection, project_run
from oskg.state import DONE, RunState

from .fixtures import make_graph_project, make_project


def run_cli(*argv) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = main(list(argv))
    return code, out.getvalue()


class TestReadOnlyCommands(unittest.TestCase):
    def setUp(self):
        self.root, self.manifest = make_graph_project(tempfile.mkdtemp())

    def test_validate_accepts_a_good_manifest(self):
        code, out = run_cli("validate", str(self.root))
        self.assertEqual(code, EXIT_OK)
        self.assertIn("valid", out)

    def test_validate_reports_problems_and_exits_nonzero(self):
        self.manifest.data["tag"] = "Not A Tag"
        self.manifest.save(self.root)
        code, out = run_cli("validate", str(self.root))
        self.assertEqual(code, EXIT_FATAL)
        self.assertIn("BAD_TAG", out)

    def test_analyze_prints_a_summary_and_writes_the_analysis(self):
        code, out = run_cli("analyze", str(self.root))
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Top hinges", out)
        self.assertTrue((self.root / ".oskg" / "analysis.json").exists())

    def test_analyze_json(self):
        code, out = run_cli("analyze", str(self.root), "--json")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("hinges", json.loads(out))

    def test_status(self):
        code, out = run_cli("status", str(self.root))
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Budget", out)
        self.assertIn("Capstone", out)

    def test_gate_json_is_machine_readable(self):
        code, out = run_cli("gate", str(self.root), "--phase", "2", "--json")
        payload = json.loads(out)
        self.assertEqual(payload[0]["phase"], 2)
        self.assertIn("findings", payload[0])

    def test_gate_exit_code_reflects_severity(self):
        broken, _ = make_graph_project(tempfile.mkdtemp(), broken=True)
        clean_code, _ = run_cli("gate", str(self.root), "--phase", "2")
        broken_code, _ = run_cli("gate", str(broken), "--phase", "2")
        self.assertEqual(clean_code, EXIT_OK)
        self.assertNotEqual(broken_code, EXIT_OK)

    def test_export_json(self):
        code, out = run_cli("export", str(self.root), "--format", "json")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("claims", json.loads(out))

    def test_export_dot(self):
        code, out = run_cli("export", str(self.root), "--format", "dot")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("digraph", out)
        self.assertIn("->", out)

    def test_export_to_a_file(self):
        target = Path(tempfile.mkdtemp()) / "graph.json"
        code, _ = run_cli("export", str(self.root), "-o", str(target))
        self.assertEqual(code, EXIT_OK)
        self.assertIn("claims", json.loads(target.read_text(encoding="utf-8")))


class TestProjectDiscovery(unittest.TestCase):
    def test_finds_the_project_from_a_subdirectory(self):
        root, _ = make_graph_project(tempfile.mkdtemp())
        code, _ = run_cli("status", str(root / "notes" / "claims"))
        self.assertEqual(code, EXIT_OK)

    def test_no_project_exits_cleanly_with_advice(self):
        code, out = run_cli("status", tempfile.mkdtemp())
        self.assertEqual(code, EXIT_NOPROJECT)
        self.assertIn("oskg build", out)


class TestDryRun(unittest.TestCase):
    def test_dry_run_spends_nothing_and_prints_a_projection(self):
        parent = tempfile.mkdtemp()
        code, out = run_cli(
            "build", "the Late Bronze Age collapse", "--parent", parent,
            "--budget", "20", "--dry-run", "--no-git",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Projected for a $20.00 budget", out)
        project = Path(parent) / "OSKG-LateBronzeAge"
        self.assertTrue((project / "oskg.yaml").exists())
        # A dry run writes no ledger entries.
        self.assertFalse((project / ".oskg" / "ledger.jsonl").exists())

    def test_scaffold_command(self):
        parent = tempfile.mkdtemp()
        code, out = run_cli("scaffold", "a scaffolded subject", "--parent", parent)
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Created", out)


class TestProjection(unittest.TestCase):
    def _projection(self, budget_usd: float):
        root, manifest = make_project(tempfile.mkdtemp(), budget=budget_usd)
        ledger = Ledger(root / ".oskg" / "ledger.jsonl")
        return project_run(manifest, Budget.from_manifest(manifest, ledger))

    def test_projection_chains_phases(self):
        # Phase 1 cannot read more sources than Phase 0 acquired. Reporting each
        # allowance in isolation would promise a corpus that does not exist.
        p = self._projection(20.0)
        notes_from_sources = p["sources"] * 3
        self.assertLessEqual(p["notes"], notes_from_sources)
        self.assertLessEqual(p["notes_extracted"], p["notes"])

    def test_a_bigger_budget_projects_a_bigger_graph(self):
        small, large = self._projection(10.0), self._projection(50.0)
        self.assertGreater(large["claims"][1], small["claims"][1])

    def test_projection_carries_the_estimate_caveat(self):
        self.assertIn("Seed estimates", format_projection(self._projection(20.0)))

    def test_a_starved_phase_zero_is_named_as_the_bottleneck(self):
        # With a tiny budget Phase 0 cannot acquire as many sources as Phase 1
        # could read, and saying so is more useful than any phase's allowance.
        root, manifest = make_project(tempfile.mkdtemp(), budget=3.0)
        manifest.data["budget"]["allocation"] = {
            "phase0": 0.02, "phase1": 0.40, "phase2": 0.30,
            "phase3": 0.16, "phase4": 0.07, "phase5": 0.05,
        }
        ledger = Ledger(root / ".oskg" / "ledger.jsonl")
        projection = project_run(manifest, Budget.from_manifest(manifest, ledger))
        self.assertIsNotNone(projection["bottleneck"])
        self.assertIn("Bottleneck", format_projection(projection))

    def test_every_phase_appears(self):
        self.assertEqual([p.phase for p in self._projection(20.0)["phases"]], list(range(6)))


class TestProgressRendering(unittest.TestCase):
    def _render(self, state: RunState) -> str:
        root, manifest = make_project(tempfile.mkdtemp())
        ledger = Ledger(root / ".oskg" / "ledger.jsonl")
        return render_progress(manifest, state, Budget.from_manifest(manifest, ledger))

    def test_no_trims_says_so(self):
        text = self._render(RunState.load(Path(tempfile.mkdtemp())))
        self.assertIn("the full planned scope was covered", text)

    def test_trims_are_the_headline(self):
        # A graph that silently covered less than it claimed is worse than a
        # small graph that says so.
        state = RunState.load(Path(tempfile.mkdtemp()))
        state.record_trim(1, "tier", "dropped Tier 4 (5 sources)", dropped=["s7", "s8"])
        text = self._render(state)
        self.assertIn("This is what the graph does not cover", text)
        self.assertIn("dropped Tier 4", text)
        self.assertIn("`s7`", text)

    def test_every_phase_has_a_row(self):
        text = self._render(RunState.load(Path(tempfile.mkdtemp())))
        for name in ("Scoping and acquisition", "Claims extraction", "Capstone"):
            self.assertIn(name, text)

    def test_phase_status_is_shown(self):
        state = RunState.load(Path(tempfile.mkdtemp()))
        state.finish_phase(0, DONE)
        self.assertIn("done", self._render(state))


if __name__ == "__main__":
    unittest.main()
