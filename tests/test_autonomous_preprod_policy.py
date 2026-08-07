from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml

from tools.node_architect.validate_autonomous_preprod_policy import (
    MANDATORY_CONTROL_PLANE_PROTECTED_PATHS,
    authority_receipt_digest,
    canonical_digest,
    manifest_approval_scope_digest,
    task_scope_hash,
    validate_manifest,
    validate_policy,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 7, 3, 0, tzinfo=timezone.utc)
BASE_SHA = "a" * 40
G2_ACTIONS = [
    "create_guarded_branch_or_worktree",
    "modify_approved_files",
    "run_sandboxed_validation",
    "stage",
    "create_commit",
    "push_working_branch",
]


def policy() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-run-policy",
        "policy_id": "AUTONOMOUS_PREPROD_INTEGRATION_POLICY",
        "policy_revision": "test-v1",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "target_branch": "pre-prod",
        "allowed_branch_prefix": "auto/",
        "max_child_risk": "R2",
        "allowed_g2_actions": list(G2_ACTIONS),
        "allowed_g4_actions": ["merge_approved_pr"],
        "denied_actions": [
            "direct_write_to_main", "direct_write_to_pre_prod", "create_or_protect_pre_prod_branch",
            "deploy_approved_release", "runtime_reload", "production_data_read", "production_data_write",
            "production_config_change", "credential_rotation", "secret_operation", "migration", "force_push",
            "branch_deletion", "history_rewrite", "pr_base_change",
        ],
        "control_plane_protected_paths": sorted(MANDATORY_CONTROL_PLANE_PROTECTED_PATHS),
        "issued_at": "2026-08-07T00:00:00Z",
        "expires_at": "2026-08-08T00:00:00Z",
    }


def task(*, risk: str = "R2", paths: list[str] | None = None) -> dict:
    value = {
        "task_id": "SCRUM-900",
        "risk_class": risk,
        "working_branch": "auto/run-1/SCRUM-900",
        "authorized_paths": paths or ["src/feature.py", "tests/test_feature.py"],
        "authorized_g2_actions": list(G2_ACTIONS),
    }
    value["scope_hash"] = task_scope_hash(value)
    return value


def manifest(p: dict | None = None, *, tasks: list[dict] | None = None) -> dict:
    p = p or policy()
    value = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-run-manifest",
        "run_id": "run-test-1",
        "repository": p["repository"],
        "policy_id": p["policy_id"],
        "policy_revision": p["policy_revision"],
        "policy_digest": canonical_digest(p),
        "approved_base_ref": "main",
        "approved_base_sha": BASE_SHA,
        "target_branch": "pre-prod",
        "allowed_tasks": tasks or [task()],
        "issued_at": "2026-08-07T01:00:00Z",
        "expires_at": "2026-08-07T23:00:00Z",
        "idempotency_key": "run-test-1-idempotency",
    }
    value["authority_receipt"] = {
        "status": "present",
        "source": "github_actions_bot_comment",
        "bot_login": "github-actions[bot]",
        "marker": "gwc:autonomous-preprod-run-authority-receipt",
        "approval_id": "APPROVE_AUTONOMOUS_RUN_TEST_1",
        "receipt_comment_id": 900101,
        "source_comment_id": 900100,
        "approved_run_id": value["run_id"],
        "approved_policy_id": value["policy_id"],
        "approved_policy_revision": value["policy_revision"],
        "approved_policy_digest": value["policy_digest"],
        "manifest_scope_digest": manifest_approval_scope_digest(value),
        "scope_hash_prefix": "0123456789abcdef",
        "issued_at": "2026-08-07T01:05:00Z",
        "expires_at": "2026-08-07T23:30:00Z",
    }
    return value


