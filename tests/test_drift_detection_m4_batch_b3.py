import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.projection_drift_detection import detect_projection_drift

SCHEMA = json.loads(Path("schemas/projection-drift-decision.schema.json").read_text(encoding="utf-8"))
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
        "task_id": "SCRUM-224",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "drift-detection",
        "source_bindings": [
            {"source_type": "TASK_RECORD", "authority_class": "CANONICAL", "ref": "jira:SCRUM-224",
             "revision": REVISION_A, "content_digest": DIGEST_A, "observed_at": "2026-08-07T13:00:00Z", "status": "VERIFIED"},
        ],
        "field_authority": [
            {"field_path": "/task/status", "source_ref": "jira:SCRUM-224", "source_revision": REVISION_A,
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
        "task_id": "SCRUM-224",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "drift-detection",
        "source_authority_digest": DIGEST_A,
        "links": [
            {"evidence_id": "task-224", "source_type": "TASK_RECORD", "ref": "jira:SCRUM-224",
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
        "task_id": "SCRUM-224",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "drift-detection",
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


def valid_envelope():
    return {
        "schema_version": "1.0",
        "artifact_type": "sync-projection-envelope",
        "task_id": "SCRUM-224",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "drift-detection",
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


def valid_canonical_state():
    return {"status": "Done", "assignee": "hermes"}


def valid_projection():
    return {"canonical_state": {"status": "Done", "assignee": "hermes"}}


class DriftDetectionTests(unittest.TestCase):
    def test_no_drift_ready(self):
        decision = detect_projection_drift(
            envelope=valid_envelope(),
            source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(),
            privacy_boundary_decision=valid_privacy(),
            projection=valid_projection(),
            canonical_state=valid_canonical_state(),
        )
        self.assertEqual(decision["outcome"], "READY")
        self.assertEqual(decision["drift_detected"], False)
        self.assertEqual(decision["drift_field_count"], 0)
        self.assertEqual(decision["drift_fields"], [])
        self.assertEqual(decision["reason_code"], "PROJECTION_DRIFT_NONE")
        self.assertEqual(decision["read_only_projection"], True)
        self.assertEqual(decision["write_authority_granted"], False)
        self.assertEqual(decision["merge_authority_granted"], False)
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])

    def test_drift_detected_blocked(self):
        canonical = {"status": "Done", "assignee": "hermes"}
        projection = {"canonical_state": {"status": "In Progress", "assignee": "hermes"}}
        decision = detect_projection_drift(
            envelope=valid_envelope(),
            source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(),
            privacy_boundary_decision=valid_privacy(),
            projection=projection,
            canonical_state=canonical,
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertEqual(decision["drift_detected"], True)
        self.assertIn("status", decision["drift_fields"])
        self.assertIn("DRIFT_DETECTED", decision["reason_codes"])
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])

    def test_missing_source_authority_blocked(self):
        bad = valid_source_authority()
        bad["outcome"] = "BLOCKED"
        decision = detect_projection_drift(
            envelope=valid_envelope(),
            source_authority_decision=bad,
            evidence_linkset=valid_linkset(),
            privacy_boundary_decision=valid_privacy(),
            projection=valid_projection(),
            canonical_state=valid_canonical_state(),
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("DRIFT_SOURCE_AUTHORITY_BLOCKED", decision["reason_codes"])

    def test_missing_evidence_linkset_blocked(self):
        bad = valid_linkset()
        bad["outcome"] = "BLOCKED"
        decision = detect_projection_drift(
            envelope=valid_envelope(),
            source_authority_decision=valid_source_authority(),
            evidence_linkset=bad,
            privacy_boundary_decision=valid_privacy(),
            projection=valid_projection(),
            canonical_state=valid_canonical_state(),
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("DRIFT_EVIDENCE_LINKSET_BLOCKED", decision["reason_codes"])

    def test_missing_privacy_blocked(self):
        bad = valid_privacy()
        bad["outcome"] = "BLOCKED"
        decision = detect_projection_drift(
            envelope=valid_envelope(),
            source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(),
            privacy_boundary_decision=bad,
            projection=valid_projection(),
            canonical_state=valid_canonical_state(),
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("DRIFT_PRIVACY_BOUNDARY_BLOCKED", decision["reason_codes"])

    def test_b1_digest_mismatch_blocked(self):
        envelope = valid_envelope()
        envelope["source_authority_digest"] = DIGEST_B  # mismatch with source decision digest
        decision = detect_projection_drift(
            envelope=envelope,
            source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(),
            privacy_boundary_decision=valid_privacy(),
            projection=valid_projection(),
            canonical_state=valid_canonical_state(),
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("DRIFT_B1_DIGEST_MISMATCH", decision["reason_codes"])

    def test_invalid_envelope_blocked(self):
        decision = detect_projection_drift(
            envelope={"artifact_type": "wrong"},
            source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(),
            privacy_boundary_decision=valid_privacy(),
            projection=valid_projection(),
            canonical_state=valid_canonical_state(),
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("DRIFT_INPUT_INVALID", decision["reason_codes"])

    def test_projection_state_missing_blocked(self):
        decision = detect_projection_drift(
            envelope=valid_envelope(),
            source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(),
            privacy_boundary_decision=valid_privacy(),
            projection={},
            canonical_state=valid_canonical_state(),
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("DRIFT_PROJECTION_STATE_MISSING", decision["reason_codes"])

    def test_digest_order_independent(self):
        canonical_a = {"status": "Done", "assignee": "hermes"}
        canonical_b = {"assignee": "hermes", "status": "Done"}
        d1 = detect_projection_drift(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            projection=valid_projection(), canonical_state=canonical_a,
        )["canonical_state_digest"]
        d2 = detect_projection_drift(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            projection=valid_projection(), canonical_state=canonical_b,
        )["canonical_state_digest"]
        self.assertEqual(d1, d2)
        self.assertTrue(d1.startswith("sha256:"))

    def test_extra_projection_field_is_drift(self):
        canonical = {"status": "Done", "assignee": "hermes"}
        projection = {"canonical_state": {"status": "Done", "assignee": "hermes", "extra": "x"}}
        decision = detect_projection_drift(
            envelope=valid_envelope(),
            source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(),
            privacy_boundary_decision=valid_privacy(),
            projection=projection,
            canonical_state=canonical,
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("extra", decision["drift_fields"])

    def test_no_authority_granted(self):
        decision = detect_projection_drift(
            envelope=valid_envelope(),
            source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(),
            privacy_boundary_decision=valid_privacy(),
            projection=valid_projection(),
            canonical_state=valid_canonical_state(),
        )
        for field in ["write_authority_granted", "approval_authority_granted",
                      "merge_authority_granted", "deployment_authority_granted",
                      "production_authority_granted"]:
            self.assertEqual(decision[field], False, field)
        self.assertEqual(decision["read_only_projection"], True)


if __name__ == "__main__":
    unittest.main()
