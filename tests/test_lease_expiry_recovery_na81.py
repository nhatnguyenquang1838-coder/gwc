#!/usr/bin/env python3
"""NA81 (SCRUM-366) lease-expiry-recovery delta tests.

Covers the current task brief: fence an expired holder, reconcile unknown
in-flight effects, and permit reacquire/resume only for the *current authorized
actor/run/scope* (wrong actor/scope/run and renewal-race are fenced). Mirrors
the historical SCRUM-243 M5 tests but asserts the NA81 binding/renewal-race
contract. The `tools/` dir is inserted into sys.path[0] so `node_architect`
resolves under CI (Python 3.12 namespace-package discipline, SCRUM-323 lesson).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

from node_architect.lease_expiry_recovery import (  # noqa: E402
    decide_lease_expiry_recovery,
    is_replay_equivalent,
)

BASE = "ba018a8be718be1137a875ffe2533520a6209613"
HEAD = "a" * 40
SCOPE = "sha256:60a28922c6921e4f" + "0" * 48


def decide(**overrides):
    payload = dict(
        task_id="SCRUM-366", repository="nhatnguyenquang1838-coder/gwc",
        branch="auto/SCRUM-366-na81-20260810", base_sha=BASE, head_sha=HEAD,
        scope_hash=SCOPE, lease_id="lease-1", worker_id="worker-a", run_id="run-1",
        now_epoch_ms=2000, lease_expires_epoch_ms=1000, observed_fencing_token=7,
        worker_fencing_token=7, readback_status="VERIFIED_ZERO_EFFECT",
        reacquire_status="REACQUIRED_MONOTONIC", duplicate_agent_detected=False,
        side_effect_status="NONE", observed_at="2026-08-12T00:00:00Z",
        expected_actor_id="worker-a", expected_run_id="run-1",
        expected_scope_hash=SCOPE,
    )
    payload.update(overrides)
    return decide_lease_expiry_recovery(**payload)


class LeaseExpiryRecoveryNA81Tests(unittest.TestCase):
    # --- exact expiry boundary ---
    def test_exact_boundary_now_equal_expires_is_expired(self):
        # at the boundary the lease is expired and the expiry branch is taken
        # (readback not yet verified -> safe readback required before resume)
        result = decide(now_epoch_ms=1000, lease_expires_epoch_ms=1000, readback_status="PENDING")
        self.assertTrue(result["lease_expired"])
        self.assertEqual(result["outcome"], "READBACK_REQUIRED")
        self.assertFalse(result["advancement_allowed"])
        self.assertFalse(result["side_effect_allowed"])

    def test_one_ms_before_boundary_still_valid(self):
        result = decide(now_epoch_ms=999, lease_expires_epoch_ms=1000)
        self.assertFalse(result["lease_expired"])
        self.assertEqual(result["outcome"], "CONTINUE")

    # --- stale holder ---
    def test_stale_holder_fenced(self):
        result = decide(worker_fencing_token=6, observed_fencing_token=7)
        self.assertEqual(result["outcome"], "FENCE_STALE_WORKER")

    # --- unknown in-flight effect must reconcile, never blind retry ---
    def test_unknown_in_flight_effect_reconciles(self):
        result = decide(side_effect_status="UNKNOWN")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertFalse(result["blind_retry_allowed"])
        self.assertFalse(result["advancement_allowed"])

    def test_committed_in_flight_effect_reconciles(self):
        result = decide(side_effect_status="COMMITTED")
        self.assertEqual(result["outcome"], "RECONCILE")

    # --- renewal race / concurrent reacquire ---
    def test_renewal_race_fenced(self):
        result = decide(concurrent_reacquire_detected=True)
        self.assertEqual(result["outcome"], "FENCE_CONCURRENT_REACQUIRE")
        self.assertFalse(result["advancement_allowed"])

    # --- safe reacquire by current authorized holder ---
    def test_safe_reacquire_by_current_actor_run_scope(self):
        result = decide()
        self.assertEqual(result["outcome"], "CONTINUE_AFTER_REACQUIRE")
        self.assertTrue(result["advancement_allowed"])
        self.assertTrue(result["side_effect_allowed"])
        self.assertTrue(result["binding_valid"])

    # --- wrong actor / run / scope are fenced (never resume) ---
    def test_wrong_actor_fenced(self):
        result = decide(worker_id="worker-b")
        self.assertEqual(result["outcome"], "FENCE_WRONG_ACTOR")
        self.assertFalse(result["binding_valid"])
        self.assertFalse(result["advancement_allowed"])
        self.assertFalse(result["side_effect_allowed"])

    def test_wrong_run_fenced(self):
        result = decide(run_id="run-2")
        self.assertEqual(result["outcome"], "FENCE_WRONG_RUN")
        self.assertFalse(result["binding_valid"])

    def test_wrong_scope_fenced(self):
        result = decide(scope_hash="sha256:deadbeef" + "0" * 56)
        self.assertEqual(result["outcome"], "FENCE_WRONG_SCOPE")
        self.assertFalse(result["binding_valid"])

    def test_wrong_actor_during_valid_lease_also_fenced(self):
        # even before expiry, a non-authorized actor must not advance
        result = decide(now_epoch_ms=500, lease_expires_epoch_ms=1000, worker_id="worker-b")
        self.assertEqual(result["outcome"], "FENCE_WRONG_ACTOR")
        self.assertFalse(result["advancement_allowed"])

    # --- duplicate / concurrent agent ---
    def test_duplicate_agent_race_fenced(self):
        result = decide(duplicate_agent_detected=True)
        self.assertEqual(result["outcome"], "FENCE_DUPLICATE_AGENT")

    # --- backward compatibility: omitting binding params keeps old behavior ---
    def test_unbound_call_keeps_historical_resume(self):
        result = decide_lease_expiry_recovery(
            task_id="SCRUM-243", repository="nhatnguyenquang1838-coder/gwc",
            branch="legacy", base_sha=BASE, head_sha=HEAD, scope_hash=SCOPE,
            lease_id="lease-1", worker_id="worker-a", now_epoch_ms=2000,
            lease_expires_epoch_ms=1000, observed_fencing_token=7,
            worker_fencing_token=7, readback_status="VERIFIED_ZERO_EFFECT",
            reacquire_status="REACQUIRED_MONOTONIC",
            duplicate_agent_detected=False, side_effect_status="NONE")
        self.assertEqual(result["outcome"], "CONTINUE_AFTER_REACQUIRE")
        self.assertTrue(result["binding_valid"])

    # --- replay determinism ---
    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-08-12T00:00:00Z")
        second = decide(observed_at="2026-08-12T00:05:00Z")
        self.assertTrue(is_replay_equivalent(first, second))

    def test_replay_differs_on_wrong_actor_decision(self):
        first = decide()
        second = decide(worker_id="worker-b")
        self.assertFalse(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
