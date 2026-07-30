from __future__ import annotations

import unittest

from tools.node_architect.timeout_recovery import decide_timeout_recovery, is_replay_equivalent

BASE = "3b0938065e71e699d327d041f5b6023ed30a29dc"
HEAD = "d" * 40
SCOPE = "sha256:3123425c4076103ca579c6757f46e37b81e55d4096213735d8dd8159b67bc2ea"


def decide(**overrides):
    payload = dict(task_id="SCRUM-238", repository="nhatnguyenquang1838-coder/gwc", branch="codex/scrum-238-timeout-recovery-m5-fastlane-r3-20260730", base_sha=BASE, head_sha=HEAD, scope_hash=SCOPE, operation_id="op-1", timed_out=True, readback_status="VERIFIED", effect_status="ZERO_EFFECT", retry_count=0, max_retries=2, idempotency_key="idem-1", deadline_at="2026-07-30T14:05:00Z", observed_at="2026-07-30T14:00:00Z")
    payload.update(overrides)
    return decide_timeout_recovery(**payload)


class TimeoutRecoveryTests(unittest.TestCase):
    def test_zero_effect_with_budget_is_bounded_retry(self):
        result = decide()
        self.assertEqual(result["outcome"], "BOUNDED_RETRY")
        self.assertEqual(result["reason_code"], "ZERO_EFFECT_WITH_RETRY_BUDGET")
        self.assertFalse(result["blind_redispatch_allowed"])
        self.assertTrue(result["checkpoint_required"])

    def test_unknown_effect_routes_to_reconcile_not_retry(self):
        result = decide(effect_status="UNKNOWN")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "UNKNOWN_EXTERNAL_EFFECT")
        self.assertFalse(result["blind_redispatch_allowed"])

    def test_unverified_readback_routes_to_reconcile(self):
        result = decide(readback_status="UNAVAILABLE", effect_status="ZERO_EFFECT")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "READBACK_NOT_VERIFIED")

    def test_committed_effect_requires_human(self):
        result = decide(effect_status="COMMITTED")
        self.assertEqual(result["outcome"], "HUMAN_REQUIRED")

    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-07-30T14:00:00Z")
        second = decide(observed_at="2026-07-30T14:01:00Z")
        self.assertTrue(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
