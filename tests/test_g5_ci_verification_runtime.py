from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "node_architect" / "validate_g5_ci_verification.py"
MERGE_SHA = "a" * 40


def evidence(classification="success", selected_runs=None, rejected_candidates=None, checkpoint_required=False):
    return {
        "schema_version": "1.0",
        "artifact_type": "g5-ci-verification-evidence",
        "generated_at": "2026-07-23T00:00:00Z",
        "task_id": "SCRUM-75",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "gate": "G5_DEPLOY",
        "merge_commit_sha": MERGE_SHA,
        "g4_approval_id": "CP-G4",
        "g4_scope_hash": "sha256:" + "b" * 64,
        "classification": classification,
        "discovery": {
            "method": "exact_push_lookup",
            "exact_sha_lookup_attempted": True,
            "fallbacks_attempted": ["known_run_id", "combined_commit_status"],
        },
        "required_workflows": [{"name": "Validate instructions", "required": True}],
        "selected_runs": selected_runs if selected_runs is not None else [{
            "workflow": "Validate instructions",
            "run_id": 29977733907,
            "run_attempt": 1,
            "head_sha": MERGE_SHA,
            "status": "completed",
            "conclusion": "success",
            "jobs": [{"job_id": 89112982225, "name": "validate", "status": "completed", "conclusion": "success"}],
        }],
        "rejected_candidates": rejected_candidates or [],
        "checkpoint_required": checkpoint_required,
        "manual_action_authorized": False,
    }


def run_validator(payload):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "evidence.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run([sys.executable, str(VALIDATOR), str(path)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class G5CiVerificationRuntimeTests(unittest.TestCase):
    def test_success_requires_exact_merge_sha_and_required_workflow(self):
        result = run_validator(evidence())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASSED", result.stdout)

    def test_success_rejects_sha_mismatch(self):
        payload = evidence(selected_runs=[{
            "workflow": "Validate instructions",
            "run_id": 1,
            "run_attempt": 1,
            "head_sha": "c" * 40,
            "status": "completed",
            "conclusion": "success",
            "jobs": [],
        }])
        result = run_validator(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not bound to merge SHA", result.stdout)

    def test_empty_lookup_is_observability_incomplete_not_pending(self):
        payload = evidence(
            classification="CONNECTOR_OBSERVABILITY_INCOMPLETE",
            selected_runs=[],
            checkpoint_required=False,
        )
        payload["discovery"]["method"] = "connector_incomplete"
        result = run_validator(payload)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ci_pending_requires_checkpoint(self):
        payload = evidence(classification="CI_PENDING", checkpoint_required=False)
        payload["selected_runs"][0]["status"] = "in_progress"
        payload["selected_runs"][0]["conclusion"] = None
        result = run_validator(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checkpoint", result.stdout)

    def test_sha_mismatch_requires_rejected_candidate(self):
        payload = evidence(classification="SHA_MISMATCH", selected_runs=[], rejected_candidates=[])
        result = run_validator(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rejected candidate", result.stdout)

    def test_failed_exact_run_is_failure(self):
        payload = evidence(classification="failure")
        payload["selected_runs"][0]["conclusion"] = "failure"
        payload["selected_runs"][0]["jobs"][0]["conclusion"] = "failure"
        result = run_validator(payload)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
