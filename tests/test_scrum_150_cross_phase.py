from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.validate_scrum_150_cross_phase import run_suite, validate_record


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "examples/integrations/cross-phase"


class Scrum150CrossPhaseTests(unittest.TestCase):
    def test_positive_contract_fixture_is_accepted(self) -> None:
        record = json.loads((FIXTURE_ROOT / "positive-cross-phase-run.json").read_text())
        self.assertEqual([], validate_record(record))

    def test_typed_fixture_suite_is_fail_closed(self) -> None:
        result = run_suite(ROOT)
        self.assertTrue(result["valid"], result)
        self.assertTrue(all(case["passed"] for case in result["cases"]), result)

    def test_stale_dependency_is_not_current_gate_truth(self) -> None:
        record = json.loads((FIXTURE_ROOT / "positive-cross-phase-run.json").read_text())
        record["dependencies"][0]["binding"]["rebaseline_status"] = "STALE"
        codes = {item["code"] for item in validate_record(record)}
        self.assertIn("STALE_DEPENDENCY_EVIDENCE", codes)

    def test_projection_cannot_grant_gate_authority(self) -> None:
        record = json.loads((FIXTURE_ROOT / "positive-cross-phase-run.json").read_text())
        record["projections"][0]["grants_gate_authority"] = True
        codes = {item["code"] for item in validate_record(record)}
        self.assertIn("PROJECTION_AUTHORITY_LEAKAGE", codes)


if __name__ == "__main__":
    unittest.main()
