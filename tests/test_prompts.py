"""Every prompt template must render.

A `KeyError` or a stray unescaped brace in a template only surfaces at the
moment a phase tries to build its prompt — which, on a real run, is after money
has already been spent getting there. Rendering all of them here costs
milliseconds.
"""

import io
import tempfile
import unittest
from pathlib import Path

from oskg.pipeline import Logger, PipelineContext
from oskg.budget import Budget, Ledger
from oskg.phases import PHASE_CLASSES
from oskg.phases.base import PROMPT_DIR, markdown_table
from oskg.state import RunState

from .fixtures import make_graph_project, make_note


# Placeholders `str.format` would have substituted. A literal `{domain}` in a
# prompt is intentional instruction to the agent; a leftover `{claim_types}` is
# a bug that only surfaces after money has been spent reaching that phase.
_FIELD_NAMES = {
    "project", "topic", "question", "project_dir", "methodology_dir", "phase", "phase_name",
    "tag", "slug_prefix", "topics", "claim_types", "evidence_types", "edge_types",
    "note_domains", "confidence_levels", "claims_min", "claims_max", "spec_refs",
    "source_table", "note_list", "existing_claims", "claim_table", "cluster_name",
    "analysis_payload", "analysis_name", "output_file", "output_structure", "metrics_block",
    "failures", "target_edges", "max_notes", "max_sources", "target_sources", "target_notes",
}


def unfilled_placeholders(text: str) -> set[str]:
    import re

    return {m for m in re.findall(r"\{(\w+)\}", text)} & _FIELD_NAMES


def context_for(root: Path, manifest) -> PipelineContext:
    ledger = Ledger(root / ".oskg" / "ledger.jsonl")
    return PipelineContext(
        project_dir=root,
        manifest=manifest,
        state=RunState.load(root),
        budget=Budget.from_manifest(manifest, ledger),
        runner=None,
        log=Logger(stream=io.StringIO(), use_colour=False),
    )


class TestTemplateRendering(unittest.TestCase):
    def setUp(self):
        self.root, self.manifest = make_graph_project(tempfile.mkdtemp())
        make_note(self.root, "Note One", source="s1", tier=1)
        self.ctx = context_for(self.root, self.manifest)

    def _driver(self, phase: int):
        driver = PHASE_CLASSES[phase](self.ctx)
        driver.plan()  # populates any per-phase state build_prompt needs
        return driver

    def test_every_phase_renders_its_prompt(self):
        batches = {
            0: ["scope"],
            1: ["read:s1"],
            2: ["notes/concepts/Note One.md"],
            3: ["alpha"],
            4: ["hinges"],
            5: ["capstone"],
        }
        for phase, batch in batches.items():
            with self.subTest(phase=phase):
                prompt = self._driver(phase).build_prompt(batch)
                self.assertGreater(len(prompt), 400)
                self.assertEqual(unfilled_placeholders(prompt), set())

    def test_phase_zero_acquisition_prompt_renders(self):
        driver = self._driver(0)
        self.assertIn("acquire", driver.build_prompt(["acquire:s1", "acquire:s2"]).lower())

    def test_repair_prompt_renders_with_real_failures(self):
        from oskg.gates import run_gate

        root, manifest = make_graph_project(tempfile.mkdtemp(), broken=True)
        driver = PHASE_CLASSES[2](context_for(root, manifest))
        prompt = driver._repair_prompt(run_gate(root, 2, manifest))
        self.assertIn("BROKEN_LINK", prompt)
        self.assertIn("filename slug", prompt)

    def test_preamble_carries_the_unattended_rules(self):
        prompt = self._driver(2).build_prompt(["notes/concepts/Note One.md"])
        self.assertIn("unattended", prompt)
        self.assertIn("there is no user", prompt.lower())
        self.assertIn("Never commit or push", prompt)

    def test_claims_prompt_repeats_the_slug_rule(self):
        # The failure that silently destroys graphs. It is stated three times
        # in the prompt on purpose.
        prompt = self._driver(2).build_prompt(["notes/concepts/Note One.md"])
        self.assertGreaterEqual(prompt.lower().count("claim_id"), 2)
        self.assertIn("verify every wikilink", prompt.lower())

    def test_synthesis_prompt_embeds_the_computed_analysis(self):
        prompt = self._driver(4).build_prompt(["hinges"])
        self.assertIn("The analysis is already done", prompt)
        self.assertIn('"hinges"', prompt)

    def test_specs_are_referenced_by_path(self):
        prompt = self._driver(2).build_prompt(["notes/concepts/Note One.md"])
        self.assertIn("spec/claim-node.md", prompt)


class TestTemplateFiles(unittest.TestCase):
    def test_every_template_is_read_as_utf8(self):
        for path in sorted(PROMPT_DIR.glob("*.md")):
            with self.subTest(template=path.name):
                self.assertGreater(len(path.read_text(encoding="utf-8")), 100)

    def test_no_template_is_orphaned(self):
        """Every prompt file is referenced from a driver or the base class."""
        source = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (PROMPT_DIR.parent / "phases").glob("*.py")
        )
        source += (PROMPT_DIR.parent / "phases" / "base.py").read_text(encoding="utf-8")
        for path in sorted(PROMPT_DIR.glob("*.md")):
            if path.name.startswith("_"):
                continue
            with self.subTest(template=path.name):
                self.assertIn(path.name, source)


class TestHelpers(unittest.TestCase):
    def test_markdown_table_escapes_pipes(self):
        table = markdown_table([{"a": "x|y"}], ("a",))
        self.assertIn(r"x\|y", table)

    def test_markdown_table_truncates_and_says_so(self):
        table = markdown_table([{"a": i} for i in range(100)], ("a",), limit=5)
        self.assertIn("95 more", table)

    def test_empty_table(self):
        self.assertEqual(markdown_table([], ("a",)), "_(none)_")


if __name__ == "__main__":
    unittest.main()
