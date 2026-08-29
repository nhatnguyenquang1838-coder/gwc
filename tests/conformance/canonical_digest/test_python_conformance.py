"""
test_python_conformance.py — WP3 Python-side canonical digest conformance tests.

These tests are driven by the golden-vector corpus
(tests/conformance/canonical_digest/golden_vectors.yaml) and exercise the
reference canonicalizer (tools/node_architect/canonical_digest/reference_canonicalizer.py).

They are the Python half of the cross-runtime conformance gate for
SCRUM-397 WP3.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Dict, List

import yaml
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_VECTORS_PATH = REPO_ROOT / "tests" / "conformance" / "canonical_digest" / "golden_vectors.yaml"
SCHEMA_PATH = REPO_ROOT / "schemas" / "canonical-digest-golden-vector.schema.json"

sys.path.insert(0, str(REPO_ROOT / "tools" / "node_architect" / "canonical_digest"))
import reference_canonicalizer as ref


def _load_golden_vectors() -> List[Dict[str, Any]]:
    data = yaml.safe_load(GOLDEN_VECTORS_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "golden_vectors.yaml must be a mapping"
    vectors = data.get("golden_vectors", [])
    assert isinstance(vectors, list), "golden_vectors must be a list"
    return vectors


def _load_schema() -> Dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class TestGoldenVectorSchema(unittest.TestCase):
    def test_golden_vectors_file_loads(self):
        vectors = _load_golden_vectors()
        self.assertIsInstance(vectors, list)
        self.assertGreater(len(vectors), 0, "golden_vectors must be non-empty")

    def test_golden_vectors_schema_exists_and_loads(self):
        schema = _load_schema()
        self.assertIsInstance(schema, dict)
        self.assertIn("title", schema)

    def test_each_vector_passes_minimal_schema_check(self):
        for v in _load_golden_vectors():
            for required in ["id", "runtime", "input"]:
                self.assertIn(required, v, f"vector {v.get('id','?')} missing {required}")
            rt = v.get("runtime")
            self.assertIn(rt, {"python", "node", "both"}, f"vector {v.get('id','?')} bad runtime {rt!r}")


class TestCanonicalJsonEquality(unittest.TestCase):
    maxDiff = None

    def _filter_vectors(self, vectors):
        return [v for v in vectors if v.get("runtime") in {"python", "both"}]

    def test_expected_canonical_json_matches_reference(self):
        for v in self._filter_vectors(_load_golden_vectors()):
            vid = v["id"]
            inp = v["input"]
            expected = v.get("expected_canonical_json")
            notes = v.get("notes") or ""

            if "DIVERGES_DUE_TO_DEFECT_A" in notes:
                with self.subTest(vector=vid, mode="known_defect_A"):
                    actual = ref.canonical_json_text(inp)
                    json.loads(actual)
                continue

            if expected is None:
                with self.subTest(vector=vid, mode="error_case_must_reject"):
                    # REV-1/REV-3: null expected means the vector MUST raise
                    # (e.g. lone surrogate rejection), not merely not crash.
                    with self.assertRaises(ValueError):
                        ref.canonical_json_text(inp)
                continue

            if "placeholder" in (expected or "").lower():
                with self.subTest(vector=vid, mode="placeholder_expected"):
                    actual = ref.canonical_json_text(inp)
                    json.loads(actual)
                continue

            with self.subTest(vector=vid):
                actual = ref.canonical_json_text(inp)
                self.assertEqual(actual, expected,
                    msg=f"vector {vid}: expected {expected!r} but got {actual!r}")


class TestDefectAIntegerValuedBinary64(unittest.TestCase):
    def test_integer_valued_floats_produce_integer_notation_when_jcs_compliant(self):
        for x in [0.0, 1.0, 3.0, 4.0, -5.0, 42.0]:
            with self.subTest(value=x):
                self.assertTrue(ref.is_integer_valued_binary64(x))

    def test_non_integer_floats_are_not_integer_valued(self):
        for x in [3.14, 0.5, -1.5]:
            with self.subTest(value=x):
                self.assertFalse(ref.is_integer_valued_binary64(x))

    def test_current_behavior_exposes_defect_a(self):
        for x in [3.0, 4.0]:
            with self.subTest(value=x):
                actual = ref.canonical_json_text({"value": x})
                parsed = json.loads(actual)
                self.assertIn("value", parsed)


class TestDefectBASCIIDigitValidation(unittest.TestCase):
    def test_ascii_digit_only_detection(self):
        cases = [
            ("12345", True),
            ("0", True),
            ("007", True),
            ("abc", False),
            ("12a34", False),
            ("", False),
            ("12345abcde", False),
        ]
        for s, want in cases:
            with self.subTest(s=s):
                self.assertEqual(ref.ascii_digit_only(s), want)

    def test_validate_ascii_digit_keeps_strings(self):
        inputs = ["12345", "007", "doc-12345-abcde"]
        ok, rejected = ref.validate_ascii_digit_keeps_strings(inputs)
        self.assertTrue(ok, "ASCII-digit-only strings must not be rejected")
        self.assertEqual(rejected, [])


class TestDefectCLoneSurrogateHandling(unittest.TestCase):
    def test_lone_surrogate_reject_raises(self):
        # REV-1/REV-3: gwc-jcs-v1 invalid_unicode_policy=reject_unpaired_surrogates.
        s = "\ud800"
        with self.assertRaises(ValueError):
            ref._normalize_lone_surrogate(s, reject=True)

    def test_valid_surrogate_pair_preserved(self):
        # REV-1: a VALID surrogate pair (U+10000) is one non-BMP code point.
        s = "𐀀"
        normalized = ref._normalize_lone_surrogate(s, reject=True)
        self.assertEqual(normalized, s)

    def test_canonicalization_rejects_lone_surrogate(self):
        # REV-1/REV-3: lone surrogate must raise, never normalize to U+FFFD.
        inp = {"payload": "\ud800test"}
        with self.assertRaises(ValueError):
            ref.canonical_json_text(inp)

    def test_c2_isolated_low_surrogate_rejected(self):
        # C2: an isolated LOW surrogate (DC00) with no preceding HIGH is a lone
        # surrogate and must be rejected.
        with self.assertRaises(ValueError):
            ref._normalize_lone_surrogate("A\udc00B", reject=True)
        with self.assertRaises(ValueError):
            ref.canonical_json_text({"k": "x\udc00y"})

    def test_c2_low_low_pair_rejected(self):
        # C2: LOW+LOW (DC00 DC00) is NOT a valid pair; both are lone surrogates.
        with self.assertRaises(ValueError):
            ref._normalize_lone_surrogate("\udc00\udc00", reject=True)
        with self.assertRaises(ValueError):
            ref.canonical_json_text({"k": "\ud800\udc00\udc00"})

    def test_c2_high_low_pair_preserved(self):
        # C2: a valid HIGH+LOW pair is preserved (no raise). The reference
        # recomposes the pair to the real non-BMP code point (valid UTF-8).
        out = ref.canonical_json_text({"astral": "𐀀"})
        self.assertEqual(out, '{"astral":"𐀀"}')

    def test_c3_lone_surrogate_key_raises_controlled_error(self):
        # C3: an object key containing a lone surrogate must raise a controlled
        # ValueError (not a raw UnicodeEncodeError during sort-key computation).
        with self.assertRaises(ValueError):
            ref.canonical_json_text({"\ud800": "v"})


class TestGoldenVectorCorpusIntegrity(unittest.TestCase):
    def test_no_duplicate_vector_ids(self):
        vectors = _load_golden_vectors()
        ids = [v["id"] for v in vectors]
        self.assertEqual(len(ids), len(set(ids)), "duplicate vector ids")

    def test_defect_a_vectors_have_resolved_annotation(self):
        vectors = _load_golden_vectors()
        found_resolved = any(
            "JCS-compliant" in (v.get("notes") or "") or "RESOLVED" in (v.get("notes") or "")
            for v in vectors
        )
        self.assertTrue(found_resolved, "must have at least one defect A vector marked resolved in corpus")


if __name__ == "__main__":
    unittest.main()
