from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone

from tools.node_architect.materialize_autonomous_g4_receipt import materialize_g4_receipt

REPO = "nhatnguyenquang1838-coder/gwc"
HEAD_SHA = "c" * 40
SCOPE_PREFIX = "10246501c24d699d"
POLICY_REVISION = "v1"


def _receipt(*, expires_in_min: int = 30, head: str = HEAD_SHA, prefix: str = SCOPE_PREFIX) -> dict:
    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(minutes=expires_in_min)
    iso = lambda d: d.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-g4-receipt",
        "decision": "ALLOW",
        "source": "autonomous_preprod_standing_policy",
        "trust_state": "requires_trusted_repo_ci_projection",
        "policy_id": "AUTONOMOUS_PREPROD_INTEGRATION_POLICY",
        "policy_revision": POLICY_REVISION,
        "policy_digest": "sha256:" + "0" * 64,
        "manifest_digest": "sha256:" + "0" * 64,
        "parent_approval_id": "APPROVE_G4_MERGE_SCRUM-275",
        "parent_scope_hash_prefix": prefix,
        "parent_authority_digest": "sha256:" + "0" * 64,
        "run_id": "run-1",
        "task_id": "SCRUM-275",
        "repository": REPO,
        "target_branch": "pre-prod",
        "approved_base_ref": "pre-prod",
        "approved_base_sha": "b" * 40,
        "working_branch": "auto/run-1/SCRUM-275",
        "pr_number": 42,
        "approved_head_sha": head,
        "task_scope_hash": "sha256:" + "1" * 64,
        "pr_body_digest": "sha256:" + "2" * 64,
        "managed_block_digest": "sha256:" + "3" * 64,
        "run_graph_digest": "sha256:" + "4" * 64,
        "gate_story_digest": "sha256:" + "5" * 64,
        "evidence_digest": "sha256:" + "6" * 64,
        "authorized_action": "merge_approved_pr",
        "expires_at": iso(expires),
        "decision_digest": "sha256:" + "9" * 64,
    }


class AutonomousG4ReceiptTests(unittest.TestCase):
    def test_valid_receipt(self):
        r = materialize_g4_receipt(
            receipt=_receipt(),
            expected_head_sha=HEAD_SHA,
            expected_scope_hash_prefix=SCOPE_PREFIX,
            expected_policy_revision=POLICY_REVISION,
        )
        self.assertEqual("RECEIPT_VALID", r["outcome"])
        self.assertFalse(r["merge_authority_granted"])

    def test_expired_receipt_rejected(self):
        r = materialize_g4_receipt(
            receipt=_receipt(expires_in_min=-5),
            expected_head_sha=HEAD_SHA,
            expected_scope_hash_prefix=SCOPE_PREFIX,
            expected_policy_revision=POLICY_REVISION,
        )
        self.assertEqual("REJECTED", r["outcome"])
        self.assertIn("AUTONOMOUS_G4_RECEIPT_EXPIRED", r["reason_codes"])

    def test_main_target_rejected(self):
        # The schema constrains target_branch to pre-prod; main hits schema-invalid
        # and is rejected fail-closed (no separate target code reachable).
        bad = _receipt()
        bad["target_branch"] = "main"
        r = materialize_g4_receipt(
            receipt=bad,
            expected_head_sha=HEAD_SHA,
            expected_scope_hash_prefix=SCOPE_PREFIX,
            expected_policy_revision=POLICY_REVISION,
        )
        self.assertEqual("REJECTED", r["outcome"])
        self.assertTrue(
            "AUTONOMOUS_G4_TARGET_NOT_PREPROD" in r["reason_codes"]
            or "AUTONOMOUS_G4_RECEIPT_SCHEMA_INVALID" in r["reason_codes"]
        )

    def test_head_drift_rejected(self):
        r = materialize_g4_receipt(
            receipt=_receipt(head="d" * 40),
            expected_head_sha=HEAD_SHA,
            expected_scope_hash_prefix=SCOPE_PREFIX,
            expected_policy_revision=POLICY_REVISION,
        )
        self.assertEqual("REJECTED", r["outcome"])
        self.assertIn("AUTONOMOUS_G4_HEAD_DRIFT", r["reason_codes"])

    def test_scope_prefix_mismatch_rejected(self):
        r = materialize_g4_receipt(
            receipt=_receipt(prefix="ffffffffffffffff"),
            expected_head_sha=HEAD_SHA,
            expected_scope_hash_prefix=SCOPE_PREFIX,
            expected_policy_revision=POLICY_REVISION,
        )
        self.assertEqual("REJECTED", r["outcome"])
        self.assertIn("AUTONOMOUS_G4_SCOPE_PREFIX_MISMATCH", r["reason_codes"])

    def test_not_allow_rejected(self):
        # The schema constrains decision to ALLOW; any other value is schema-invalid
        # and therefore rejected fail-closed (no separate decision code reachable).
        bad = _receipt()
        bad["decision"] = "DENY"
        r = materialize_g4_receipt(
            receipt=bad,
            expected_head_sha=HEAD_SHA,
            expected_scope_hash_prefix=SCOPE_PREFIX,
            expected_policy_revision=POLICY_REVISION,
        )
        self.assertEqual("REJECTED", r["outcome"])
        self.assertTrue(
            "AUTONOMOUS_G4_RECEIPT_SCHEMA_INVALID" in r["reason_codes"]
            or "AUTONOMOUS_G4_DECISION_NOT_ALLOW" in r["reason_codes"]
        )


if __name__ == "__main__":
    unittest.main()
