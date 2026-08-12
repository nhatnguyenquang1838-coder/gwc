from __future__ import annotations

import os
import sys
import unittest

# SCRUM-323 import-path lesson: insert the absolute tools/ dir into sys.path[0]
# so `node_architect` (a namespace package, no __init__.py) is importable under
# CI `python -m unittest discover` from the repo root on Python 3.12.
TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from node_architect.timeout_recovery import decide_timeout_recovery, is_replay_equivalent  # noqa: E402

BASE = "3b0938065e71e699d327d041f5b6023ed30a29dc"
HEAD = "d" * 40
SCOPE = "sha256:3123425c4076103ca579c6757f46e37b81e55d4096213735d8dd8159b67bc2ea"


def decide(**overrides):
    payload = dict(
        task_id="SCRUM-361", repository="nhatnguyenquang1838-coder/gwc",
        branch="auto/SCRUM-361-na81-20260810", base_sha=BASE, head_sha=HEAD,
        scope_hash=SCOPE, operation_id="op-361", timed_out=True,
        readback_status="VERIFIED", effect_status="ZERO_EFFECT",
        retry_count=0, max_retries=2, idempotency_key="idem-361",
        deadline_at="2026-08-12T14:05:00Z", observed_at="2026-08-12T14:00:00Z",
    )
    payload.update(overrides)
    return decide_timeout_recovery(**payload)


class TimeoutRecoveryNA81Tests(unittest.TestCase):
    # --- brief: "real pending" is distinct from timeout/terminal failure ---
    def test_real_pending_routes_to_wait_not_reconcile(self):
        result = decide(effect_status="PENDING")
        self.assertEqual(result["outcome"], "WAIT")
        self.assertEqual(result["reason_code"], "REAL_PENDING_AWAIT_READBACK")
        self.assertTrue(result["checkpoint_required"])
        self.assertFalse(result["blind_redispatch_allowed"])

    # --- brief: "interruption" must not blind-redispatch (no duplicate effect) ---
    def test_interruption_blocks_bounded_retry(self):
        result = decide(effect_status="ZERO_EFFECT", interruption_detected=True)
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "INTERRUPTION_REQUIRES_RECHECK")
        self.assertTrue(result["interruption_detected"])

    def test_interruption_blocks_pending_poll(self):
        result = decide(effect_status="PENDING", interruption_detected=True)
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "INTERRUPTION_REQUIRES_RECHECK")

    def test_interruption_keeps_confirmed_failure_terminal(self):
        result = decide(effect_status="FAILED", interruption_detected=True)
        self.assertEqual(result["outcome"], "FAIL")
        self.assertEqual(result["reason_code"], "READBACK_CONFIRMED_FAILURE")

    # --- brief: "retryable/exhausted retry" ---
    def test_retryable_has_budget(self):
        self.assertEqual(decide(retry_count=0)["outcome"], "BOUNDED_RETRY")
        self.assertEqual(decide(retry_count=1)["outcome"], "BOUNDED_RETRY")

    def test_exhausted_retry_fails(self):
        result = decide(retry_count=2, max_retries=2)
        self.assertEqual(result["outcome"], "FAIL")
        self.assertEqual(result["reason_code"], "RETRY_BUDGET_EXHAUSTED")

    # --- brief: "unknown effect" routes to reconcile, never retry ---
    def test_unknown_effect_reconciles(self):
        result = decide(effect_status="UNKNOWN")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "UNKNOWN_EXTERNAL_EFFECT")

    # --- brief: "unavailable readback" ---
    def test_unavailable_readback_reconciles(self):
        result = decide(readback_status="UNAVAILABLE")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "READBACK_NOT_VERIFIED")

    # --- brief: "replay / no duplicate effect" ---
    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-08-12T14:00:00Z")
        second = decide(observed_at="2026-08-12T14:01:00Z")
        self.assertTrue(is_replay_equivalent(first, second))

    def test_distinct_decisions_are_not_replay_equivalent(self):
        a = decide(effect_status="ZERO_EFFECT")
        b = decide(effect_status="FAILED")
        self.assertFalse(is_replay_equivalent(a, b))


if __name__ == "__main__":
    unittest.main()