class AutonomousPreprodPolicyTests(unittest.TestCase):
    def test_valid_policy_and_approved_manifest_pass(self):
        p = policy(); m = manifest(p)
        self.assertEqual("PASS", validate_policy(p, root=ROOT, now=NOW)["outcome"])
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertEqual("PASS", result["outcome"])
        self.assertEqual(authority_receipt_digest(m["authority_receipt"]), result["authority_receipt_digest"])

    def test_same_inputs_have_same_digests(self):
        p = policy(); m = manifest(p)
        first = validate_manifest(p, m, root=ROOT, now=NOW)
        second = validate_manifest(copy.deepcopy(p), copy.deepcopy(m), root=ROOT, now=NOW)
        self.assertEqual(first["policy_digest"], second["policy_digest"])
        self.assertEqual(first["manifest_digest"], second["manifest_digest"])
        self.assertEqual(first["authority_receipt_digest"], second["authority_receipt_digest"])

    def test_expired_policy_fails_closed(self):
        p = policy(); p["expires_at"] = "2026-08-07T02:00:00Z"
        self.assertIn("AUTONOMOUS_POLICY_EXPIRED", validate_policy(p, root=ROOT, now=NOW)["reason_codes"])

    def test_policy_digest_drift_invalidates_manifest(self):
        p = policy(); m = manifest(p); p["policy_revision"] = "test-v2"
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_POLICY_REVISION_DRIFT", result["reason_codes"])
        self.assertIn("AUTONOMOUS_POLICY_DIGEST_DRIFT", result["reason_codes"])
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", result["reason_codes"])

    def test_r3_child_is_blocked(self):
        p = policy(); m = manifest(p, tasks=[task(risk="R3")])
        self.assertIn("AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING", validate_manifest(p, m, root=ROOT, now=NOW)["reason_codes"])

    def test_control_plane_self_modification_is_blocked(self):
        p = policy(); m = manifest(p, tasks=[task(paths=["tools/node_architect/autonomous_preprod_runtime.py"])])
        self.assertIn("AUTONOMOUS_CONTROL_PLANE_SELF_MODIFICATION_FORBIDDEN", validate_manifest(p, m, root=ROOT, now=NOW)["reason_codes"])

    def test_path_traversal_cannot_bypass_control_plane_protection(self):
        p = policy(); m = manifest(p, tasks=[task(paths=["tools/node_architect/../node_architect/autonomous_preprod_runtime.py"])])
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertEqual("BLOCKED", result["outcome"])
        self.assertIn("AUTONOMOUS_SCOPE_DRIFT", result["reason_codes"])

    def test_repository_root_scope_is_blocked(self):
        p = policy(); m = manifest(p, tasks=[task(paths=["."])])
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertEqual("BLOCKED", result["outcome"])
        self.assertIn("AUTONOMOUS_SCOPE_DRIFT", result["reason_codes"])

    def test_active_policy_preserves_mandatory_control_plane(self):
        active = yaml.safe_load((ROOT / "governance/autonomous-preprod-policy.yaml").read_text(encoding="utf-8"))
        self.assertTrue(MANDATORY_CONTROL_PLANE_PROTECTED_PATHS.issubset(set(active["control_plane_protected_paths"])))

    def test_policy_cannot_drop_mandatory_control_plane(self):
        p = policy(); p["control_plane_protected_paths"].remove(".github/workflows")
        result = validate_policy(p, root=ROOT, now=NOW)
        self.assertEqual("BLOCKED", result["outcome"])
        self.assertIn("AUTONOMOUS_POLICY_INVALID", result["reason_codes"])

    def test_scope_hash_tampering_is_blocked(self):
        p = policy(); m = manifest(p); m["allowed_tasks"][0]["authorized_paths"].append("src/extra.py")
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_SCOPE_DRIFT", result["reason_codes"])
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", result["reason_codes"])

    def test_main_target_has_terminal_reason(self):
        p = policy(); m = manifest(p); m["target_branch"] = "main"
        self.assertIn("AUTONOMOUS_MAIN_TARGET_FORBIDDEN", validate_manifest(p, m, root=ROOT, now=NOW)["reason_codes"])

    def test_missing_parent_authority_is_blocked(self):
        p = policy(); m = manifest(p); m.pop("authority_receipt")
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", validate_manifest(p, m, root=ROOT, now=NOW)["reason_codes"])

    def test_forged_parent_authority_source_is_blocked(self):
        p = policy(); m = manifest(p); m["authority_receipt"]["source"] = "caller_supplied"
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", validate_manifest(p, m, root=ROOT, now=NOW)["reason_codes"])

    def test_manifest_edit_after_approval_invalidates_parent_receipt(self):
        p = policy(); m = manifest(p); m["idempotency_key"] = "tampered-after-approval"
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
