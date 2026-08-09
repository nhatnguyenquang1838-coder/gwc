from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from tools.node_architect.materialize_autonomous_preprod_run_authority import (
    canonical_digest,
    validate_parent_run_authority,
)


def iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class AutonomousPreprodRunAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 9, 13, 30, tzinfo=timezone.utc)
        self.manifest = {
            "schema_version": "1.0",
            "artifact_type": "autonomous-preprod-run-manifest",
            "run_id": "na81-scrum-288-20260809",
            "repository": "nhatnguyenquang1838-coder/gwc",
            "policy_id": "AUTONOMOUS_PREPROD_INTEGRATION_POLICY",
            "policy_revision": "v1",
            "policy_digest": "sha256:" + "1" * 64,
            "approved_base_ref": "pre-prod",
            "approved_base_sha": "e4ebb448647e314a9bd48eac18460c1d408d1e68",
            "target_branch": "pre-prod",
            "immutable_authority_paths": [
                ".github/workflows/autonomous-preprod-runtime.yml",
                ".github/workflows/g4-g5-evidence.yml",
                "tools/node_architect/materialize_autonomous_preprod_run_authority.py",
            ],
            "allowed_tasks": [{
                "task_id": "SCRUM-302",
                "risk_class": "R2",
                "working_branch": "auto/SCRUM-302-risk-classification-20260809",
                "authorized_paths": ["tools/node_architect/risk_classification.py"],
                "authorized_g2_actions": ["modify_approved_files", "push_working_branch"],
                "scope_hash": "sha256:" + "2" * 64,
            }],
            "issued_at": iso(self.now - timedelta(minutes=5)),
            "expires_at": iso(self.now + timedelta(hours=6)),
            "idempotency_key": "na81-scrum-288-20260809-v1",
            "authority_receipt": {},
        }
        scope = deepcopy(self.manifest)
        scope.pop("authority_receipt")
        scope_digest = canonical_digest(scope)
        self.receipt = {
            "status": "present",
            "source": "github_actions_bot_comment",
            "bot_login": "github-actions[bot]",
            "marker": "gwc:autonomous-preprod-run-authority-receipt",
            "approval_id": "CP-NA81-001",
            "receipt_comment_id": 200,
            "source_comment_id": 199,
            "approved_run_id": self.manifest["run_id"],
            "approved_policy_id": self.manifest["policy_id"],
            "approved_policy_revision": self.manifest["policy_revision"],
            "approved_policy_digest": self.manifest["policy_digest"],
            "manifest_scope_digest": scope_digest,
            "scope_hash_prefix": scope_digest.removeprefix("sha256:")[:16],
            "issued_at": iso(self.now - timedelta(minutes=4)),
            "expires_at": iso(self.now + timedelta(hours=6)),
        }
        self.manifest["authority_receipt"] = deepcopy(self.receipt)

    def check(self, **overrides):
        args = dict(
            manifest=self.manifest,
            receipt=self.receipt,
            observed_comment_login="github-actions[bot]",
            expected_repository="nhatnguyenquang1838-coder/gwc",
            expected_task_id="SCRUM-302",
            expected_base_sha="e4ebb448647e314a9bd48eac18460c1d408d1e68",
            now=self.now,
        )
        args.update(overrides)
        return validate_parent_run_authority(**args)

    def test_valid_trusted_receipt_yields_authorized_ready(self):
        result = self.check()
        self.assertEqual("PASS", result["outcome"])
        self.assertEqual("AUTHORIZED_READY", result["state"])
        self.assertTrue(result["standing_g4_valid"])

    def test_route_marker_without_receipt_fails_closed(self):
        result = self.check(receipt=None)
        self.assertEqual("READY_FOR_AUTHORITY", result["state"])
        self.assertFalse(result["standing_g4_valid"])

    def test_wrong_comment_actor_is_untrusted(self):
        result = self.check(observed_comment_login="local-agent")
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", result["reason_codes"])

    def test_task_must_be_allowlisted(self):
        result = self.check(expected_task_id="SCRUM-303")
        self.assertIn("AUTONOMOUS_TASK_NOT_ALLOWLISTED", result["reason_codes"])

    def test_scope_digest_drift_is_rejected(self):
        receipt = deepcopy(self.receipt)
        receipt["manifest_scope_digest"] = "sha256:" + "f" * 64
        result = self.check(receipt=receipt)
        self.assertIn("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED", result["reason_codes"])

    def test_expired_receipt_is_rejected(self):
        receipt = deepcopy(self.receipt)
        receipt["expires_at"] = iso(self.now - timedelta(seconds=1))
        result = self.check(receipt=receipt)
        self.assertIn("AUTONOMOUS_RUN_MANIFEST_EXPIRED", result["reason_codes"])

    def test_base_drift_is_rejected(self):
        result = self.check(expected_base_sha="0" * 40)
        self.assertIn("AUTONOMOUS_BASE_SHA_MISMATCH", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
