#!/usr/bin/env python3
"""NA81 audit-projection tests for external_audit_event_projection (SCRUM-345).

Exercises the SCRUM-345 (NA81-F6-N03) brief requirements for the
``sync_projection.external-audit-event-projection`` node:

* canonical-source rendering
* stable correlation (task / repository / projection_target)
* duplicate replay (idempotent re-projection -> CURRENT, not a new event)
* stale source (digest-valid decision observed against an outdated canonical
  snapshot is surfaced as EXTERNAL_AUDIT_SOURCE_STALE)
* sensitive-field handling (non-canonical / secret keys are never projected)
* missing source (no source-authority decision -> BLOCKED, not READY)
* non-authoritative semantics (every authority field fixed false; read-only)

The renderer is imported via an absolute ``tools/`` path insertion so that
``import node_architect...`` resolves under ``python -m unittest discover``
from the repository root (PEP 420 namespace packages). No connector call,
network request, filesystem mutation, Jira, branch, commit, PR, approval,
merge, deployment or production operation occurs.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.external_audit_event_projection as ea  # noqa: E402

TASK_ID = "SCRUM-345"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
TARGET = "github-audit-mirror"

STALE_OBSERVED_AT = "2026-08-01T00:00:00Z"
FRESH_OBSERVED_AT = "2026-08-15T00:00:00Z"
CUTOFF = "2026-08-10T00:00:00Z"


def _digest(payload):
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _authority(observed_at=FRESH_OBSERVED_AT):
    semantic = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": TARGET,
        "source_bindings": {},
        "field_authority": {},
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "observed_at": observed_at,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    semantic["decision_digest"] = _digest(
        {k: v for k, v in semantic.items() if k not in {"reason_codes", "decision_digest"}}
    )
    semantic["reason_codes"] = []
    return semantic


def _linkset(linkset_digest):
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-evidence-linkset",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": TARGET,
        "outcome": "READY",
        "reason_code": "EVIDENCE_LINKSET_READY",
        "linkset_digest": linkset_digest,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _privacy(redacted=False):
    semantic = {
        "schema_version": "1.0",
        "artifact_type": "projection-privacy-decision",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": TARGET,
        "outcome": "READY",
        "reason_code": "PRIVACY_APPROVED_REDACTED" if redacted else "PRIVACY_APPROVED",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    semantic["decision_digest"] = _digest(
        {k: v for k, v in semantic.items() if k not in {"reason_codes", "decision_digest"}}
    )
    semantic["reason_codes"] = []
    return semantic


def _canonical_state(linkset_digest, authority_digest, privacy_digest, **extra):
    state = {
        "event_id": "E1",
        "event_type": "G3_PASS",
        "task_id": TASK_ID,
        "repository": REPOSITORY,
        "projection_target": TARGET,
        "gate": "G3_PR",
        "gate_outcome": "PASS",
        "evidence_linkset_digest": linkset_digest,
        "source_authority_digest": authority_digest,
        "privacy_boundary_digest": privacy_digest,
        "projected_at": "2026-08-18T00:00:00Z",
    }
    state.update(extra)
    return state


def build(authority=None, linkset_digest=None, privacy=None, canonical_extra=None, stale_authority=False):
    authority = authority or _authority(STALE_OBSERVED_AT if stale_authority else FRESH_OBSERVED_AT)
    linkset_digest = linkset_digest or _digest({"a": 1})
    privacy = privacy or _privacy()
    envelope = {
        "source_authority_digest": authority["decision_digest"],
        "evidence_linkset_digest": linkset_digest,
        "privacy_boundary_digest": privacy["decision_digest"],
        "canonical_state": _canonical_state(
            linkset_digest, authority["decision_digest"], privacy["decision_digest"],
            **(canonical_extra or {}),
        ),
    }
    return authority, _linkset(linkset_digest), privacy, envelope


def project_na81(stale_authority=False, cutoff=None, **kwargs):
    authority, linkset, privacy, envelope = build(stale_authority=stale_authority)
    return ea.project_external_audit_event_na81(
        task_id=TASK_ID,
        repository=REPOSITORY,
        projection_target=TARGET,
        source_authority_decision=authority,
        evidence_linkset=linkset,
        privacy_boundary_decision=privacy,
        envelope=envelope,
        source_freshness_cutoff=cutoff,
        **kwargs,
    )


class ExternalAuditEventProjectionNA81Test(unittest.TestCase):
    # 1. canonical-source rendering -----------------------------------------
    def test_canonical_source_rendering(self):
        authority, linkset, privacy, envelope = build()
        result = ea.project_external_audit_event(
            task_id=TASK_ID, repository=REPOSITORY, projection_target=TARGET,
            source_authority_decision=authority, evidence_linkset=linkset,
            privacy_boundary_decision=privacy, envelope=envelope,
        )
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_code"], "EXTERNAL_AUDIT_EVENT_READY")
        self.assertEqual(result["canonical_state"], envelope["canonical_state"])
        self.assertEqual(result["canonical_state_digest"], _digest(envelope["canonical_state"]))

    # 2. stable correlation -------------------------------------------------
    def test_stable_correlation(self):
        authority, linkset, privacy, envelope = build()
        result = ea.project_external_audit_event(
            task_id=TASK_ID, repository=REPOSITORY, projection_target=TARGET,
            source_authority_decision=authority, evidence_linkset=linkset,
            privacy_boundary_decision=privacy, envelope=envelope,
        )
        self.assertEqual(result["task_id"], TASK_ID)
        self.assertEqual(result["repository"], REPOSITORY)
        self.assertEqual(result["projection_target"], TARGET)
        # invalid identifiers are sanitized, never silently trusted
        bad = ea.project_external_audit_event(
            task_id="not-a-task", repository="bad", projection_target="BAD",
            source_authority_decision=authority, evidence_linkset=linkset,
            privacy_boundary_decision=privacy, envelope=envelope,
        )
        self.assertNotEqual(bad["task_id"], "not-a-task")
        self.assertNotEqual(bad["repository"], "bad")
        self.assertNotEqual(bad["projection_target"], "BAD")

    # 3. duplicate replay (idempotency) -------------------------------------
    def test_duplicate_replay_is_current_not_ready(self):
        authority, linkset, privacy, envelope = build()
        first = ea.project_external_audit_event(
            task_id=TASK_ID, repository=REPOSITORY, projection_target=TARGET,
            source_authority_decision=authority, evidence_linkset=linkset,
            privacy_boundary_decision=privacy, envelope=envelope,
        )
        self.assertEqual(first["outcome"], "READY")
        replay = ea.project_external_audit_event(
            task_id=TASK_ID, repository=REPOSITORY, projection_target=TARGET,
            source_authority_decision=authority, evidence_linkset=linkset,
            privacy_boundary_decision=privacy, envelope=envelope,
            prior_projection=first,
        )
        self.assertEqual(replay["outcome"], "READY")
        self.assertEqual(replay["reason_code"], "EXTERNAL_AUDIT_EVENT_CURRENT")
        self.assertTrue(replay["prior_projection_present"])
        # the canonical content digest is stable across idempotent replay
        self.assertEqual(replay["canonical_state_digest"], first["canonical_state_digest"])
        self.assertEqual(replay["canonical_state"], first["canonical_state"])

    # 4. stale source -------------------------------------------------------
    def test_stale_source_detected(self):
        # digest-valid decision observed against an outdated canonical snapshot
        result = project_na81(stale_authority=True, cutoff=CUTOFF)
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "EXTERNAL_AUDIT_SOURCE_STALE")
        self.assertIn("EXTERNAL_AUDIT_SOURCE_STALE", result["reason_codes"])

    def test_fresh_source_not_stale(self):
        result = project_na81(stale_authority=False, cutoff=CUTOFF)
        self.assertEqual(result["outcome"], "READY")
        self.assertNotEqual(result["reason_code"], "EXTERNAL_AUDIT_SOURCE_STALE")

    def test_no_cutoff_is_backward_compatible(self):
        # without a cutoff the NA81 wrapper behaves exactly like the base renderer
        stale = project_na81(stale_authority=True, cutoff=None)
        base = ea.project_external_audit_event(
            task_id=TASK_ID, repository=REPOSITORY, projection_target=TARGET,
            source_authority_decision=_authority(STALE_OBSERVED_AT),
            evidence_linkset=_linkset(_digest({"a": 1})),
            privacy_boundary_decision=_privacy(),
            envelope=build(stale_authority=True)[3],
        )
        self.assertEqual(stale["outcome"], base["outcome"])
        self.assertEqual(stale["reason_code"], base["reason_code"])
        self.assertEqual(stale["projection_digest"], base["projection_digest"])

    def test_cutoff_equal_observed_is_fresh(self):
        # observed exactly at the cutoff is current, not stale
        authority = _authority(CUTOFF)
        _, linkset, privacy, envelope = build(authority=authority)
        result = ea.project_external_audit_event_na81(
            task_id=TASK_ID, repository=REPOSITORY, projection_target=TARGET,
            source_authority_decision=authority, evidence_linkset=linkset,
            privacy_boundary_decision=privacy, envelope=envelope,
            source_freshness_cutoff=CUTOFF,
        )
        self.assertEqual(result["outcome"], "READY")

    # 5. sensitive-field handling -------------------------------------------
    def test_sensitive_field_never_projected(self):
        # a non-canonical / secret key in canonical_state is dropped, not projected
        authority, linkset, privacy, envelope = build(
            canonical_extra={"api_token": "supersecret", "password": "hunter2"}
        )
        result = ea.project_external_audit_event(
            task_id=TASK_ID, repository=REPOSITORY, projection_target=TARGET,
            source_authority_decision=authority, evidence_linkset=linkset,
            privacy_boundary_decision=privacy, envelope=envelope,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("EXTERNAL_AUDIT_INPUT_INVALID", result["reason_codes"])
        self.assertNotIn("api_token", result["canonical_state"])
        self.assertNotIn("password", result["canonical_state"])

    def test_privacy_boundary_rejected_blocks(self):
        authority, linkset, privacy, envelope = build(privacy=_privacy())
        privacy_bad = dict(privacy)
        privacy_bad["outcome"] = "BLOCKED"
        result = ea.project_external_audit_event(
            task_id=TASK_ID, repository=REPOSITORY, projection_target=TARGET,
            source_authority_decision=authority, evidence_linkset=linkset,
            privacy_boundary_decision=privacy_bad, envelope=envelope,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("EXTERNAL_AUDIT_PRIVACY_BOUNDARY_INVALID", result["reason_codes"])

    # 6. missing source -----------------------------------------------------
    def test_missing_source_blocked(self):
        authority, linkset, privacy, envelope = build()
        result = ea.project_external_audit_event(
            task_id=TASK_ID, repository=REPOSITORY, projection_target=TARGET,
            source_authority_decision=None, evidence_linkset=linkset,
            privacy_boundary_decision=privacy, envelope=envelope,
        )
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertIn("EXTERNAL_AUDIT_SOURCE_AUTHORITY_INVALID", result["reason_codes"])

    # 7. non-authoritative semantics ----------------------------------------
    def test_non_authoritative_semantics(self):
        result = project_na81()
        self.assertTrue(result["read_only_projection"])
        for field in (
            "write_authority_granted", "approval_authority_granted",
            "merge_authority_granted", "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(result[field], f"{field} must be false")

    def test_schema_contract_invariants(self):
        result = project_na81()
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["artifact_type"], "external-audit-event-projection")
        self.assertTrue(result["projection_digest"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
