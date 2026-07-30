from __future__ import annotations

import unittest

from tools.node_architect.unknown_write_reconciliation import decide_unknown_write_reconciliation, is_replay_equivalent

BASE = "1a27705f221d8095ce30f192b5313f108ea1e830"
HEAD = "e" * 40
SCOPE = "sha256:af7096196898770c" + "0" * 48


def decide(**overrides):
    payload = dict(task_id="SCRUM-241", repository="nhatnguyenquang1838-coder/gwc", branch="codex/scrum-240-242-failure-recovery-m5-20260731", base_sha=BASE, head_sha=HEAD, scope_hash=SCOPE, operation_id="op-1", provider_readback_status="VERIFIED", external_effect_status="ZERO_EFFECT", idempotency_key="idem-1", retry_count=0, max_retries=1, pending_action_recorded=True, observed_at="2026-07-31T00:00:00Z")
    payload.update(overrides)
    return decide_unknown_write_reconciliation(**payload)


class UnknownWriteReconciliationTests(unittest.TestCase):
    def test_zero_effect_with_budget_routes_bounded_retry(self):
        result = decide()
        self.assertEqual(result["outcome"], "BOUNDED_RETRY")
        self.assertFalse(result["blind_retry_allowed"])

    def test_unknown_effect_reconciles_not_retry(self):
        result = decide(external_effect_status="UNKNOWN")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertFalse(result["blind_retry_allowed"])

    def test_missing_pending_action_evidence_reconciles(self):
        result = decide(pending_action_recorded=False)
        self.assertEqual(result["outcome"], "RECONCILE")

    def test_committed_write_requires_human(self):
        result = decide(external_effect_status="COMMITTED")
        self.assertEqual(result["outcome"], "HUMAN_REQUIRED")

    def test_retry_budget_exhaustion_fails(self):
        result = decide(retry_count=1, max_retries=1)
        self.assertEqual(result["outcome"], "FAIL")

    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-07-31T00:00:00Z")
        second = decide(observed_at="2026-07-31T00:02:00Z")
        self.assertTrue(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
