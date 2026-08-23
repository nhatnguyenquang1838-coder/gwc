#!/usr/bin/env python3
"""Conformance vector tests (SCRUM-396, AC19) — Python reference verifier.

Asserts the repo's canonical_json + sha256 matches the golden vectors. A Go
implementation of the same canonicalization must produce identical digests
(independent-implementation guard). Vectors in tests/conformance_vectors/.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from tools.node_architect.schema_compatibility_resolver import canonical_json

VECTORS_PATH = Path(__file__).parent / "conformance_vectors" / "jcs_vectors.json"


def digest(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class ConformanceVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(VECTORS_PATH, "r", encoding="utf-8") as fh:
            cls.vectors = json.load(fh)

    def test_vector_file_wellformed(self) -> None:
        self.assertEqual(self.vectors["profile_id"], "gwc-jcs-v1")
        self.assertEqual(self.vectors["hash_algorithm"], "sha256")

    def test_all_cases_match_python_reference(self) -> None:
        for case in self.vectors["cases"]:
            with self.subTest(case_id=case["id"]):
                actual = digest(case["input"])
                self.assertEqual(
                    actual,
                    case["expected_canonical_sha256"],
                    f"case {case['id']} canonical digest mismatch",
                )

    def test_deterministic_key_order_independent(self) -> None:
        """Same semantic object with different insertion order -> same digest."""
        a = digest({"a": 1, "b": 2})
        b = digest({"b": 2, "a": 1})
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
