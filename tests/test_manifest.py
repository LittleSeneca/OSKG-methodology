"""The manifest — what makes the pipeline domain-agnostic."""

import tempfile
import unittest
from pathlib import Path

from oskg.manifest import (
    BASE_EDGE_TYPES,
    DEFAULT_ALLOCATION,
    Manifest,
    ManifestError,
    default_manifest,
)


def base(**overrides) -> Manifest:
    m = default_manifest(project="OSKG-Test", topic="a subject", slug="test")
    for key, value in overrides.items():
        m.data[key] = value
    return m


class TestDefaults(unittest.TestCase):
    def test_default_manifest_is_valid(self):
        self.assertEqual(default_manifest(project="P", topic="t", slug="s").validate(), [])

    def test_allocation_sums_to_one(self):
        self.assertAlmostEqual(sum(DEFAULT_ALLOCATION.values()), 1.0, places=6)

    def test_covers_every_phase(self):
        self.assertEqual(set(DEFAULT_ALLOCATION), {f"phase{n}" for n in range(6)})

    def test_base_edge_types_are_always_present(self):
        self.assertTrue(set(BASE_EDGE_TYPES) <= set(base().edge_types))


class TestValidation(unittest.TestCase):
    def _problem_codes(self, manifest: Manifest) -> set[str]:
        return {p.split(":")[0] for p in manifest.validate()}

    def test_unsupported_version(self):
        self.assertIn("UNSUPPORTED_VERSION", self._problem_codes(base(oskg_version=99)))

    def test_missing_required_key(self):
        self.assertIn("MISSING_KEY", self._problem_codes(base(project="")))

    def test_edge_types_must_include_the_base_four(self):
        # Analysis assumes they exist; depends_on drives hinges and cascades.
        self.assertIn("INCOMPLETE_EDGE_TYPES", self._problem_codes(base(edge_types=["supports"])))

    def test_allocation_must_sum_to_one(self):
        m = base()
        m.data["budget"]["allocation"]["phase0"] = 0.5
        self.assertIn("BAD_ALLOCATION", self._problem_codes(m))

    def test_every_phase_needs_an_allocation(self):
        m = base()
        del m.data["budget"]["allocation"]["phase3"]
        self.assertIn("MISSING_PHASE_ALLOCATION", self._problem_codes(m))

    def test_reserve_must_be_less_than_total(self):
        m = base()
        m.data["budget"]["reserve_usd"] = 25.0
        self.assertIn("BAD_BUDGET", self._problem_codes(m))

    def test_provider_without_model_is_rejected(self):
        # hermes rejects --provider without --model; catching it here fails at
        # manifest load rather than confusingly at request time.
        m = base()
        m.data["model"] = {"default": None, "provider": "deepseek"}
        self.assertIn("PROVIDER_WITHOUT_MODEL", self._problem_codes(m))

    def test_reserved_note_domains_are_rejected(self):
        self.assertIn("BAD_NOTE_DOMAINS", self._problem_codes(base(note_domains=["claims", "history"])))

    def test_bad_tag_shape(self):
        self.assertIn("BAD_TAG", self._problem_codes(base(tag="OSKG Test")))

    def test_inverted_claims_range(self):
        m = base()
        m.data["scope"]["claims_per_note"] = [10, 5]
        self.assertIn("BAD_RANGE", self._problem_codes(m))

    def test_min_tier_out_of_range(self):
        m = base()
        m.data["scope"]["min_tier"] = 9
        self.assertIn("BAD_RANGE", self._problem_codes(m))


class TestPersistence(unittest.TestCase):
    def test_round_trip_preserves_everything(self):
        root = Path(tempfile.mkdtemp())
        original = base(topic="a topic: with punctuation, and commas")
        original.data["scope"]["claims_per_note"] = [4, 9]
        original.save(root)
        reloaded = Manifest.load(root)
        self.assertEqual(reloaded.data, original.data)
        self.assertEqual(reloaded.claims_per_note, (4, 9))

    def test_load_refuses_an_invalid_manifest_by_default(self):
        root = Path(tempfile.mkdtemp())
        m = base(tag="Not A Tag")
        m.save(root)
        with self.assertRaises(ManifestError):
            Manifest.load(root)
        # ...but can be loaded for inspection, which is how `oskg validate`
        # reports what is wrong instead of just refusing to start.
        self.assertTrue(Manifest.load(root, validate=False).validate())

    def test_missing_file(self):
        with self.assertRaises(ManifestError):
            Manifest.load(Path(tempfile.mkdtemp()))


class TestAccessors(unittest.TestCase):
    def test_question_falls_back_to_topic(self):
        m = base(question="")
        self.assertEqual(m.question, m.topic)

    def test_per_phase_model_override(self):
        m = base()
        m.data["model"] = {"default": "small", "provider": "p", "per_phase": {"phase5": "big"}}
        self.assertEqual(m.model_for_phase(2), ("small", "p"))
        self.assertEqual(m.model_for_phase(5), ("big", "p"))

    def test_gate_thresholds_merge_over_defaults(self):
        m = base(gates={"min_edges_per_claim": 3.0})
        self.assertEqual(m.gates["min_edges_per_claim"], 3.0)
        self.assertIn("max_orphan_ratio", m.gates)  # default still present


if __name__ == "__main__":
    unittest.main()
