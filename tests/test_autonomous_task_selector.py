from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.node_architect.select_autonomous_jira_task import select_autonomous_jira_task


class AutonomousTaskSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "schema_version": "1.0",
            "artifact_type": "autonomous-task-selection-input",
            "run_id": "run-scrum-270",
            "active_lane": "SCRUM-270",
            "excluded_lanes": ["SCRUM-275", "SCRUM-276"],
            "manifest": {
                "allowed_tasks": [
                    {"task_id": "SCRUM-274"},
                    {"task_id": "SCRUM-275"},
                    {"task_id": "SCRUM-280"},
                    {"task_id": "SCRUM-281"},
                ]
            },
            "jira_tasks": [
                {"task_id": "SCRUM-274", "lane": "SCRUM-270", "status": "Ready", "priority": "High", "dependencies": ["SCRUM-273"]},
                {"task_id": "SCRUM-275", "lane": "SCRUM-275", "status": "Ready", "priority": "Highest", "dependencies": []},
                {"task_id": "SCRUM-280", "lane": "SCRUM-270", "status": "Ready", "priority": "High", "dependencies": ["SCRUM-270-REFINE"]},
                {"task_id": "SCRUM-281", "lane": "SCRUM-270", "status": "Ready", "priority": "Medium", "dependencies": []},
                {"task_id": "SCRUM-999", "lane": "SCRUM-270", "status": "Ready", "priority": "Highest", "dependencies": []},
            ],
            "dependency_evidence": {
                "SCRUM-273": {
                    "jira_status": "Done",
                    "semantic_state": "deliverable",
                    "repository_implementation": True,
                    "exact_sha_verified": True,
                    "evidence_refs": ["git:63210d7bb58b9b1043a1f34766062533e6744d06"],
                },
                "SCRUM-270-REFINE": {
                    "jira_status": "Done",
                    "semantic_state": "refinement-only",
                    "repository_implementation": False,
                    "exact_sha_verified": False,
                    "evidence_refs": ["jira:SCRUM-270-REFINE"],
                },
            },
        }

    def test_mixed_fixture_selects_one_deterministic_eligible_task(self) -> None:
        first = select_autonomous_jira_task(self.payload)
        second = select_autonomous_jira_task(copy.deepcopy(self.payload))
        self.assertEqual(first, second)
        self.assertEqual(first["selected_task"], "SCRUM-274")
        self.assertEqual(first["next_eligible_tasks"], ["SCRUM-281"])
        self.assertFalse(first["parallel_execution_allowed"])
        self.assertFalse(first["authority_granted"])
        self.assertEqual(first["selection_reason"], "SELECTED_DEPENDENCY_READY_PRIORITY_MANIFEST_ORDER")

    def test_out_of_manifest_and_out_of_lane_are_never_selected(self) -> None:
        result = select_autonomous_jira_task(self.payload)
        selected_or_next = [result["selected_task"], *result["next_eligible_tasks"]]
        self.assertNotIn("SCRUM-999", selected_or_next)
        self.assertNotIn("SCRUM-275", selected_or_next)

    def test_unsafe_done_dependency_is_explicit_and_blocks_candidate(self) -> None:
        result = select_autonomous_jira_task(self.payload)
        unsafe = {row["task_id"]: row for row in result["unsafe_done_dependencies"]}
        self.assertIn("SCRUM-270-REFINE", unsafe)
        self.assertIn("REFINEMENT_ONLY", unsafe["SCRUM-270-REFINE"]["reasons"])
        self.assertIn("REPOSITORY_IMPLEMENTATION_MISSING", unsafe["SCRUM-270-REFINE"]["reasons"])
        self.assertIn("EXACT_SHA_EVIDENCE_MISSING", unsafe["SCRUM-270-REFINE"]["reasons"])
        self.assertNotIn("SCRUM-280", result["next_eligible_tasks"])

    def test_priority_then_manifest_order_is_deterministic(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["jira_tasks"][3]["priority"] = "High"
        result = select_autonomous_jira_task(payload)
        self.assertEqual(result["selected_task"], "SCRUM-274")
        self.assertEqual(result["next_eligible_tasks"], ["SCRUM-281"])

    def test_done_without_exact_sha_is_unsafe(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["dependency_evidence"]["SCRUM-273"]["exact_sha_verified"] = False
        result = select_autonomous_jira_task(payload)
        self.assertEqual(result["selected_task"], "SCRUM-281")
        unsafe = {row["task_id"]: row for row in result["unsafe_done_dependencies"]}
        self.assertIn("EXACT_SHA_EVIDENCE_MISSING", unsafe["SCRUM-273"]["reasons"])

    def test_input_and_result_validate_against_closed_schema(self) -> None:
        result = select_autonomous_jira_task(self.payload)
        schema = json.loads((ROOT / "schemas/node-architect/autonomous-task-selection.schema.json").read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertEqual(list(validator.iter_errors(self.payload)), [])
        self.assertEqual(list(validator.iter_errors(result)), [])


if __name__ == "__main__":
    unittest.main()
