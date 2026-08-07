from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.node_architect.validate_autonomous_preprod_policy import (
    canonical_digest,
    task_scope_hash,
    validate_manifest,
    validate_policy,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 7, 3, 0, tzinfo=timezone.utc)
BASE_SHA = "a" * 40


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
        "allowed_g2_actions": ["modify_approved_files", "run_sandboxed_validation", "push_working_branch"],
        "allowed_g4_actions": ["merge_approved_pr"],
        "denied_actions": [
            "direct_write_to_main", "direct_write_to_pre_prod", "create_or_protect_pre_prod_branch",
            "deploy_approved_release", "runtime_reload", "production_data_read", "production_data_write",
            "production_config_change", "credential_rotation", "secret_operation", "migration", "force_push",
            "branch_deletion", "history_rewrite", "pr_base_change",
        ],
        "control_plane_protected_paths": [
            "governance/autonomous-preprod-policy.yaml",
            "schemas/autonomous-preprod-run-policy.schema.json",
            "tools/node_architect/validate_autonomous_preprod_policy.py",
            "tools/node_architect/derive_task_authority.py",
            "tools/validate_gate_action.py",
        ],
        "issued_at": "2026-08-07T00:00:00Z",
        "expires_at": "2026-08-08T00:00:00Z",
    }


def task(*, risk: str = "R2", paths: list[str] | None = None) -> dict:
    value = {
        "task_id": "SCRUM-900",
        "risk_class": risk,
        "working_branch": "auto/run-1/SCRUM-900",
        "authorized_paths": paths or ["src/feature.py", "tests/test_feature.py"],
        "authorized_g2_actions": ["modify_approved_files", "run_sandboxed_validation", "push_working_branch"],
    }
    value["scope_hash"] = task_scope_hash(value)
    return value


def manifest(p: dict | None = None, *, tasks: list[dict] | None = None) -> dict:
    p = p or policy()
    return {
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


class AutonomousPreprodPolicyTests(unittest.TestCase):
    def test_valid_policy_and_manifest_pass(self):
        p = policy()
        self.assertEqual("PASS", validate_policy(p, root=ROOT, now=NOW)["outcome"])
        result = validate_manifest(p, manifest(p), root=ROOT, now=NOW)
        self.assertEqual("PASS", result["outcome"])
        self.assertTrue(result["policy_digest"].startswith("sha256:"))
        self.assertTrue(result["manifest_digest"].startswith("sha256:"))

    def test_same_inputs_have_same_digests(self):
        p = policy(); m = manifest(p)
        first = validate_manifest(p, m, root=ROOT, now=NOW)
        second = validate_manifest(copy.deepcopy(p), copy.deepcopy(m), root=ROOT, now=NOW)
        self.assertEqual(first["policy_digest"], second["policy_digest"])
        self.assertEqual(first["manifest_digest"], second["manifest_digest"])

    def test_expired_policy_fails_closed(self):
        p = policy(); p["expires_at"] = "2026-08-07T02:00:00Z"
        result = validate_policy(p, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_POLICY_EXPIRED", result["reason_codes"])

    def test_policy_digest_drift_invalidates_manifest(self):
        p = policy(); m = manifest(p); p["policy_revision"] = "test-v2"
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_POLICY_REVISION_DRIFT", result["reason_codes"])
        self.assertIn("AUTONOMOUS_POLICY_DIGEST_DRIFT", result["reason_codes"])

    def test_r3_child_is_blocked(self):
        p = policy(); m = manifest(p, tasks=[task(risk="R3")])
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING", result["reason_codes"])

    def test_control_plane_self_modification_is_blocked(self):
        p = policy(); m = manifest(p, tasks=[task(paths=["tools/validate_gate_action.py"])])
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_CONTROL_PLANE_SELF_MODIFICATION_FORBIDDEN", result["reason_codes"])

    def test_scope_hash_tampering_is_blocked(self):
        p = policy(); m = manifest(p); m["allowed_tasks"][0]["authorized_paths"].append("src/extra.py")
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_SCOPE_DRIFT", result["reason_codes"])

    def test_main_target_has_terminal_reason(self):
        p = policy(); m = manifest(p); m["target_branch"] = "main"
        result = validate_manifest(p, m, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_MAIN_TARGET_FORBIDDEN", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
