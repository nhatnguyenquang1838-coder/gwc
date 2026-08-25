#!/usr/bin/env python3
"""SCRUM-533 event_source tests for external_audit_event_projection.

Verifies the SCRUM-533 v3.1 amendment L1.1/L1.2 requirements added on top of the
SCRUM-222/SCRUM-345 renderer:

* optional event_source is accepted and participates in the canonical digest
* event_source format violation fails closed (EVENT_SOURCE_BINDING_CONFLICT)
* caller-supplied event_source inconsistent with the projection's own
  system/target/schema-version fails closed
* legacy projections WITHOUT event_source render exactly as before
  (backward compatibility)
* idempotent re-projection with the same event_source -> CURRENT

Read-only. No connector call, network, filesystem mutation, Jira, branch,
commit, PR, approval, merge, deployment or production operation.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.external_audit_event_projection as ea  # noqa: E402

TASK_ID = "SCRUM-533"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
TARGET = "external-audit-projection"
OBSERVED_AT = "2026-08-15T00:00:00Z"
PROJECTED_AT = "2026-08-20T00:00:00Z"

CANONICAL_STATE = {
    "event_id": "evt-0001",
    "event_type": "external_audit",
    "task_id": TASK_ID,
    "repository": REPOSITORY,
    "repository_head": "0" * 40,
    "projection_target": TARGET,
    "gate": "G2_EXECUTION",
    "gate_outcome": "PASS",
    "evidence_linkset_digest": "sha256:" + "1" * 64,
    "source_authority_digest": "sha256:" + "2" * 64,
    "privacy_boundary_digest": "sha256:" + "3" * 64,
    "projected_at": PROJECTED_AT,
}


def _digest(value) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _authority_decision() -> dict:
    decision = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": TARGET,
        "source_bindings": {"task_id": TASK_ID, "repository": REPOSITORY},
        "field_authority": {"default": "READ_ONLY"},
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": OBSERVED_AT,
        "decision_digest": None,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    decision["decision_digest"] = _digest(
        {k: v for k, v in decision.items() if k not in {"reason_codes", "decision_digest"}}
    )
    return decision


def _linkset() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-evidence-linkset",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": TARGET,
        "outcome": "READY",
        "reason_code": "EVIDENCE_LINKSET_READY",
        "linkset_digest": "sha256:" + "1" * 64,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _privacy_decision() -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-privacy-decision",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": TARGET,
        "outcome": "READY",
        "reason_code": "PRIVACY_APPROVED",
        "decision_digest": "sha256:" + "3" * 64,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _envelope(event_source: str | None = None) -> dict:
    cs = dict(CANONICAL_STATE)
    if event_source is not None:
        cs["event_source"] = event_source
    return {"source_authority_digest": _authority_decision()["decision_digest"],
            "evidence_linkset_digest": _linkset()["linkset_digest"],
            "privacy_boundary_digest": _privacy_decision()["decision_digest"],
            "canonical_state": cs}


class EventSourceTest(unittest.TestCase):
    def _project(self, event_source=None):
        return ea.project_external_audit_event(
            task_id=TASK_ID,
            repository=REPOSITORY,
            projection_target=TARGET,
            source_authority_decision=_authority_decision(),
            evidence_linkset=_linkset(),
            privacy_boundary_decision=_privacy_decision(),
            envelope=_envelope(event_source),
            projected_at=PROJECTED_AT,
        )

    def test_canonical_event_source_accepted(self):
        result = self._project("gwc.node-architect.external-audit-projection.v1.0")
        self.assertEqual(result["outcome"], "READY", result["reason_codes"])
        self.assertIn("event_source", result["canonical_state"])
        # event_source participates in the canonical_state_digest.
        self.assertEqual(
            result["canonical_state_digest"],
            ea._canonical_state_digest(result["canonical_state"]),
        )

    def test_event_source_participates_in_semantic_identity(self):
        with_source = self._project("gwc.node-architect.external-audit-projection.v1.0")
        without_source = self._project(None)
        self.assertNotEqual(with_source["canonical_state_digest"], without_source["canonical_state_digest"])

    def test_invalid_format_fails_closed(self):
        result = self._project("https://evil.example/not-a-namespace")
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("EVENT_SOURCE_BINDING_CONFLICT", result["reason_codes"])

    def test_inconsistent_source_fails_closed(self):
        # Wrong target / wrong system / wrong version must not bind.
        for bad in ("gwc.other-system.external-audit-projection.v1.0",
                    "gwc.node-architect.wrong-target.v1.0",
                    "gwc.node-architect.external-audit-projection.v9.9"):
            with self.subTest(bad=bad):
                result = self._project(bad)
                self.assertEqual(result["outcome"], "BLOCKED")
                self.assertIn("EVENT_SOURCE_BINDING_CONFLICT", result["reason_codes"])

    def test_legacy_without_event_source_unchanged(self):
        result = self._project(None)
        self.assertEqual(result["outcome"], "READY")
        self.assertNotIn("event_source", result["canonical_state"])
        # All authority flags stay false.
        for flag in ("write_authority_granted", "approval_authority_granted",
                     "merge_authority_granted", "deployment_authority_granted",
                     "production_authority_granted"):
            self.assertFalse(result[flag])

    def test_idempotent_reprojection_same_source_current(self):
        first = self._project("gwc.node-architect.external-audit-projection.v1.0")
        second = ea.project_external_audit_event(
            task_id=TASK_ID,
            repository=REPOSITORY,
            projection_target=TARGET,
            source_authority_decision=_authority_decision(),
            evidence_linkset=_linkset(),
            privacy_boundary_decision=_privacy_decision(),
            envelope=_envelope("gwc.node-architect.external-audit-projection.v1.0"),
            prior_projection=first,
            projected_at=PROJECTED_AT,
        )
        self.assertEqual(second["outcome"], "READY")
        self.assertEqual(second["reason_code"], "EXTERNAL_AUDIT_EVENT_CURRENT")


if __name__ == "__main__":
    unittest.main()
