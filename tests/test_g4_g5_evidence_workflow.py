from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
G4_TOOL = ROOT / "tools" / "validate_g4_merge_authority.py"
G4_SCHEMA = ROOT / "schemas" / "g4-merge-authority-receipt.schema.json"
G4_TEMPLATE = ROOT / "templates" / "gates" / "g4-merge-authority-receipt.template.json"
G5_TOOL = ROOT / "tools" / "node_architect" / "validate_g5_ci_verification.py"
WORKFLOW = ROOT / ".github" / "workflows" / "g4-g5-evidence.yml"

SPEC = importlib.util.spec_from_file_location("validate_g4_merge_authority", G4_TOOL)
assert SPEC and SPEC.loader
G4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G4)

MERGE_SHA = "b" * 40
HEAD_SHA = "a" * 40


def enhanced_g5() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "g5-ci-verification-evidence",
        "generated_at": "2026-08-01T10:05:00Z",
        "task_id": "PR-152",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "gate": "G5_DEPLOY",
        "merge_commit_sha": MERGE_SHA,
        "g4_approval_id": "G4-PR-152",
        "classification": "success",
        "discovery": {
            "method": "exact_push_lookup",
            "exact_sha_lookup_attempted": True,
            "fallbacks_attempted": ["workflow_run_id", "combined_commit_status"],
        },
        "required_workflows": [
            {"name": "Validate instructions", "required": True},
            {"name": "Build instruction packages", "required": True},
        ],
        "selected_runs": [
            {
                "workflow": "Validate instructions",
                "run_id": 1,
                "run_attempt": 1,
                "head_sha": MERGE_SHA,
                "status": "completed",
                "conclusion": "success",
                "jobs": [],
            },
            {
                "workflow": "Build instruction packages",
                "run_id": 2,
                "run_attempt": 1,
                "head_sha": MERGE_SHA,
                "status": "completed",
                "conclusion": "success",
                "jobs": [],
            },
        ],
        "rejected_candidates": [],
        "checkpoint_required": False,
        "manual_action_authorized": False,
        "evidence_chain": {
            "g4_authority": {
                "approval_id": "G4-PR-152",
                "source_comment_id": 101,
                "approved_head_sha": HEAD_SHA,
                "scope_hash_prefix": "0123456789abcdef",
            },
            "merge_proof": {
                "provider": "github",
                "event": "pull_request.closed",
                "pr_number": 152,
                "merged_head_sha": HEAD_SHA,
                "merge_commit_sha": MERGE_SHA,
                "merged_at": "2026-08-01T10:01:00Z",
                "merged_by": "human-merger",
                "exact_head_match": True,
            },
            "canonical_machine_evidence": {
                "provider": "github_actions_artifact",
                "artifact_name": "g5-evidence-pr-152",
                "workflow_run_id": 3,
            },
            "human_traceability": {
                "provider": "github_pr_comment",
                "pr_number": 152,
                "comment_marker": "gwc:g5-status",
            },
            "projection_authority": {
                "jira": "projection_only",
                "slack": "projection_only",
            },
            "no_recursive_evidence_pr": True,
        },
    }


def run_g5(payload: dict) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "g5.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(G5_TOOL), str(path)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


class G4G5EvidenceWorkflowTests(unittest.TestCase):
    def test_g4_template_is_valid_and_unexpired_at_generation(self) -> None:
        record = json.loads(G4_TEMPLATE.read_text(encoding="utf-8"))
        schema = json.loads(G4_SCHEMA.read_text(encoding="utf-8"))
        now = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
        self.assertEqual([], G4.validate_record(record, schema, now=now))

    def test_g4_draft_or_expired_authority_fails(self) -> None:
        record = json.loads(G4_TEMPLATE.read_text(encoding="utf-8"))
        schema = json.loads(G4_SCHEMA.read_text(encoding="utf-8"))
        record["pr_state"]["draft"] = True
        issues = G4.validate_record(record, schema, now=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc))
        self.assertTrue(any("draft" in issue.lower() or "expired" in issue.lower() for issue in issues))

    def test_enhanced_g5_chain_passes(self) -> None:
        result = run_g5(enhanced_g5())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_g5_rejects_approval_to_merge_head_mismatch(self) -> None:
        payload = enhanced_g5()
        payload["evidence_chain"]["merge_proof"]["merged_head_sha"] = "c" * 40
        result = run_g5(payload)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("approved head", result.stdout)

    def test_workflow_separates_and_hardens_g4_g5_evidence(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for marker in (
            "issue_comment:",
            "pull_request:",
            "workflow_run:",
            "gwc:g4-authority-receipt",
            "gwc:g4-merge-proof",
            "gwc:g5-status",
            "github-actions[bot]",
            "issues.getComment",
            "getCollaboratorPermissionLevel",
            "pr.merged_by.login",
            "hasPending",
            "CONNECTOR_OBSERVABILITY_INCOMPLETE",
            "github_actions_artifact",
            "projection_only",
            "no_recursive_evidence_pr: true",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("git push", text)
        self.assertNotIn("merge_pull_request(", text)
        self.assertNotIn("create_pull_request", text)


if __name__ == "__main__":
    unittest.main()
