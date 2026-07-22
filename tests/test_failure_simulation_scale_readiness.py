from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.node_architect.validate_failure_simulation_matrix import main


REQUIRED_CASE_IDS = [
    "unknown_write_result_reconciles_before_retry",
    "cas_mismatch_reloads_checkpoint",
    "lease_expired_stops_or_reacquires",
    "approval_expired_regenerates_request",
    "duplicate_agent_blocked_by_lease",
    "node_version_drift_pins_or_restarts",
]


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://gwc.local/schemas/node-architect/failure-simulation-matrix.schema.json",
    "title": "Failure Simulation Matrix",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "matrix_id", "scale_81_nodes_allowed", "required_cases"],
    "properties": {
        "scale_81_nodes_allowed": {"const": False},
        "required_cases": {"type": "array", "minItems": 6},
    },
}


def valid_matrix() -> dict:
    return {
        "schema_version": "0.1",
        "matrix_id": "revamp-gwc-013-failure-simulation-scale-readiness",
        "scale_81_nodes_allowed": False,
        "required_cases": [
            {
                "case_id": case_id,
                "trigger": "trigger",
                "expected_response": "expected",
                "forbidden_behaviors": ["forbidden"],
                "evidence_required": ["evidence"],
            }
            for case_id in REQUIRED_CASE_IDS
        ],
    }


class FailureSimulationScaleReadinessTests(unittest.TestCase):
    def _write_files(self, root: Path, matrix: dict | None = None, schema: dict | None = None) -> None:
        matrix_path = root / "core" / "node-architect" / "failure-simulation-matrix.json"
        schema_path = root / "schemas" / "node-architect" / "failure-simulation-matrix.schema.json"
        matrix_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        matrix_path.write_text(json.dumps(valid_matrix() if matrix is None else matrix, indent=2) + "\n", encoding="utf-8")
        schema_path.write_text(json.dumps(SCHEMA if schema is None else schema, indent=2) + "\n", encoding="utf-8")

    def test_valid_matrix_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_files(root)
            self.assertEqual(main(["--root", str(root)]), 0)

    def test_scale_allowed_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            matrix = valid_matrix()
            matrix["scale_81_nodes_allowed"] = True
            self._write_files(root, matrix=matrix)
            self.assertEqual(main(["--root", str(root)]), 1)

    def test_missing_required_case_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            matrix = valid_matrix()
            matrix["required_cases"] = matrix["required_cases"][:-1]
            self._write_files(root, matrix=matrix)
            self.assertEqual(main(["--root", str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
