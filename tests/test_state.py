"""Run state — what survives a process being killed at 3am."""

import json
import tempfile
import unittest
from pathlib import Path

from oskg.frontmatter import parse, read, write
from oskg.state import DONE, FAILED, PENDING, SKIPPED, RunState


class TestPersistence(unittest.TestCase):
    def test_round_trip(self):
        root = Path(tempfile.mkdtemp())
        state = RunState.load(root)
        state.project = "OSKG-Test"
        state.phase(1).enqueue(["a", "b"])
        state.phase(1).mark("a", DONE)
        state.record_trim(1, "tier", "dropped Tier 4", dropped=["s9"])
        state.save()

        reloaded = RunState.load(root)
        self.assertEqual(reloaded.project, "OSKG-Test")
        self.assertEqual(reloaded.phase(1).items, {"a": DONE, "b": PENDING})
        self.assertEqual(len(reloaded.trims), 1)

    def test_a_corrupt_state_file_does_not_strand_the_project(self):
        # The ledger is append-only and still has the spend; starting fresh
        # re-derives phase status from what is on disk.
        root = Path(tempfile.mkdtemp())
        path = root / ".oskg" / "state.json"
        path.parent.mkdir(parents=True)
        path.write_text("{ not json", encoding="utf-8")
        self.assertEqual(RunState.load(root).current_phase, 0)

    def test_save_is_atomic(self):
        root = Path(tempfile.mkdtemp())
        state = RunState.load(root)
        state.save()
        self.assertTrue(state.path.exists())
        self.assertFalse(state.path.with_suffix(".json.tmp").exists())
        json.loads(state.path.read_text(encoding="utf-8"))  # valid, not half-written


class TestWorkQueue(unittest.TestCase):
    def test_enqueue_never_resets_finished_work(self):
        # Re-planning a phase must not un-complete what it already did.
        state = RunState.load(Path(tempfile.mkdtemp()))
        ps = state.phase(2)
        ps.enqueue(["a"])
        ps.mark("a", DONE)
        ps.enqueue(["a", "b"])
        self.assertEqual(ps.items, {"a": DONE, "b": PENDING})

    def test_a_fresh_run_retries_failed_and_skipped(self):
        state = RunState.load(Path(tempfile.mkdtemp()))
        state.phase(1).items = {"f": FAILED, "s": SKIPPED, "d": DONE}
        state.start_phase(1)
        self.assertEqual(state.phase(1).items, {"f": PENDING, "s": PENDING, "d": DONE})

    def test_next_phase_finds_the_first_incomplete(self):
        state = RunState.load(Path(tempfile.mkdtemp()))
        state.finish_phase(0, DONE)
        state.finish_phase(1, DONE)
        self.assertEqual(state.next_phase(), 2)

    def test_next_phase_is_none_when_finished(self):
        state = RunState.load(Path(tempfile.mkdtemp()))
        for n in range(6):
            state.finish_phase(n, DONE)
        self.assertIsNone(state.next_phase())

    def test_reset_phase_forgets_everything(self):
        state = RunState.load(Path(tempfile.mkdtemp()))
        state.phase(3).enqueue(["a"])
        state.finish_phase(3, DONE)
        state.reset_phase(3)
        self.assertEqual(state.phase(3).status, PENDING)
        self.assertEqual(state.phase(3).items, {})


class TestFrontmatter(unittest.TestCase):
    def test_parses_meta_and_body(self):
        doc = parse("---\ntags:\n  - type/claim\nkey: value\n---\n\n# Title\n\nBody.\n")
        self.assertEqual(doc.meta["key"], "value")
        self.assertEqual(doc.tags, ["type/claim"])
        self.assertIn("# Title", doc.body)

    def test_missing_frontmatter_is_reported_not_raised(self):
        # One malformed claim in a batch of 400 is one gate failure, not an
        # aborted run.
        doc = parse("# Just a heading\n")
        self.assertEqual(doc.error, "NO_FRONTMATTER")

    def test_broken_yaml_is_reported_not_raised(self):
        doc = parse("---\na: |\n  block\n---\n\nbody\n")
        self.assertTrue(doc.error.startswith("YAML_PARSE_ERROR"))

    def test_sections_stop_at_the_next_same_level_heading(self):
        doc = parse(
            "---\nk: v\n---\n\n## Evidence\n\nfirst\n\n### Sub\n\nnested\n\n## Edges\n\nsecond\n"
        )
        sections = doc.sections()
        self.assertIn("nested", sections["Evidence"])
        self.assertNotIn("second", sections["Evidence"])
        self.assertIn("second", sections["Edges"])

    def test_section_lookup_is_case_insensitive_with_fallbacks(self):
        doc = parse("---\nk: v\n---\n\n## Claims\n\nbody\n")
        self.assertEqual(doc.section("Candidate Claims", "claims"), "body")
        self.assertEqual(doc.section("Nothing Here"), "")

    def test_write_then_read_round_trips(self):
        path = Path(tempfile.mkdtemp()) / "note.md"
        write(path, {"tags": ["type/note"], "title": "A: colon"}, "# Heading\n\nBody.\n")
        doc = read(path)
        self.assertEqual(doc.meta["title"], "A: colon")
        self.assertEqual(doc.tags, ["type/note"])

    def test_missing_file_is_reported_not_raised(self):
        self.assertTrue(read(Path("/nonexistent/x.md")).error.startswith("READ_ERROR"))

    def test_tag_helpers(self):
        doc = parse("---\ntags:\n  - type/claim\n  - source/nist\n  - topic/a\n  - topic/b\n---\n\nx\n")
        self.assertEqual(doc.tag_after("source/"), "nist")
        self.assertEqual(doc.tags_with_prefix("topic/"), ["topic/a", "topic/b"])
        self.assertIsNone(doc.tag_after("nothing/"))


if __name__ == "__main__":
    unittest.main()
