#!/usr/bin/env python3
"""Tests for runtime_checkpoint.state-reconciliation (SCRUM-209)."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "tools" / "node_architect" / "runtime_checkpoint"),
)

from state_reconciliation import (  # noqa: E402
    REASON_CODES,
    ROUTES,
    SCHEMA_ID,
    SCHEMA_VERSION,
    Outcome,
    authority_granted,
    load_evidence,
    m5_claimable,
    reconcile_state,
)

BASE_EVIDENCE = {
    "task_id": "SCRUM-209",
    "worker_id": "worker-1",
    "repository": "org/gwc",
    "branch": "fastlane/SCRUM-209",
    "evidence_refreshed": True,
    "checkpoint": {
        "checkpoint_id": "ckpt-1",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "scope_hash": "scope-1",
    },
    "repository_state": {
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "scope_hash": "scope-1",
        "unknown_write_detected": False,
    },
    "runtime_event": {"pending_action_id": "act-1", "pending_action_status": "NONE"},
    "lease": {"status": "ACTIVE", "holder": "worker-1"},
    "cas_revision": {"expected": 7, "observed": 7},
    "approval": {"status": "VALID", "scope_hash": "scope-1"},
    "ci": {"evidence_available": True, "conclusion": "SUCCESS", "head_sha": "b" * 40},
}


def evidence(**overrides):
    payload = copy.deepcopy(BASE_EVIDENCE)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key].update(value)
        else:
            payload[key] = value
    return payload


class StateReconciliationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_evidence(self, name, payload):
        path = self.tmpdir / name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def assert_route(self, result, outcome, reason, route, drift):
        self.assertEqual(result.outcome, outcome)
        self.assertEqual(result.reason, reason)
        self.assertEqual(result.route, route)
        self.assertEqual(result.drift_classification, drift)
        self.assertIn(result.reason, REASON_CODES)
        self.assertIn(result.route, ROUTES)

    # --- acceptance-criteria scenarios ------------------------------------
    def test_clean_resume(self):
        result = reconcile_state(evidence())
        self.assert_route(result, Outcome.PASS, "RECONCILED_RESUME", "RESUME", "NONE")
        self.assertTrue(result.exact_head_ci_verified)
        self.assertTrue(m5_claimable(result))

    def test_base_drift_routes_to_repair(self):
        result = reconcile_state(evidence(repository_state={"base_sha": "c" * 40}))
        self.assert_route(result, Outcome.PASS, "RECONCILED_REPAIR", "REPAIR", "BASE_DRIFT")
        self.assertFalse(m5_claimable(result))

    def test_approval_expiry_requires_reapproval(self):
        result = reconcile_state(evidence(approval={"status": "EXPIRED"}))
        self.assert_route(
            result,
            Outcome.PASS,
            "RECONCILED_REAPPROVAL_REQUIRED",
            "REAPPROVAL_REQUIRED",
            "APPROVAL_DRIFT",
        )

    def test_cas_mismatch_routes_to_repair(self):
        result = reconcile_state(evidence(cas_revision={"observed": 9}))
        self.assert_route(result, Outcome.PASS, "RECONCILED_REPAIR", "REPAIR", "CAS_DRIFT")

    def test_stale_lease_aborts_worker(self):
        result = reconcile_state(evidence(lease={"status": "EXPIRED", "holder": "worker-2"}))
        self.assert_route(
            result, Outcome.FAIL, "ABORT_STALE_WORKER", "ABORT_STALE_WORKER", "LEASE_DRIFT"
        )

    def test_lease_held_by_other_worker_aborts(self):
        result = reconcile_state(evidence(lease={"status": "ACTIVE", "holder": "worker-9"}))
        self.assert_route(
            result, Outcome.FAIL, "ABORT_STALE_WORKER", "ABORT_STALE_WORKER", "LEASE_DRIFT"
        )

    def test_unknown_write_stops_blocked(self):
        result = reconcile_state(evidence(repository_state={"unknown_write_detected": True}))
        self.assert_route(result, Outcome.FAIL, "DRIFT_DETECTED", "STOP_BLOCKED", "UNKNOWN_WRITE")

    def test_committed_before_response_is_idempotent_replay(self):
        result = reconcile_state(evidence(runtime_event={"pending_action_status": "COMMITTED"}))
        self.assert_route(
            result, Outcome.PASS, "IDEMPOTENT_REPLAY", "RESUME", "COMMITTED_BEFORE_RESPONSE"
        )

    def test_missing_ci_evidence_never_claims_pass(self):
        result = reconcile_state(evidence(ci={"evidence_available": False, "conclusion": None}))
        self.assert_route(
            result, Outcome.FAIL, "EVIDENCE_UNAVAILABLE", "STOP_BLOCKED", "EVIDENCE_MISSING"
        )
        self.assertIn("EVIDENCE_MISSING:ci.evidence_available", result.limitations)
        self.assertFalse(result.exact_head_ci_verified)

    def test_evidence_not_refreshed_blocks(self):
        result = reconcile_state(evidence(evidence_refreshed=False))
        self.assert_route(
            result, Outcome.FAIL, "EVIDENCE_UNAVAILABLE", "STOP_BLOCKED", "EVIDENCE_MISSING"
        )
        self.assertIn("CANONICAL_EVIDENCE_NOT_REFRESHED", result.limitations)

    # --- invariants --------------------------------------------------------
    def test_exact_head_ci_required_for_m5(self):
        stale_ci = reconcile_state(evidence(ci={"head_sha": "d" * 40}))
        self.assertEqual(stale_ci.route, "RESUME")
        self.assertFalse(stale_ci.exact_head_ci_verified)
        self.assertFalse(m5_claimable(stale_ci))
        self.assertIn("EXACT_HEAD_CI_NOT_VERIFIED", stale_ci.limitations)

    def test_authority_never_granted(self):
        for payload in (
            evidence(),
            evidence(lease={"status": "EXPIRED"}),
            evidence(approval={"status": "REVOKED"}),
        ):
            result = reconcile_state(payload)
            self.assertFalse(authority_granted(result))
            self.assertFalse(result.to_dict()["authority_granted"])

    def test_result_is_deterministic(self):
        first = reconcile_state(evidence())
        second = reconcile_state(evidence())
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.result_digest, second.result_digest)
        self.assertRegex(first.result_digest, r"^sha256:[0-9a-f]{64}$")
        noisy = reconcile_state(evidence(observed_at="2026-01-01T00:00:00Z", run_id="r-2"))
        self.assertEqual(first.result_digest, noisy.result_digest)

    def test_different_drift_yields_different_digest(self):
        self.assertNotEqual(
            reconcile_state(evidence()).result_digest,
            reconcile_state(evidence(cas_revision={"observed": 42})).result_digest,
        )

    def test_load_evidence_from_tempdir_file(self):
        path = self.write_evidence("evidence.json", evidence())
        result = reconcile_state(load_evidence(str(path)))
        self.assert_route(result, Outcome.PASS, "RECONCILED_RESUME", "RESUME", "NONE")
        self.assertEqual(result.to_dict()["schema_id"], SCHEMA_ID)
        self.assertEqual(result.to_dict()["schema_version"], SCHEMA_VERSION)

    def test_result_matches_schema_shape(self):
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / "node-architect"
            / "runtime-checkpoint"
            / "state-reconciliation.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        payload = reconcile_state(evidence()).to_dict()
        self.assertEqual(set(schema["required"]) - set(payload), set())
        self.assertEqual(set(payload) - set(schema["properties"]), set())
        try:
            import jsonschema  # type: ignore
        except ImportError:  # pragma: no cover - optional dependency
            self.skipTest("jsonschema not installed; structural check only")
        jsonschema.validate(payload, schema)


if __name__ == "__main__":
    unittest.main()
