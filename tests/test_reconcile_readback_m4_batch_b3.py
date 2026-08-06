import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.projection_reconcile_readback import reconcile_projection_readback

SCHEMA = json.loads(Path("schemas/projection-reconcile-readback.schema.json").read_text(encoding="utf-8"))
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
        "task_id": "SCRUM-225",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
        "source_bindings": [
            {"source_type": "TASK_RECORD", "authority_class": "CANONICAL", "ref": "jira:SCRUM-225",
             "revision": REVISION_A, "content_digest": DIGEST_A, "observed_at": "2026-08-07T13:00:00Z", "status": "VERIFIED"},
        ],
        "field_authority": [
            {"field_path": "/task/status", "source_ref": "jira:SCRUM-225", "source_revision": REVISION_A,
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
        "task_id": "SCRUM-225",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
        "source_authority_digest": DIGEST_A,
        "links": [
            {"evidence_id": "task-225", "source_type": "TASK_RECORD", "ref": "jira:SCRUM-225",
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
        "task_id": "SCRUM-225",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
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


def valid_drift():
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-drift-decision",
        "task_id": "SCRUM-225",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_DRIFT_NONE",
        "reason_codes": ["PROJECTION_DRIFT_NONE"],
        "drift_detected": False,
        "drift_field_count": 0,
        "drift_fields": [],
        "canonical_state_digest": _authority_digest({"outcome": "READY", "drift_detected": False}),
        "observed_at": "2026-08-07T14:00:00Z",
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
        "task_id": "SCRUM-225",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
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


class ReconcileReadbackTests(unittest.TestCase):
    def test_no_divergence_current(self):
        prior = {"canonical_state": {"status": "Done", "assignee": "hermes"}}
        proj = {"canonical_state": {"status": "Done", "assignee": "hermes"}}
        decision = reconcile_projection_readback(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), projection=proj, prior_readback=prior,
        )
        self.assertEqual(decision["outcome"], "READY")
        self.assertEqual(decision["current"], True)
        self.assertEqual(decision["reason_code"], "PROJECTION_CURRENT")
        self.assertEqual(decision["divergence_fields"], [])
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])

    def test_divergence_blocked(self):
        prior = {"canonical_state": {"status": "Done", "assignee": "hermes"}}
        proj = {"canonical_state": {"status": "In Progress", "assignee": "hermes"}}
        decision = reconcile_projection_readback(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), projection=proj, prior_readback=prior,
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertEqual(decision["current"], False)
        self.assertIn("status", decision["divergence_fields"])
        self.assertIn("RECONCILE_READBACK_DIVERGENCE", decision["reason_codes"])
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])

    def test_drift_detected_blocked(self):
        drift = valid_drift()
        drift["drift_detected"] = True
        drift["outcome"] = "BLOCKED"
        drift["reason_codes"] = ["DRIFT_DETECTED"]
        decision = reconcile_projection_readback(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=drift, projection={"canonical_state": {"status": "Done"}},
            prior_readback={"canonical_state": {"status": "Done"}},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("RECONCILE_DRIFT_DECISION_BLOCKED", decision["reason_codes"])

    def test_missing_source_authority_blocked(self):
        bad = valid_source_authority()
        bad["outcome"] = "BLOCKED"
        decision = reconcile_projection_readback(
            envelope=valid_envelope(), source_authority_decision=bad,
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), projection={"canonical_state": {}},
            prior_readback={"canonical_state": {}},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("RECONCILE_SOURCE_AUTHORITY_BLOCKED", decision["reason_codes"])

    def test_missing_drift_decision_blocked(self):
        decision = reconcile_projection_readback(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision={"artifact_type": "wrong"},
            projection={"canonical_state": {}}, prior_readback={"canonical_state": {}},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("RECONCILE_DRIFT_DECISION_BLOCKED", decision["reason_codes"])

    def test_prior_state_missing_blocked(self):
        decision = reconcile_projection_readback(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), projection={"canonical_state": {}},
            prior_readback={},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("RECONCILE_PRIOR_STATE_MISSING", decision["reason_codes"])

    def test_invalid_envelope_blocked(self):
        decision = reconcile_projection_readback(
            envelope={"artifact_type": "wrong"}, source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), projection={"canonical_state": {}},
            prior_readback={"canonical_state": {}},
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("RECONCILE_INPUT_INVALID", decision["reason_codes"])

    def test_digest_order_independent(self):
        prior_a = {"canonical_state": {"status": "Done", "assignee": "hermes"}}
        prior_b = {"canonical_state": {"assignee": "hermes", "status": "Done"}}
        proj = {"canonical_state": {"status": "Done", "assignee": "hermes"}}
        d1 = reconcile_projection_readback(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), projection=proj, prior_readback=prior_a,
        )["decision_digest"]
        d2 = reconcile_projection_readback(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), projection=proj, prior_readback=prior_b,
        )["decision_digest"]
        self.assertEqual(d1, d2)
        self.assertTrue(d1.startswith("sha256:"))

    def test_no_authority_granted(self):
        decision = reconcile_projection_readback(
            envelope=valid_envelope(), source_authority_decision=valid_source_authority(),
            evidence_linkset=valid_linkset(), privacy_boundary_decision=valid_privacy(),
            drift_decision=valid_drift(), projection={"canonical_state": {"status": "Done"}},
            prior_readback={"canonical_state": {"status": "Done"}},
        )
        for field in ["write_authority_granted", "approval_authority_granted",
                      "merge_authority_granted", "deployment_authority_granted",
                      "production_authority_granted"]:
            self.assertEqual(decision[field], False, field)
        self.assertEqual(decision["read_only_projection"], True)


if __name__ == "__main__":
    unittest.main()
