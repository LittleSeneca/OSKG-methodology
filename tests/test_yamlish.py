"""The YAML subset — the module everything else parses through."""

import unittest

from oskg import yamlish


class TestParsing(unittest.TestCase):
    def test_scalars(self):
        d = yamlish.loads(
            "s: hello\n"
            'q: "quoted: colon"\n'
            "i: 42\n"
            "f: 1.5\n"
            "t: true\n"
            "f2: no\n"
            "n: null\n"
            "empty:\n"
        )
        self.assertEqual(d["s"], "hello")
        self.assertEqual(d["q"], "quoted: colon")
        self.assertEqual(d["i"], 42)
        self.assertEqual(d["f"], 1.5)
        self.assertIs(d["t"], True)
        self.assertIs(d["f2"], False)
        self.assertIsNone(d["n"])
        self.assertIsNone(d["empty"])

    def test_dates_stay_strings(self):
        # Every consumer wants the ISO text it was written with; a date object
        # would round-trip through the emitter and rewrite an untouched file.
        self.assertEqual(yamlish.loads("created: 2026-08-12")["created"], "2026-08-12")

    def test_block_list(self):
        d = yamlish.loads("tags:\n  - type/claim\n  - oskg-test\nother: x\n")
        self.assertEqual(d["tags"], ["type/claim", "oskg-test"])
        self.assertEqual(d["other"], "x")

    def test_nested_mappings(self):
        d = yamlish.loads(
            "budget:\n"
            "  total_usd: 20.0\n"
            "  allocation:\n"
            "    phase0: 0.12\n"
            "    phase1: 0.3\n"
            "  rollover: true\n"
        )
        self.assertEqual(d["budget"]["allocation"], {"phase0": 0.12, "phase1": 0.3})
        self.assertIs(d["budget"]["rollover"], True)

    def test_inline_collections(self):
        d = yamlish.loads("r: [5, 10]\nempty_list: []\nm: {a: 1, b: two}\nempty_map: {}\n")
        self.assertEqual(d["r"], [5, 10])
        self.assertEqual(d["empty_list"], [])
        self.assertEqual(d["m"], {"a": 1, "b": "two"})
        self.assertEqual(d["empty_map"], {})

    def test_comments_respect_quotes(self):
        d = yamlish.loads('url: "http://x#y"   # a trailing comment\n# whole line\nk: v # tail\n')
        self.assertEqual(d["url"], "http://x#y")
        self.assertEqual(d["k"], "v")

    def test_document_markers_are_skipped(self):
        self.assertEqual(yamlish.loads("---\na: 1\n"), {"a": 1})

    def test_empty_input(self):
        self.assertEqual(yamlish.loads(""), {})
        self.assertEqual(yamlish.loads("# just a comment\n"), {})


class TestRejections(unittest.TestCase):
    """Unsupported YAML must fail loudly, never parse to something plausible."""

    def _reject(self, text: str):
        with self.assertRaises(yamlish.YamlishError):
            yamlish.loads(text)

    def test_anchor_in_value_position(self):
        self._reject("a: &anchor 1")

    def test_alias(self):
        self._reject("a: *ref")

    def test_anchor_in_list(self):
        self._reject("items:\n  - &x 1")

    def test_block_scalar(self):
        self._reject("a: |\n  some text")
        self._reject("a: >\n  folded")

    def test_list_of_mappings(self):
        self._reject("sources:\n  - slug: a\n    title: b")

    def test_multiple_documents(self):
        self._reject("a: 1\n---\nb: 2")

    def test_merge_key(self):
        self._reject("<<: *base")

    def test_tab_indentation(self):
        self._reject("a:\n\t- 1")

    def test_nested_inline_collection(self):
        self._reject("a: [1, [2, 3]]")

    def test_error_names_the_line(self):
        with self.assertRaises(yamlish.YamlishError) as ctx:
            yamlish.loads("ok: 1\nbad: |\n  block")
        self.assertIn("line 2", str(ctx.exception))


class TestEmitting(unittest.TestCase):
    def test_round_trip(self):
        original = {
            "oskg_version": 1,
            "project": "OSKG-Test",
            "topic": "a topic: with a colon",
            "tags": ["type/claim", "oskg-test"],
            "budget": {"total_usd": 20.0, "allocation": {"phase0": 0.12}, "rollover": True},
            "empty_list": [],
            "empty_map": {},
            "nothing": None,
        }
        self.assertEqual(yamlish.loads(yamlish.dumps(original)), original)

    def test_ambiguous_strings_are_quoted(self):
        # Without quoting these would read back as bool / None / int.
        for value in ("yes", "no", "true", "null", "~", "42", "1.5", ""):
            with self.subTest(value=value):
                out = yamlish.loads(yamlish.dumps({"k": value}))
                self.assertEqual(out["k"], value)

    def test_strings_with_specials_survive(self):
        for value in ("a: b", "- leading dash", "#hash", "trailing ", 'has "quotes"'):
            with self.subTest(value=value):
                self.assertEqual(yamlish.loads(yamlish.dumps({"k": value}))["k"], value)

    def test_refuses_lists_of_collections(self):
        with self.assertRaises(yamlish.YamlishError):
            yamlish.dumps({"a": [{"b": 1}]})


if __name__ == "__main__":
    unittest.main()
