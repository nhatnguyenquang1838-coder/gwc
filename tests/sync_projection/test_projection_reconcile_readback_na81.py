#!/usr/bin/env python3
"""NA81 readback-contract tests for projection_reconcile_readback (SCRUM-348).

Verify the CONFIRMED / PENDING / CONFLICT / UNAVAILABLE taxonomy, the
source-revision + idempotency-identity binding, and the rule that unknown
outcome is never inferred success.
"""

from __future__ import annotations

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
REVISION = "d9a89a002aae4348359cd88810a9d03926199597"


def _decision_digest(d):
    payload = {k: v for k, v in d.items() if k not in ("reason_codes", "decision_digest")}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _source_authority():
    d = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": "SCRUM-348",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
        "source_bindings": [{
            "source_type": "TASK_RECORD", "authority_class": "CANONICAL", "ref": "jira:SCRUM-348",
            "revision": REVISION, "content_digest": DIGEST_A, "observed_at": "2026-08-12T06:00:00Z", "status": "VERIFIED"
        }],
        "field_authority": [{
            "field_path": "/task/status", "source_ref": "jira:SCRUM-348", "source_revision": REVISION,
            "evidence_digest": DIGEST_A, "derivation": "DIRECT"
        }],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": "2026-08-12T06:00:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    d["decision_digest"] = _decision_digest(d)
    return d


def _linkset():
    d = {
        "schema_version": "1.0",
        "artifact_type": "projection-evidence-linkset",
        "task_id": "SCRUM-348",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
        "source_authority_digest": DIGEST_A,
        "links": [{
            "evidence_id": "task-348", "source_type": "TASK_RECORD", "ref": "jira:SCRUM-348",
            "revision": REVISION, "content_digest": DIGEST_A, "relation": "SUPPORTS_FIELD",
            "field_paths": ["/task/status"], "verification_status": "VERIFIED"
        }],
        "covered_fields": ["/task/status"],
        "uncovered_fields": [],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_EVIDENCE_LINKSET_CONFIRMED",
        "reason_codes": ["PROJECTION_EVIDENCE_LINKSET_CONFIRMED"],
        "observed_at": "2026-08-12T06:01:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": DIGEST_B,
    }
    return d


def _privacy():
    d = {
        "schema_version": "1.0",
        "artifact_type": "projection-privacy-decision",
        "task_id": "SCRUM-348",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
        "evidence_linkset_digest": DIGEST_B,
        "rejected_classes": ["SECRET", "CREDENTIAL", "TOKEN", "PRIVATE_KEY", "PRODUCTION_DATA", "HIDDEN_REASONING"],
        "redacted_fields": [],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_PRIVACY_BOUNDARY_CONFIRMED",
        "reason_codes": ["PROJECTION_PRIVACY_BOUNDARY_CONFIRMED"],
        "observed_at": "2026-08-12T06:02:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": DIGEST_C,
    }
    return d


def _drift():
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-drift-decision",
        "task_id": "SCRUM-348",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_DRIFT_NONE",
        "reason_codes": ["PROJECTION_DRIFT_NONE"],
        "drift_detected": False,
        "drift_field_count": 0,
        "drift_fields": [],
        "canonical_state_digest": _decision_digest({"outcome": "READY", "drift_detected": False}),
        "observed_at": "2026-08-12T06:03:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": DIGEST_C,
    }


