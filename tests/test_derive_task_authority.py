from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.test_autonomous_preprod_policy import BASE_SHA, G2_ACTIONS, manifest, policy
from tools.node_architect.derive_task_authority import derive_g2_authority, derive_g4_receipt, validate_g4_receipt

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 7, 3, 0, tzinfo=timezone.utc)
HEAD_SHA = "b" * 40
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64


def g2_request() -> dict:
    return {
        "task_id": "SCRUM-900",
        "observed_base_sha": BASE_SHA,
        "working_branch": "auto/run-1/SCRUM-900",
        "risk_class": "R2",
        "requested_paths": ["src/feature.py", "tests/test_feature.py"],
        "requested_actions": list(G2_ACTIONS),
    }


def g4_context(m: dict | None = None) -> dict:
    m = m or manifest(policy())
    return {
        "task_id": "SCRUM-900",
        "target_branch": "pre-prod",
        "pr_number": 900,
        "approved_head_sha": HEAD_SHA,
        "task_scope_hash": m["allowed_tasks"][0]["scope_hash"],
        "pr_body_digest": DIGEST_A,
        "managed_block_digest": DIGEST_B,
        "run_graph_digest": DIGEST_C,
        "gate_story_digest": DIGEST_D,
        "evidence_digest": DIGEST_E,
    }


class TaskAuthorityDerivationTests(unittest.TestCase):
    def test_valid_g2_is_task_scoped_deterministic_and_parent_bound(self):
        p = policy(); m = manifest(p); request = g2_request()
        first = derive_g2_authority(p, m, request, root=ROOT, now=NOW)
        second = derive_g2_authority(copy.deepcopy(p), copy.deepcopy(m), copy.deepcopy(request), root=ROOT, now=NOW)
        self.assertEqual("ALLOW", first["decision"])
        self.assertEqual("G2_EXECUTION", first["gate"])
        self.assertFalse(first["g4_g5_g6_authority_granted"])
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        self.assertEqual(m["authority_receipt"]["approval_id"], first["parent_approval_id"])
        self.assertEqual(m["authority_receipt"]["scope_hash_prefix"], first["parent_scope_hash_prefix"])
        self.assertTrue(first["parent_authority_digest"].startswith("sha256:"))
        self.assertEqual(m["allowed_tasks"][0]["risk_class"], first["risk_class"])
        self.assertIn("create_commit", first["authorized_actions"])

    def test_unknown_task_is_denied(self):
        p = policy(); m = manifest(p); request = g2_request(); request["task_id"] = "SCRUM-999"
        self.assertEqual("AUTONOMOUS_TASK_NOT_ALLOWLISTED", derive_g2_authority(p, m, request, root=ROOT, now=NOW)["reason_code"])

    def test_base_drift_is_denied(self):
        p = policy(); m = manifest(p); request = g2_request(); request["observed_base_sha"] = "f" * 40
        self.assertEqual("AUTONOMOUS_BASE_SHA_MISMATCH", derive_g2_authority(p, m, request, root=ROOT, now=NOW)["reason_code"])

    def test_unallowlisted_action_is_denied(self):
        p = policy(); m = manifest(p); request = g2_request(); request["requested_actions"] = ["merge_approved_pr"]
        self.assertEqual("AUTONOMOUS_ACTION_FORBIDDEN", derive_g2_authority(p, m, request, root=ROOT, now=NOW)["reason_code"])

    def test_risk_downgrade_is_scope_drift(self):
        p = policy(); m = manifest(p); request = g2_request(); request["risk_class"] = "R0"
        result = derive_g2_authority(p, m, request, root=ROOT, now=NOW)
        self.assertEqual("DENY", result["decision"])
        self.assertEqual("AUTONOMOUS_SCOPE_DRIFT", result["reason_code"])

    def test_untrusted_parent_run_cannot_derive_g2(self):
        p = policy(); m = manifest(p); m["authority_receipt"]["manifest_scope_digest"] = "sha256:" + "f" * 64
        self.assertEqual("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", derive_g2_authority(p, m, g2_request(), root=ROOT, now=NOW)["reason_code"])

    def test_valid_g4_receipt_is_exact_head_deterministic_and_contract_only(self):
        p = policy(); m = manifest(p); context = g4_context(m)
        first = derive_g4_receipt(p, m, context, root=ROOT, now=NOW)
        second = derive_g4_receipt(copy.deepcopy(p), copy.deepcopy(m), copy.deepcopy(context), root=ROOT, now=NOW)
        self.assertEqual("ALLOW", first["decision"])
        self.assertEqual("pre-prod", first["target_branch"])
        self.assertEqual("merge_approved_pr", first["authorized_action"])
        self.assertEqual("requires_trusted_repo_ci_projection", first["trust_state"])
        self.assertEqual(HEAD_SHA, first["approved_head_sha"])
        self.assertEqual(m["authority_receipt"]["approval_id"], first["parent_approval_id"])
        self.assertEqual(first["decision_digest"], second["decision_digest"])

    def test_main_target_is_denied(self):
        p = policy(); m = manifest(p); context = g4_context(m); context["target_branch"] = "main"
        self.assertEqual("AUTONOMOUS_MAIN_TARGET_FORBIDDEN", derive_g4_receipt(p, m, context, root=ROOT, now=NOW)["reason_code"])

    def test_receipt_head_drift_is_invalid(self):
        p = policy(); m = manifest(p); current = g4_context(m)
        receipt = derive_g4_receipt(p, m, current, root=ROOT, now=NOW)
        drifted = dict(current); drifted["approved_head_sha"] = "c" * 40
        self.assertIn("AUTONOMOUS_HEAD_DRIFT", validate_g4_receipt(receipt, p, m, drifted, root=ROOT, now=NOW)["reason_codes"])

    def test_receipt_body_graph_and_evidence_drift_are_invalid(self):
        p = policy(); m = manifest(p); current = g4_context(m)
        receipt = derive_g4_receipt(p, m, current, root=ROOT, now=NOW)
        drifted = dict(current)
        drifted["pr_body_digest"] = "sha256:" + "f" * 64
        drifted["run_graph_digest"] = "sha256:" + "0" * 64
        drifted["evidence_digest"] = "sha256:" + "1" * 64
        result = validate_g4_receipt(receipt, p, m, drifted, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_PR_BODY_DRIFT", result["reason_codes"])
        self.assertIn("AUTONOMOUS_GRAPH_DRIFT", result["reason_codes"])
        self.assertIn("AUTONOMOUS_EVIDENCE_DRIFT", result["reason_codes"])

    def test_parent_provenance_drift_invalidates_g4_receipt(self):
        p = policy(); m = manifest(p); current = g4_context(m)
        receipt = derive_g4_receipt(p, m, current, root=ROOT, now=NOW)
        receipt["parent_approval_id"] = "FORGED"
        result = validate_g4_receipt(receipt, p, m, current, root=ROOT, now=NOW)
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", result["reason_codes"])

    def test_r3_manifest_cannot_derive_g4(self):
        p = policy(); m = manifest(p); m["allowed_tasks"][0]["risk_class"] = "R3"
        from tools.node_architect.validate_autonomous_preprod_policy import manifest_approval_scope_digest, task_scope_hash
        m["allowed_tasks"][0]["scope_hash"] = task_scope_hash(m["allowed_tasks"][0])
        m["authority_receipt"]["manifest_scope_digest"] = manifest_approval_scope_digest(m)
        self.assertEqual("AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING", derive_g4_receipt(p, m, g4_context(m), root=ROOT, now=NOW)["reason_code"])


if __name__ == "__main__":
    unittest.main()
