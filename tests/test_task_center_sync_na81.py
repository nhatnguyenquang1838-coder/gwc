#!/usr/bin/env python3
"""NA81 Task Center sync-intent tests for task_center_sync (SCRUM-344 / #279).

Exercises the SCRUM-279 (NA81-F6-N02) execution-level Task Center sync intent
``render_task_center_sync_na81``:

* deterministic intent (stable idempotency key, deep-equal replay)
* duplicate replay is a clean no-op (SYNC_CURRENT)
* out-of-order source revision is rejected
* stale source (same revision, mutated canonical content) is rejected
* privacy boundary gates the projection
* missing canonical source (no repository head) is rejected
* non-authoritative B1 decisions are rejected (no authority granted)
* monotonic source revision advances cleanly
* readback expectation is explicit and present only when READY

The module is imported via an absolute ``tools/`` path insertion so that
``import node_architect...`` resolves under ``python -m unittest discover``
from the repository root (PEP 420 namespace packages). This honours the
SCRUM-323 import rule.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import node_architect.task_center_sync as tcs  # noqa: E402

TASK_ID = "SCRUM-344"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
TARGET = "task-center"
ZERO = "sha256:" + "0" * 64


def _digest(payload):
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def make_source_authority(task_id=TASK_ID, repository=REPOSITORY, target=TARGET, decision_digest=None):
    d = {
        "schema_version": "1.0",
        "artifact_type": "projection-source-authority-decision",
        "task_id": task_id,
        "repository": repository,
        "projection_target": target,
        "source_bindings": {},
        "field_authority": {},
        "outcome": "READY",
        "authority_status": "CONFIRMED",
        "reason_code": "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
        "reason_codes": ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"],
        "observed_at": "2026-08-18T00:00:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    if decision_digest is None:
        semantic = {k: v for k, v in d.items() if k not in {"reason_codes", "decision_digest"}}
        decision_digest = _digest(semantic)
    d["decision_digest"] = decision_digest
    return d


def make_linkset(task_id=TASK_ID, repository=REPOSITORY, target=TARGET, linkset_digest=None):
    return {
        "schema_version": "1.0",
        "artifact_type": "projection-evidence-linkset",
        "task_id": task_id,
        "repository": repository,
        "projection_target": target,
        "outcome": "READY",
        "reason_code": "EVIDENCE_LINKSET_READY",
        "reason_codes": ["EVIDENCE_LINKSET_READY"],
        "linkset_digest": linkset_digest or _digest({"x": 1}),
        "observed_at": "2026-08-18T00:00:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def make_privacy(task_id=TASK_ID, repository=REPOSITORY, target=TARGET, reason_code="PRIVACY_APPROVED", decision_digest=None):
    d = {
        "schema_version": "1.0",
        "artifact_type": "projection-privacy-decision",
        "task_id": task_id,
        "repository": repository,
        "projection_target": target,
        "outcome": "READY",
        "reason_code": reason_code,
        "reason_codes": [reason_code],
        "observed_at": "2026-08-18T00:00:00Z",
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    if decision_digest is None:
        decision_digest = _digest({k: v for k, v in d.items() if k != "decision_digest"})
    d["decision_digest"] = decision_digest
    return d


def base_state(head="cda2eef0000000000000000000000000000000000"):
    return {
        "task_id": TASK_ID,
        "task_status": "In Progress",
        "task_title": "sync_projection.task-center-sync",
        "task_type": "connector",
        "task_assignee": "hermes",
        "gate": "G2_EXECUTION",
        "gate_outcome": "READY",
        "repository": REPOSITORY,
        "repository_head": head,
        "projection_target": TARGET,
        "projected_at": "2026-08-18T00:00:00Z",
        "evidence_linkset_digest": "sha256:" + "a" * 64,
        "source_authority_digest": "sha256:" + "b" * 64,
        "privacy_boundary_digest": "sha256:" + "c" * 64,
    }


def render(**over):
    kw = dict(
        task_id=TASK_ID,
        repository=REPOSITORY,
        projection_target=TARGET,
        source_authority_decision=make_source_authority(),
        evidence_linkset=make_linkset(),
        privacy_boundary_decision=make_privacy(),
        envelope={"canonical_state": base_state()},
        source_revision=5,
    )
    kw.update(over)
    return tcs.render_task_center_sync_na81(**kw)


class TestTaskCenterSyncIntentNA81(unittest.TestCase):

    def test_deterministic_intent(self):
        a = render()
        b = render()
        self.assertEqual(a, b)
        self.assertEqual(a["outcome"], "READY")
        self.assertEqual(a["reason_code"], "TASK_CENTER_NA81_SYNC_READY")
        self.assertTrue(a["read_only_projection"])
        self.assertFalse(any(a[k] for k in (
            "write_authority_granted", "approval_authority_granted",
            "merge_authority_granted", "deployment_authority_granted",
            "production_authority_granted",
        )))
        # stable idempotency key
        self.assertTrue(a["idempotency_key"].startswith("sha256:"))
        self.assertEqual(a["idempotency_key"], b["idempotency_key"])
        # explicit readback expectation present and consistent
        rb = a["readback_expectation"]
        self.assertIsNotNone(rb)
        self.assertEqual(rb["task_id"], TASK_ID)
        self.assertEqual(rb["projection_target"], TARGET)
        self.assertEqual(rb["source_revision"], 5)
        self.assertEqual(rb["expected_canonical_state_digest"], a["canonical_state_digest"])
        self.assertEqual(rb["idempotency_key"], a["idempotency_key"])
        self.assertEqual(a["monotonic_source_revision"], 5)

    def test_duplicate_replay_is_noop(self):
        first = render()
        self.assertEqual(first["reason_code"], "TASK_CENTER_NA81_SYNC_READY")
        second = render(prior_readback_expectation=first["readback_expectation"])
        self.assertEqual(second["outcome"], "READY")
        self.assertEqual(second["reason_code"], "TASK_CENTER_NA81_SYNC_CURRENT")
        # idempotency key identical -> replay is a clean no-op: the deterministic
        # sync intent does not change even though a prior readback now exists.
        self.assertEqual(second["idempotency_key"], first["idempotency_key"])
        self.assertEqual(second["canonical_state_digest"], first["canonical_state_digest"])

    def test_out_of_order_revision_rejected(self):
        prior = render()["readback_expectation"]  # source_revision 5
        # source moved backwards to 3 at identical content
        lower = render(source_revision=3, prior_readback_expectation=prior)
        self.assertEqual(lower["outcome"], "BLOCKED")
        self.assertEqual(lower["reason_code"], "TASK_CENTER_NA81_REVISION_OUT_OF_ORDER")
        self.assertIsNone(lower["readback_expectation"])
        self.assertIsNone(lower["monotonic_source_revision"])
        self.assertFalse(any(lower[k] for k in (
            "write_authority_granted", "approval_authority_granted",
            "merge_authority_granted", "deployment_authority_granted",
            "production_authority_granted",
        )))

    def test_stale_source_rejected(self):
        prior = render()["readback_expectation"]  # rev 5, digest over base_state
        # same revision 5 but canonical content mutated -> stale
        mutated = dict(base_state())
        mutated["task_status"] = "Done"
        stale = render(envelope={"canonical_state": mutated}, prior_readback_expectation=prior)
        self.assertEqual(stale["outcome"], "BLOCKED")
        self.assertEqual(stale["reason_code"], "TASK_CENTER_NA81_STALE_SOURCE")
        self.assertIsNone(stale["readback_expectation"])

    def test_monotonic_revision_advances(self):
        prior = render()["readback_expectation"]  # rev 5
        advanced = render(source_revision=6, prior_readback_expectation=prior)
        self.assertEqual(advanced["outcome"], "READY")
        self.assertEqual(advanced["reason_code"], "TASK_CENTER_NA81_SYNC_READY")
        self.assertEqual(advanced["monotonic_source_revision"], 6)
        self.assertNotEqual(advanced["idempotency_key"], prior["idempotency_key"])
        rb = advanced["readback_expectation"]
        self.assertEqual(rb["source_revision"], 6)

    def test_privacy_boundary_invalid_rejected(self):
        bad_privacy = make_privacy(reason_code="PRIVACY_DENIED")
        out = render(privacy_boundary_decision=bad_privacy)
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertEqual(out["reason_code"], "TASK_CENTER_NA81_PRIVACY_BOUNDARY_INVALID")
        self.assertIsNone(out["readback_expectation"])
        self.assertFalse(any(out[k] for k in (
            "write_authority_granted", "approval_authority_granted",
            "merge_authority_granted", "deployment_authority_granted",
            "production_authority_granted",
        )))

    def test_privacy_redacted_accepted(self):
        redacted = make_privacy(reason_code="PRIVACY_APPROVED_REDACTED")
        out = render(privacy_boundary_decision=redacted)
        self.assertEqual(out["outcome"], "READY")
        self.assertIsNotNone(out["readback_expectation"])

    def test_protected_keys_never_projected(self):
        # canonical_state keys outside ALLOWED_CANONICAL_KEYS are dropped, never
        # projected to Task Center (privacy boundary). An unknown key is invalid.
        state = dict(base_state())
        state["password"] = "supersecret"
        out = render(envelope={"canonical_state": state})
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("TASK_CENTER_NA81_INPUT_INVALID", out["reason_codes"])
        self.assertNotIn("password", out["canonical_state"])

    def test_missing_canonical_source_rejected(self):
        # no repository head -> no canonical source anchor
        state = {k: v for k, v in base_state().items() if k != "repository_head"}
        out = render(envelope={"canonical_state": state})
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertEqual(out["reason_code"], "TASK_CENTER_NA81_MISSING_CANONICAL_SOURCE")
        self.assertIsNone(out["readback_expectation"])

    def test_empty_canonical_state_missing_source(self):
        out = render(envelope={"canonical_state": {}})
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("TASK_CENTER_NA81_MISSING_CANONICAL_SOURCE", out["reason_codes"])

    def test_non_authoritative_source_rejected(self):
        bad_auth = make_source_authority()
        bad_auth["outcome"] = "BLOCKED"
        bad_auth["authority_status"] = "DENIED"
        # recompute digest so it stays internally consistent
        semantic = {k: v for k, v in bad_auth.items() if k not in {"reason_codes", "decision_digest"}}
        bad_auth["decision_digest"] = _digest(semantic)
        out = render(source_authority_decision=bad_auth)
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertEqual(out["reason_code"], "TASK_CENTER_NA81_NON_AUTHORITATIVE")
        self.assertFalse(any(out[k] for k in (
            "write_authority_granted", "approval_authority_granted",
            "merge_authority_granted", "deployment_authority_granted",
            "production_authority_granted",
        )))

    def test_non_authoritative_linkset_rejected(self):
        bad_linkset = make_linkset()
        bad_linkset["outcome"] = "BLOCKED"
        out = render(evidence_linkset=bad_linkset)
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertEqual(out["reason_code"], "TASK_CENTER_NA81_NON_AUTHORITATIVE")

    def test_prior_readback_mismatch_rejected(self):
        prior = {"source_revision": 5, "expected_canonical_state_digest": "not-a-digest", "idempotency_key": "not-a-digest"}
        out = render(prior_readback_expectation=prior)
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertEqual(out["reason_code"], "TASK_CENTER_NA81_PRIOR_READBACK_MISMATCH")
        self.assertIsNone(out["readback_expectation"])

    def test_invalid_identifiers_rejected(self):
        out = render(task_id="not-a-task")
        self.assertEqual(out["outcome"], "BLOCKED")
        self.assertIn("TASK_CENTER_NA81_INPUT_INVALID", out["reason_codes"])


if __name__ == "__main__":
    unittest.main()