def _envelope():
    return {
        "schema_version": "1.0",
        "artifact_type": "sync-projection-envelope",
        "task_id": "SCRUM-348",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "reconcile-readback",
        "source_authority_digest": _source_authority()["decision_digest"],
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


class TestNA81ReadbackContract(unittest.TestCase):
    def test_confirmed_when_states_match(self):
        decision = reconcile_projection_readback(
            envelope=_envelope(),
            source_authority_decision=_source_authority(),
            evidence_linkset=_linkset(),
            privacy_boundary_decision=_privacy(),
            drift_decision=_drift(),
            projection={"canonical_state": {"status": "Done", "assignee": "hermes"}},
            prior_readback={"canonical_state": {"status": "Done", "assignee": "hermes"}},
            source_revision=REVISION,
            idempotency_identity={"task_id": "SCRUM-348", "idempotency_key": "k1"},
        )
        self.assertEqual(decision["outcome"], "CONFIRMED")
        self.assertTrue(decision["current"])
        self.assertEqual(decision["reason_code"], "PROJECTION_READBACK_CONFIRMED")
        self.assertEqual(decision["divergence_fields"], [])
        self.assertEqual(decision["source_revision"], REVISION)
        self.assertEqual(decision["idempotency_identity"]["task_id"], "SCRUM-348")
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])

    def test_conflict_when_states_diverge(self):
        decision = reconcile_projection_readback(
            envelope=_envelope(),
            source_authority_decision=_source_authority(),
            evidence_linkset=_linkset(),
            privacy_boundary_decision=_privacy(),
            drift_decision=_drift(),
            projection={"canonical_state": {"status": "In Progress", "assignee": "hermes"}},
            prior_readback={"canonical_state": {"status": "Done", "assignee": "hermes"}},
            source_revision=REVISION,
            idempotency_identity={"task_id": "SCRUM-348", "idempotency_key": "k1"},
        )
        self.assertEqual(decision["outcome"], "CONFLICT")
        self.assertFalse(decision["current"])
        self.assertEqual(decision["reason_code"], "RECONCILE_READBACK_CONFLICT")
        self.assertIn("status", decision["divergence_fields"])
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])

    def test_pending_when_no_prior_readback(self):
        decision = reconcile_projection_readback(
            envelope=_envelope(),
            source_authority_decision=_source_authority(),
            evidence_linkset=_linkset(),
            privacy_boundary_decision=_privacy(),
            drift_decision=_drift(),
            projection={"canonical_state": {"status": "Done"}},
            prior_readback=None,
            source_revision=REVISION,
            idempotency_identity={"task_id": "SCRUM-348", "idempotency_key": "k1"},
        )
        self.assertEqual(decision["outcome"], "PENDING")
        self.assertFalse(decision["current"])
        self.assertEqual(decision["reason_code"], "RECONCILE_READBACK_PENDING")
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])

    def test_unavailable_when_gates_blocked(self):
        drift = _drift()
        drift["drift_detected"] = True
        decision = reconcile_projection_readback(
            envelope=_envelope(),
            source_authority_decision=_source_authority(),
            evidence_linkset=_linkset(),
            privacy_boundary_decision=_privacy(),
            drift_decision=drift,
            projection={"canonical_state": {"status": "Done"}},
            prior_readback={"canonical_state": {"status": "Done"}},
            source_revision=REVISION,
            idempotency_identity={"task_id": "SCRUM-348", "idempotency_key": "k1"},
        )
        self.assertEqual(decision["outcome"], "UNAVAILABLE")
        self.assertIn("RECONCILE_DRIFT_DETECTED", decision["reason_codes"])
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])

    def test_unknown_never_inferred_success(self):
        # Missing canonical_state on both sides with new contract => PENDING, not CONFIRMED
        decision = reconcile_projection_readback(
            envelope=_envelope(),
            source_authority_decision=_source_authority(),
            evidence_linkset=_linkset(),
            privacy_boundary_decision=_privacy(),
            drift_decision=_drift(),
            projection={},
            prior_readback={},
            source_revision=REVISION,
            idempotency_identity={"task_id": "SCRUM-348", "idempotency_key": "k1"},
        )
        self.assertNotEqual(decision["outcome"], "CONFIRMED")
        errors = sorted(VALIDATOR.iter_errors(decision), key=str)
        self.assertEqual(errors, [], [e.message for e in errors])


if __name__ == "__main__":
    unittest.main()
