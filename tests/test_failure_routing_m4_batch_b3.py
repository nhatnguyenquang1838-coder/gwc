import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.projection_failure_routing import route_projection_failure

SCHEMA = json.loads(Path("schemas/projection-failure-routing.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
REVISION_A = "d9a89a002aae4348359cd88810a9d03926199597"


def _authority_digest(decision):
    semantic = {k: v for k, v in decision.items() if k not in {"reason_codes", "decision_digest"}}
    payload = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def valid_source_authority():
    decision = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": "SCRUM-226",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "source_bindings": [
            {"source_type": "TASK_RECORD", "authority_class": "CANONICAL", "ref": "jira:SCRUM-226",
             "revision": REVISION_A, "content_digest": DIGEST_A, "observed_at": "2026-08-07T13:00:00Z", "status": "VERIFIED"},
        ],
        "field_authority": [
            {"field_path": "/task/status", "source_ref": "jira:SCRUM-226", "source_revision": REVISION_A,
             "evidence_digest": DIGEST_A, "derivation": "DIRECT"},
        ],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": "2026-08-07T13:05:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    decision["decision_digest"] = _authority_digest(decision)
    return decision


def valid_linkset():
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-evidence-linkset",
        "task_id": "SCRUM-226",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "source_authority_digest": DIGEST_A,
        "links": [
            {"evidence_id": "task-226", "source_type": "TASK_RECORD", "ref": "jira:SCRUM-226",
             "revision": REVISION_A, "content_digest": DIGEST_A, "relation": "SUPPORTS_FIELD",
             "field_paths": ["/task/status"], "verification_status": "VERIFIED"},
        ],
        "covered_fields": ["/task/status"],
        "uncovered_fields": [],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_EVIDENCE_LINKSET_CONFIRMED",
        "reason_codes": ["PROJECTION_EVIDENCE_LINKSET_CONFIRMED"],
        "observed_at": "2026-08-07T13:06:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": DIGEST_B,
    }


def valid_privacy():
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-privacy-decision",
        "task_id": "SCRUM-226",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "evidence_linkset_digest": DIGEST_B,
        "rejected_classes": ["SECRET", "CREDENTIAL", "TOKEN", "PRIVATE_KEY", "PRODUCTION_DATA", "HIDDEN_REASONING"],
        "redacted_fields": [],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_PRIVACY_BOUNDARY_CONFIRMED",
        "reason_codes": ["PROJECTION_PRIVACY_BOUNDARY_CONFIRMED"],
        "observed_at": "2026-08-07T13:07:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": DIGEST_C,
    }


def valid_drift(drift_detected=False):
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-drift-decision",
        "task_id": "SCRUM-226",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "outcome": "READY" if not drift_detected else "BLOCKED",
        "authority_status": "CONFIRMED" if not drift_detected else "REJECTED",
        "reason_code": "PROJECTION_DRIFT_NONE" if not drift_detected else "DRIFT_DETECTED",
        "reason_codes": ["PROJECTION_DRIFT_NONE"] if not drift_detected else ["DRIFT_DETECTED"],
        "drift_detected": drift_detected,
        "drift_field_count": 1 if drift_detected else 0,
        "drift_fields": ["status"] if drift_detected else [],
        "canonical_state_digest": "sha256:" + "0" * 64,
        "observed_at": "2026-08-07T14:00:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": DIGEST_C,
    }


def valid_reconcile(current=True):
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-reconcile-readback",
        "task_id": "SCRUM-226",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_CURRENT" if current else "RECONCILE_READBACK_DIVERGENCE",
        "reason_codes": ["PROJECTION_CURRENT"] if current else ["RECONCILE_READBACK_DIVERGENCE"],
        "current": current,
        "divergence_fields": [] if current else ["status"],
        "canonical_state_digest": "sha256:" + "0" * 64,
        "observed_at": "2026-08-07T14:05:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": DIGEST_C,
    }


def valid_envelope():
    return {
        "schema_version": "1.0",
        "artifact_type": "sync-projection-envelope",
        "task_id": "SCRUM-226",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "source_authority_digest": valid_source_authority()["decision_digest"],
        "evidence_linkset_digest": DIGEST_B,
        "privacy_boundary_digest": DIGEST_C,
        "canonical_state": {"status": "Done", "assignee": "hermes"},
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


class FailureRoutingTests(unittest.TestCase):
    def test_retryable(self):
        decision = route_projection_failure(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(drift_detected=True), reconcile_decision=valid_reconcile(current=False),
        )
        self.assertEqual(decision["outcome"], "READY")
        self.assertEqual(decision["routing_verdict"], "RETRYABLE")
        self.assertEqual(decision["reason_code"], "ROUTE_RETRYABLE")
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])

    def test_hard_denied(self):
        decision = route_projection_failure(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(drift_detected=False), reconcile_decision=valid_reconcile(current=True),
        )
        self.assertEqual(decision["routing_verdict"], "HARD_DENIED")
        self.assertEqual(decision["reason_code"], "ROUTE_HARD_DENIED")

    def test_stale_evidence(self):
        decision = route_projection_failure(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(drift_detected=False), reconcile_decision=valid_reconcile(current=False),
        )
        self.assertEqual(decision["routing_verdict"], "STALE_EVIDENCE")
        self.assertEqual(decision["reason_code"], "ROUTE_STALE_EVIDENCE")

    def test_authority_conflict(self):
        decision = route_projection_failure(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(drift_detected=True), reconcile_decision=valid_reconcile(current=True),
        )
        self.assertEqual(decision["routing_verdict"], "AUTHORITY_CONFLICT")
        self.assertEqual(decision["reason_code"], "ROUTE_AUTHORITY_CONFLICT")

    def test_missing_source_authority_blocked(self):
        bad = valid_source_authority()
        bad["outcome"] = "BLOCKED"
        decision = route_projection_failure(
            envelope=valid_envelope(), source_authority_decision=bad,
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), reconcile_decision=valid_reconcile(),
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("ROUTE_SOURCE_AUTHORITY_BLOCKED", decision["reason_codes"])

    def test_missing_drift_decision_blocked(self):
        decision = route_projection_failure(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision={"artifact_type": "wrong"}, reconcile_decision=valid_reconcile(),
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("ROUTE_DRIFT_DECISION_BLOCKED", decision["reason_codes"])

    def test_missing_reconcile_decision_blocked(self):
        decision = route_projection_failure(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), reconcile_decision={"artifact_type": "wrong"},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("ROUTE_RECONCILE_DECISION_BLOCKED", decision["reason_codes"])

    def test_invalid_envelope_blocked(self):
        decision = route_projection_failure(
            envelope={"artifact_type": "wrong"}, source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), reconcile_decision=valid_reconcile(),
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("ROUTE_INPUT_INVALID", decision["reason_codes"])

    def test_no_authority_granted(self):
        decision = route_projection_failure(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(drift_detected=True), reconcile_decision=valid_reconcile(current=False),
        )
        for field in ["write_authority_granted", "approval_authority_granted",
                      "merge_authority_granted", "deployment_authority_granted",
                      "production_authority_granted"]:
            self.assertEqual(decision[field], False, field)
        self.assertEqual(decision["read_only_projection"], True)


if __name__ == "__main__":
    unittest.main()
