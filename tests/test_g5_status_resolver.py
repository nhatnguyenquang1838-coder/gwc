from __future__ import annotations

import copy
import unittest
from pathlib import Path

from tools.resolve_g5_status import resolve
from tools.validate_g5_status import validate


ROOT = Path(__file__).resolve().parents[1]
MERGE_SHA = "a" * 40


def candidate(workflow: str, run_id: int, *, head_sha: str = MERGE_SHA, status: str = "completed", conclusion: str | None = "success") -> dict:
    return {
        "workflow": workflow,
        "run_id": run_id,
        "run_attempt": 1,
        "head_sha": head_sha,
        "status": status,
        "conclusion": conclusion,
        "jobs": [],
    }


def payload(candidates: list[dict]) -> dict:
    return {
        "task_id": "SCRUM-103",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "merge_commit_sha": MERGE_SHA,
        "generated_at": "2026-07-26T07:00:00Z",
        "required_workflows": ["Validate instructions", "Build instruction packages"],
        "discovery": {
            "method": "exact_push_lookup",
            "exact_sha_lookup_attempted": True,
            "fallbacks_attempted": ["known_run_id", "combined_commit_status"],
        },
        "candidates": candidates,
    }


class G5StatusResolverTests(unittest.TestCase):
    def test_exact_sha_success_is_valid(self):
        evidence = resolve(payload([
            candidate("Validate instructions", 10),
            candidate("Build instruction packages", 11),
            candidate("Validate instructions", 9),
        ]))
        self.assertEqual("success", evidence["classification"])
        self.assertEqual(2, len(evidence["selected_runs"]))
        self.assertTrue(any(item["reason"] == "stale_attempt" for item in evidence["rejected_candidates"]))
        self.assertEqual([], validate(evidence, ROOT / "schemas/g5-status-evidence.schema.json"))

    def test_sha_mismatch_is_not_selected(self):
        evidence = resolve(payload([candidate("Validate instructions", 10, head_sha="b" * 40)]))
        self.assertEqual("SHA_MISMATCH", evidence["classification"])
        self.assertTrue(any(item["reason"] == "sha_mismatch" for item in evidence["rejected_candidates"]))
        self.assertEqual([], validate(evidence, ROOT / "schemas/g5-status-evidence.schema.json"))

    def test_pending_requires_checkpoint(self):
        value = payload([candidate("Validate instructions", 10, status="in_progress", conclusion=None)])
        value["checkpoint_path"] = ".gwc/tasks/SCRUM-103/g5/checkpoint.json"
        evidence = resolve(value)
        self.assertEqual("CI_PENDING", evidence["classification"])
        self.assertEqual([], validate(evidence, ROOT / "schemas/g5-status-evidence.schema.json"))

        invalid = copy.deepcopy(evidence)
        invalid.pop("checkpoint_path")
        self.assertTrue(validate(invalid, ROOT / "schemas/g5-status-evidence.schema.json"))

    def test_empty_lookup_is_observability_gap(self):
        evidence = resolve(payload([]))
        evidence["discovery"]["method"] = "connector_incomplete"
        self.assertEqual("CONNECTOR_OBSERVABILITY_INCOMPLETE", evidence["classification"])
        self.assertEqual([], validate(evidence, ROOT / "schemas/g5-status-evidence.schema.json"))


if __name__ == "__main__":
    unittest.main()
