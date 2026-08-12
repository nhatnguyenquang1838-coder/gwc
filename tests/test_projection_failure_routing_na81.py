"""NA81 current-task tests for SCRUM-349 (sync_projection.projection-failure-routing).

These tests validate the current brief's additional requirements without relying
on the sandbox-broken ``jsonschema``/``rpds`` package (validated in CI instead):
- exhausted retry routes to HUMAN_REQUIRED
- unavailable target routes to BLOCKED
- advisory nonblocking (degraded + stale evidence) routes to ADVISORY_NONBLOCKING
- unknown evidence routes to HUMAN_REQUIRED
- deterministic replay under new verdicts
- backward-compatible default params (existing M4 tests unchanged)
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from node_architect.projection_failure_routing import route_projection_failure

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
REVISION_A = "d9a89a002aae4348359cd88810a9d03926199597"

ALLOWED_ROUTING_VERDICTS = {
    "RETRYABLE", "HARD_DENIED", "STALE_EVIDENCE", "AUTHORITY_CONFLICT",
    "BLOCKED", "RETRYABLE_EXHAUSTED", "HUMAN_REQUIRED", "ADVISORY_NONBLOCKING",
}


def _authority_digest(decision):
    semantic = {k: v for k, v in decision.items() if k not in {"reason_codes", "decision_digest"}}
    payload = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def valid_source_authority():
    decision = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": "SCRUM-349",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "source_bindings": [
            {"source_type": "TASK_RECORD", "authority_class": "CANONICAL",
             "ref": "jira:SCRUM-349", "revision": REVISION_A, "content_digest": DIGEST_A,
             "observed_at": "2026-08-06T13:00:00Z", "status": "VERIFIED"},
        ],
        "field_authority": [
            {"field_path": "/task/status", "source_ref": "jira:SCRUM-349",
             "source_revision": REVISION_A, "evidence_digest": DIGEST_A, "derivation": "DIRECT"},
        ],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": "2026-08-06T13:05:00Z",
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
        "task_id": "SCRUM-349",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "source_authority_digest": valid_source_authority()["decision_digest"],
        "links": [
            {"evidence_id": "task-349", "source_type": "TASK_RECORD", "ref": "jira:SCRUM-349",
             "revision": REVISION_A, "content_digest": DIGEST_A, "relation": "SUPPORTS_FIELD",
             "field_paths": ["/task/status"], "verification_status": "VERIFIED"},
        ],
        "covered_fields": ["/task/status"],
        "uncovered_fields": [],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_EVIDENCE_LINKSET_CONFIRMED",
        "reason_codes": ["PROJECTION_EVIDENCE_LINKSET_CONFIRMED"],
        "observed_at": "2026-08-06T13:06:00Z",
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
        "task_id": "SCRUM-349",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "evidence_linkset_digest": DIGEST_B,
        "rejected_classes": ["SECRET", "CREDENTIAL", "TOKEN", "PRIVATE_KEY", "PRODUCTION_DATA", "HIDDEN_REASONING"],
        "redacted_fields": [],
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_PRIVACY_BOUNDARY_CONFIRMED",
        "reason_codes": ["PROJECTION_PRIVACY_BOUNDARY_CONFIRMED"],
        "observed_at": "2026-08-06T13:07:00Z",
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
        "task_id": "SCRUM-349",
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
        "observed_at": "2026-08-06T14:00:00Z",
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
        "task_id": "SCRUM-349",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "projection_target": "failure-routing",
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_CURRENT" if current else "RECONCILE_READBACK_DIVERGENCE",
        "reason_codes": ["PROJECTION_CURRENT"] if current else ["RECONCILE_READBACK_DIVERGENCE"],
        "current": current,
        "divergence_fields": [] if current else ["status"],
        "canonical_state_digest": "sha256:" + "0" * 64,
        "observed_at": "2026-08-06T14:05:00Z",
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
        "task_id": "SCRUM-349",
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


def route(**kwargs):
    base = dict(
        envelope=valid_envelope(),
        source_authority_decision=valid_source_authority(),
        evidence_linkset=valid_linkset(),
        privacy_boundary_decision=valid_privacy(),
        drift_decision=valid_drift(),
        reconcile_decision=valid_reconcile(),
    )
    base.update(kwargs)
    decision = route_projection_failure(**base)
    # Lightweight validation: required keys, allowed verdict, authority consts.
    required = {
        "schema_version", "artifact_type", "task_id", "repository",
        "projection_target", "outcome", "authority_status", "reason_code",
        "reason_codes", "routing_verdict", "read_only_projection",
        "write_authority_granted", "approval_authority_granted",
        "merge_authority_granted", "deployment_authority_granted",
        "production_authority_granted", "decision_digest",
    }
    missing = sorted(required - set(decision))
    assert missing == [], f"missing keys: {missing}"
    assert decision["outcome"] in {"READY", "BLOCKED"}, decision["outcome"]
    assert decision["routing_verdict"] in ALLOWED_ROUTING_VERDICTS, decision["routing_verdict"]
    assert decision["read_only_projection"] is True
    for field in ["write_authority_granted", "approval_authority_granted",
                  "merge_authority_granted", "deployment_authority_granted",
                  "production_authority_granted"]:
        assert decision[field] is False, field
    return decision


class SCRUM349NA81Tests(unittest.TestCase):
    """NA81 requirement→code→test evidence map for SCRUM-349."""

    # --- exhausted retry routes to HUMAN_REQUIRED ---

    def test_exhausted_retry_routes_human_required(self):
        decision = route(
            drift_decision=valid_drift(drift_detected=True),
            reconcile_decision=valid_reconcile(current=False),
            retry_exhausted=True,
        )
        self.assertEqual(decision["outcome"], "READY")
        self.assertEqual(decision["routing_verdict"], "HUMAN_REQUIRED")
        self.assertEqual(decision["reason_code"], "ROUTE_RETRYABLE_EXHAUSTED")

    # --- unavailable target routes to BLOCKED ---

    def test_unavailable_target_routes_blocked(self):
        decision = route(projection_availability="unavailable")
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertEqual(decision["routing_verdict"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "ROUTE_UNAVAILABLE_TARGET")

    # --- advisory nonblocking (degraded + stale evidence) ---

    def test_degraded_target_stale_evidence_advisory_nonblocking(self):
        decision = route(
            projection_availability="degraded",
            drift_decision=valid_drift(drift_detected=False),
            reconcile_decision=valid_reconcile(current=False),
        )
        self.assertEqual(decision["outcome"], "READY")
        self.assertEqual(decision["routing_verdict"], "ADVISORY_NONBLOCKING")
        self.assertEqual(decision["reason_code"], "ROUTE_ADVISORY_NONBLOCKING")

    # --- unknown evidence routes to HUMAN_REQUIRED ---

    def test_unknown_evidence_routes_human_required(self):
        decision = route(unknown_evidence=True)
        self.assertEqual(decision["outcome"], "READY")
        self.assertEqual(decision["routing_verdict"], "HUMAN_REQUIRED")
        self.assertEqual(decision["reason_code"], "ROUTE_UNKNOWN_EVIDENCE")

    # --- backward compatibility: defaults unchanged ---

    def test_default_params_preserve_retryable(self):
        decision = route(
            drift_decision=valid_drift(drift_detected=True),
            reconcile_decision=valid_reconcile(current=False),
        )
        self.assertEqual(decision["routing_verdict"], "RETRYABLE")

    def test_default_params_preserve_hard_denied(self):
        decision = route(
            drift_decision=valid_drift(drift_detected=False),
            reconcile_decision=valid_reconcile(current=True),
        )
        self.assertEqual(decision["routing_verdict"], "HARD_DENIED")

    # --- deterministic replay ---

    def test_deterministic_replay_na81(self):
        first = route(
            retry_exhausted=True,
            drift_decision=valid_drift(drift_detected=True),
            reconcile_decision=valid_reconcile(current=False),
        )
        second = route(
            retry_exhausted=True,
            drift_decision=valid_drift(drift_detected=True),
            reconcile_decision=valid_reconcile(current=False),
        )
        self.assertEqual(first["decision_digest"], second["decision_digest"])

    # --- unavailable overrides retry_exhausted ---

    def test_unavailable_overrides_retry_exhausted(self):
        decision = route(
            retry_exhausted=True,
            projection_availability="unavailable",
        )
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertEqual(decision["routing_verdict"], "BLOCKED")
        self.assertEqual(decision["reason_code"], "ROUTE_UNAVAILABLE_TARGET")

    # --- no authority granted on new verdicts ---

    def test_no_authority_granted_on_human_required(self):
        decision = route(
            drift_decision=valid_drift(drift_detected=True),
            reconcile_decision=valid_reconcile(current=False),
            retry_exhausted=True,
        )
        for field in ["write_authority_granted", "approval_authority_granted",
                      "merge_authority_granted", "deployment_authority_granted",
                      "production_authority_granted"]:
            self.assertEqual(decision[field], False, field)
        self.assertTrue(decision["read_only_projection"])


if __name__ == "__main__":
    unittest.main()
