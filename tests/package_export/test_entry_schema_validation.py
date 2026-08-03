"""Fixture-driven tests for package_export entry-schema-validation (SCRUM-230).

Layout ported from PR #199 (fixture organization). The regression guard that
matters here: a manifest containing two entries with the SAME ``id`` must still
produce TWO inventory records — inventory is addressed by entry index, never
keyed by ``entry_id``.
"""
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
# Import the evaluator from the repo's tools/ dir directly (a host env may own a
# different top-level `tools` package under the bare CI unittest discovery).
sys.path.insert(0, str(_REPO_ROOT / "tools"))
sys.path.insert(0, str(_HERE))

from node_architect.package_export.entry_schema_validation import (  # noqa: E402
    ENTRY_DUPLICATE_ID,
    Outcome,
    validate_entries,
)

from fixtures import ALL_FIXTURES, FIXTURE_DUPLICATE_ID, FIXTURE_SOURCE_SHA  # noqa: E402


class FixtureMatrixTest(unittest.TestCase):
    """Every fixture class produces its expected outcome and acceptance vector."""

    def test_all_fixtures(self):
        for name, fx in ALL_FIXTURES.items():
            with self.subTest(fixture=name):
                result = validate_entries(fx["manifest"], source_sha=FIXTURE_SOURCE_SHA)
                self.assertEqual(result.outcome.value, fx["expected_outcome"])
                self.assertEqual(
                    [v.accepted for v in result.inventory],
                    fx["expected_accepted"],
                )

    def test_inventory_covers_every_entry(self):
        for name, fx in ALL_FIXTURES.items():
            with self.subTest(fixture=name):
                result = validate_entries(fx["manifest"], source_sha=FIXTURE_SOURCE_SHA)
                self.assertEqual(
                    len(result.inventory),
                    len(fx["manifest"]["entries"]),
                    "inventory must hold exactly one record per manifest entry",
                )
                self.assertEqual(
                    [v.entry_index for v in result.inventory],
                    list(range(len(fx["manifest"]["entries"]))),
                )


class DuplicateIdInventoryTest(unittest.TestCase):
    """Duplicate entry ids must NOT collapse into a single inventory record."""

    def setUp(self):
        self.manifest = FIXTURE_DUPLICATE_ID["manifest"]
        self.result = validate_entries(self.manifest, source_sha=FIXTURE_SOURCE_SHA)

    def test_two_duplicate_entries_produce_two_inventory_records(self):
        same_id = [v for v in self.result.inventory if v.entry_id == "alpha"]
        self.assertEqual(len(same_id), 2)
        self.assertEqual([v.entry_index for v in same_id], [0, 1])

    def test_duplicate_is_reported_and_outcome_fails(self):
        self.assertEqual(self.result.outcome, Outcome.FAIL)
        dup_errors = [e for e in self.result.errors if e.reason_code == ENTRY_DUPLICATE_ID]
        self.assertEqual(len(dup_errors), 1)
        self.assertEqual(dup_errors[0].entry_index, 1)

    def test_first_occurrence_accepted_duplicate_rejected(self):
        self.assertTrue(self.result.inventory[0].accepted)
        self.assertFalse(self.result.inventory[1].accepted)

    def test_three_way_duplicate_produces_three_records(self):
        entry = dict(self.manifest["entries"][0])
        manifest = {"entries": [dict(entry), dict(entry), dict(entry)]}
        result = validate_entries(manifest, source_sha=FIXTURE_SOURCE_SHA)
        self.assertEqual(len(result.inventory), 3)
        self.assertEqual([v.entry_index for v in result.inventory], [0, 1, 2])
        dup_errors = [e for e in result.errors if e.reason_code == ENTRY_DUPLICATE_ID]
        self.assertEqual(len(dup_errors), 2)


class DeterminismTest(unittest.TestCase):
    def test_repeated_evaluation_is_identical(self):
        for name, fx in ALL_FIXTURES.items():
            with self.subTest(fixture=name):
                a = validate_entries(fx["manifest"], source_sha=FIXTURE_SOURCE_SHA)
                b = validate_entries(fx["manifest"], source_sha=FIXTURE_SOURCE_SHA)
                self.assertEqual(a.to_json(), b.to_json())
                self.assertEqual(a.semantic_digest(), b.semantic_digest())


if __name__ == "__main__":
    unittest.main()
