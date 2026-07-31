from __future__ import annotations

import unittest

from tools.node_architect.lease_expiry_recovery import decide_lease_expiry_recovery, is_replay_equivalent

BASE = "3abc72eb8dc30759e5731d0c9492b11262567f56"
HEAD = "a" * 40
SCOPE = "sha256:91d003f52727f62a" + "0" * 48


def decide(**overrides):
    payload = dict(task_id="SCRUM-243", repository="nhatnguyenquang1838-coder/gwc", branch="codex/scrum-243-lease-expiry-recovery-m5-20260731", base_sha=BASE, head_sha=HEAD, scope_hash=SCOPE, lease_id="lease-1", worker_id="worker-a", now_epoch_ms=2000, lease_expires_epoch_ms=1000, observed_fencing_token=7, worker_fencing_token=7, readback_status="VERIFIED_ZERO_EFFECT", reacquire_status="REACQUIRED_MONOTONIC", duplicate_agent_detected=False, side_effect_status="NONE", observed_at="2026-07-31T00:00:00Z")
    payload.update(overrides)
    return decide_lease_expiry_recovery(**payload)


class LeaseExpiryRecoveryTests(unittest.TestCase):
    def test_valid_lease_allows_continue_without_reacquire(self):
        result = decide(now_epoch_ms=500, lease_expires_epoch_ms=1000)
        self.assertEqual(result["outcome"], "CONTINUE")
        self.assertTrue(result["advancement_allowed"])
        self.assertFalse(result["checkpoint_required"])

    def test_expired_lease_requires_readback_before_continue(self):
        result = decide(readback_status="UNAVAILABLE")
        self.assertEqual(result["outcome"], "READBACK_REQUIRED")
        self.assertFalse(result["advancement_allowed"])
        self.assertFalse(result["side_effect_allowed"])

    def test_stale_worker_is_fenced_by_monotonic_token(self):
        result = decide(worker_fencing_token=6, observed_fencing_token=7)
        self.assertEqual(result["outcome"], "FENCE_STALE_WORKER")
        self.assertFalse(result["advancement_allowed"])

    def test_duplicate_agent_race_is_fenced(self):
        result = decide(duplicate_agent_detected=True)
        self.assertEqual(result["outcome"], "FENCE_DUPLICATE_AGENT")

    def test_unknown_side_effect_reconciles_not_retry(self):
        result = decide(side_effect_status="UNKNOWN")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertFalse(result["blind_retry_allowed"])

    def test_reacquire_required_when_monotonic_token_not_proven(self):
        result = decide(reacquire_status="NOT_REACQUIRED")
        self.assertEqual(result["outcome"], "REACQUIRE_LEASE")
        self.assertTrue(result["reacquire_required"])

    def test_reacquired_monotonic_lease_allows_continuation(self):
        result = decide()
        self.assertEqual(result["outcome"], "CONTINUE_AFTER_REACQUIRE")
        self.assertTrue(result["advancement_allowed"])
        self.assertTrue(result["side_effect_allowed"])

    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-07-31T00:00:00Z")
        second = decide(observed_at="2026-07-31T00:05:00Z")
        self.assertTrue(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
