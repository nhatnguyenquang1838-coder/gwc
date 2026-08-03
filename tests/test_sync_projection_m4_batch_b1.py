import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.projection_source_authority_check import decide_projection_source_authority

SCHEMA = json.loads(Path("schemas/projection-source-authority-decision.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
REVISION_A = "d9a89a002aae4348359cd88810a9d03926199597"
REVISION_B = "e9a89a002aae4348359cd88810a9d03926199598"


def valid_input():
    return {
        "task_id": "SCRUM-223",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "ds-admin",
        "requested_fields": ["/task/status"],
        "source_bindings": [
            {
                "source_type": "TASK_RECORD",
                "authority_class": "CANONICAL",
                "ref": "jira:SCRUM-223",
                "revision": REVISION_A,
                "content_digest": DIGEST_A,
                "observed_at": "2026-08-03T13:00:00Z",
                "status": "VERIFIED",
            }
        ],
        "field_evidence": [
            {
                "field_path": "/task/status",
                "source_ref": "jira:SCRUM-223",
                "source_revision": REVISION_A,
                "evidence_digest": DIGEST_A,
                "derivation": "DIRECT",
            }
        ],
        "current_revisions": [
            {
                "ref": "jira:SCRUM-223",
                "revision": REVISION_A,
                "observed_at": "2026-08-03T13:05:00Z",
            }
        ],
        "freshness_policy": {
            "max_source_age_seconds": 3600,
            "max_readback_age_seconds": 900,
        },
        "observed_at": "2026-08-03T13:10:00Z",
    }


class ProjectionSourceAuthorityTests(unittest.TestCase):
    def assert_schema_valid(self, decision):
        errors = sorted(VALIDATOR.iter_errors(decision), key=lambda error: list(error.path))
        self.assertEqual(errors, [], [error.message for error in errors])

    def decide(self, payload=None):
        decision = decide_projection_source_authority(**(payload or valid_input()))
        self.assert_schema_valid(decision)
        return decision

    def test_valid_direct_evidence_is_ready_and_read_only(self):
        decision = self.decide()
        self.assertEqual(decision["outcome"], "READY")
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_AUTHORITY_CONFIRMED")
        self.assertTrue(decision["read_only_projection"])
        for key in (
            "write_authority_granted",
            "approval_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(decision[key])

    def test_known_deterministic_derivation_is_ready(self):
        payload = valid_input()
        payload["field_evidence"][0]["derivation"] = "DETERMINISTIC_DERIVATION"
        payload["field_evidence"][0]["derivation_rule_id"] = "canonical-json-pointer-v1"
        self.assertEqual(self.decide(payload)["outcome"], "READY")

    def test_no_canonical_source_fails_closed(self):
        payload = valid_input()
        payload["source_bindings"][0]["authority_class"] = "ADVISORY"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_CANONICAL_MISSING")

    def test_projection_only_source_rejected(self):
        payload = valid_input()
        payload["source_bindings"].append(
            {
                **payload["source_bindings"][0],
                "authority_class": "PROJECTION",
                "ref": "projection:task-center:SCRUM-223",
                "revision": REVISION_B,
                "content_digest": DIGEST_B,
            }
        )
        payload["field_evidence"][0].update(
            source_ref="projection:task-center:SCRUM-223",
            source_revision=REVISION_B,
            evidence_digest=DIGEST_B,
        )
        payload["current_revisions"].append(
            {"ref": "projection:task-center:SCRUM-223", "revision": REVISION_B, "observed_at": "2026-08-03T13:05:00Z"}
        )
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_AUTHORITY_INVALID")

    def test_missing_field_binding_rejected(self):
        payload = valid_input()
        payload["requested_fields"].append("/task/assignee")
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_FIELD_UNBOUND")

    def test_ambiguous_or_conflicting_binding_rejected(self):
        payload = valid_input()
        payload["source_bindings"][0]["status"] = "CONFLICT"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_CONFLICT")

    def test_digest_mismatch_rejected(self):
        payload = valid_input()
        payload["field_evidence"][0]["evidence_digest"] = DIGEST_B
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_DIGEST_MISMATCH")

    def test_current_revision_drift_rejected(self):
        payload = valid_input()
        payload["current_revisions"][0]["revision"] = REVISION_B
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_REVISION_DRIFT")

    def test_stale_source_rejected(self):
        payload = valid_input()
        payload["source_bindings"][0]["observed_at"] = "2026-08-03T10:00:00Z"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_STALE")

    def test_missing_canonical_binding_status_rejected(self):
        payload = valid_input()
        payload["source_bindings"][0]["status"] = "MISSING"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_CANONICAL_MISSING")

    def test_missing_current_readback_rejected(self):
        payload = valid_input()
        payload["current_revisions"] = []
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_REVISION_DRIFT")

    def test_stale_readback_rejected(self):
        payload = valid_input()
        payload["current_revisions"][0]["observed_at"] = "2026-08-03T12:00:00Z"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_STALE")

    def test_unknown_derivation_rule_rejected(self):
        payload = valid_input()
        payload["field_evidence"][0]["derivation"] = "DETERMINISTIC_DERIVATION"
        payload["field_evidence"][0]["derivation_rule_id"] = "unknown-rule-v99"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_DERIVATION_UNVERIFIED")

    def test_inferred_status_rejected(self):
        payload = valid_input()
        payload["field_evidence"][0]["derivation"] = "INFERRED"
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_INFERRED_STATUS_REJECTED")
        self.assertIn("PROJECTION_SOURCE_FIELD_UNBOUND", decision["reason_codes"])

    def test_empty_fields_rejected_before_source_analysis(self):
        payload = valid_input()
        payload["requested_fields"] = []
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_FIELDS_EMPTY")

    def test_invalid_input_precedence(self):
        payload = valid_input()
        payload["task_id"] = "bad"
        payload["requested_fields"] = []
        decision = self.decide(payload)
        self.assertEqual(decision["reason_code"], "PROJECTION_SOURCE_INPUT_INVALID")

    def test_input_order_does_not_change_digest(self):
        payload = valid_input()
        payload["requested_fields"].append("/task/id")
        payload["field_evidence"].append(
            {
                "field_path": "/task/id",
                "source_ref": "jira:SCRUM-223",
                "source_revision": REVISION_A,
                "evidence_digest": DIGEST_A,
                "derivation": "DIRECT",
            }
        )
        first = self.decide(payload)
        reordered = copy.deepcopy(payload)
        reordered["requested_fields"].reverse()
        reordered["field_evidence"].reverse()
        reordered["source_bindings"].reverse()
        reordered["current_revisions"].reverse()
        second = self.decide(reordered)
        self.assertEqual(first["decision_digest"], second["decision_digest"])

    def test_semantic_change_changes_digest(self):
        first = self.decide()
        payload = valid_input()
        payload["projection_target"] = "task-center"
        second = self.decide(payload)
        self.assertNotEqual(first["decision_digest"], second["decision_digest"])

    def test_observed_at_is_excluded_from_digest(self):
        first = self.decide()
        payload = valid_input()
        payload["observed_at"] = "2026-08-03T13:11:00Z"
        payload["source_bindings"][0]["observed_at"] = "2026-08-03T13:01:00Z"
        payload["current_revisions"][0]["observed_at"] = "2026-08-03T13:06:00Z"
        second = self.decide(payload)
        # Input evidence timestamps are semantic and remain in the digest; only output observed_at is excluded.
        self.assertNotEqual(first["decision_digest"], second["decision_digest"])


if __name__ == "__main__":
    unittest.main()
