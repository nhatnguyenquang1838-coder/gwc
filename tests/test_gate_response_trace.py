from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "trace_validator", ROOT / "tools/validate_gate_response_trace.py"
)
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)
SCHEMA = ROOT / "schemas/gate-response-trace.schema.json"


def valid_trace() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "artifact_type": "gate-response-trace",
        "gate": "G2_EXECUTION",
        "Skills called": ["DWC GitHub", "Context7 JSON Schema"],
        "Started at UTC": "2026-07-21T02:00:00Z",
        "Ended at UTC": "2026-07-21T02:10:00Z",
    }


class GateResponseTraceTests(unittest.TestCase):
    def test_valid_trace(self) -> None:
        self.assertEqual(VALIDATOR.validate_trace(valid_trace(), SCHEMA), [])

    def test_empty_skills_rejected(self) -> None:
        value = valid_trace()
        value["Skills called"] = []
        self.assertTrue(VALIDATOR.validate_trace(value, SCHEMA))

    def test_duplicate_skills_rejected(self) -> None:
        value = valid_trace()
        value["Skills called"] = ["DWC", "DWC"]
        self.assertTrue(VALIDATOR.validate_trace(value, SCHEMA))

    def test_non_utc_timestamp_rejected(self) -> None:
        value = valid_trace()
        value["Started at UTC"] = "2026-07-21T09:00:00+07:00"
        self.assertTrue(VALIDATOR.validate_trace(value, SCHEMA))

    def test_end_before_start_rejected(self) -> None:
        value = valid_trace()
        value["Ended at UTC"] = "2026-07-21T01:59:59Z"
        self.assertIn(
            "Ended at UTC must be equal to or later than Started at UTC",
            VALIDATOR.validate_trace(value, SCHEMA),
        )


if __name__ == "__main__":
    unittest.main()
