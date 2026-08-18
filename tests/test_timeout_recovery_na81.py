from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# SCRUM-361 NA81-F8 fix: absolute tools/ path so
# `python -m unittest discover -s tests` works without PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from node_architect.timeout_recovery import decide_timeout_recovery, is_replay_equivalent

# ---------------------------------------------------------------------------
# SCRUM-361 / #296 context: failure_recovery.timeout-recovery NA81-F8 delta
# ---------------------------------------------------------------------------
SCOPE = "sha256:6b11cfc49db574e2582cc753585fd9a75154323847da94d2931afed928eee70b"
BASE = "42220b4b"
HEAD = "0" * 40
BRANCH = "auto/SCRUM-361-na81-recert-20260814-r10"


def decide(**overrides):
    payload = dict(
        task_id="SCRUM-361",
        repository="nhatnguyenquang1838-coder/gwc",
        branch=BRANCH,
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash=SCOPE,
        operation_id="op-361",
        timed_out=True,
        readback_status="VERIFIED",
        effect_status="ZERO_EFFECT",
        retry_count=0,
        max_retries=2,
        idempotency_key="idem-361",
        deadline_at="2026-08-18T14:05:00Z",
        observed_at="2026-08-18T14:00:00Z",
    )
    payload.update(overrides)
    return decide_timeout_recovery(**payload)


class TimeoutRecoveryNA81Tests(unittest.TestCase):
    # ---- Family invariant: recovery must never blind-redispatch/retry. -----
    def test_no_blind_redispatch_under_any_routing(self):
        for o in [
            decide(),
            decide(effect_status="UNKNOWN"),
            decide(effect_status="PENDING"),
            decide(effect_status="INTERRUPTED"),
            decide(readback_status="UNAVAILABLE", effect_status="ZERO_EFFECT"),
            decide(effect_status="COMMITTED"),
            decide(effect_status="FAILED"),
            decide(retry_count=2, max_retries=2),
            decide(effect_status="NONSENSE"),
        ]:
            with self.subTest(outcome=o["outcome"], reason=o["reason_code"]):
                self.assertFalse(o["blind_redispatch_allowed"])

    # ---- Requirement: zero effect with budget -> bounded retry. -----------
    def test_zero_effect_with_budget_is_bounded_retry(self):
        r = decide()
        self.assertEqual(r["outcome"], "BOUNDED_RETRY")
        self.assertEqual(r["reason_code"], "ZERO_EFFECT_WITH_RETRY_BUDGET")
        self.assertTrue(r["checkpoint_required"])

    # ---- Requirement: unknown effect -> reconcile, never retry. -----------
    def test_unknown_effect_routes_to_reconcile_not_retry(self):
        r = decide(effect_status="UNKNOWN")
        self.assertEqual(r["outcome"], "RECONCILE")
        self.assertEqual(r["reason_code"], "UNKNOWN_EXTERNAL_EFFECT")
        self.assertFalse(r["blind_redispatch_allowed"])
        self.assertTrue(r["checkpoint_required"])

    # ---- NEW: real pending effect -> reconcile before retry. -------------
    def test_real_pending_effect_reconciles_before_retry(self):
        r = decide(effect_status="PENDING")
        self.assertEqual(r["outcome"], "RECONCILE")
        self.assertEqual(r["reason_code"], "PENDING_EFFECT_RECONCILE")
        self.assertFalse(r["blind_redispatch_allowed"])
        self.assertTrue(r["checkpoint_required"])

    # ---- NEW: interruption -> reconcile (unknown external effect). --------
    def test_interruption_reconciles_unknown_effect(self):
        r = decide(effect_status="INTERRUPTED")
        self.assertEqual(r["outcome"], "RECONCILE")
        self.assertEqual(r["reason_code"], "INTERRUPTED_UNKNOWN_EFFECT")
        self.assertFalse(r["blind_redispatch_allowed"])
        self.assertTrue(r["checkpoint_required"])

    # ---- Requirement: unavailable readback -> reconcile. -----------------
    def test_unverified_readback_routes_to_reconcile(self):
        r = decide(readback_status="UNAVAILABLE", effect_status="ZERO_EFFECT")
        self.assertEqual(r["outcome"], "RECONCILE")
        self.assertEqual(r["reason_code"], "READBACK_NOT_VERIFIED")

    # ---- Requirement: committed effect -> human required. ---------------
    def test_committed_effect_requires_human(self):
        r = decide(effect_status="COMMITTED")
        self.assertEqual(r["outcome"], "HUMAN_REQUIRED")

    # ---- Requirement: readback-confirmed failure -> terminal fail. -------
    def test_failed_effect_is_terminal(self):
        r = decide(effect_status="FAILED")
        self.assertEqual(r["outcome"], "FAIL")
        self.assertEqual(r["reason_code"], "READBACK_CONFIRMED_FAILURE")

    # ---- Requirement: retryable vs exhausted retry. ----------------------
    def test_retryable_within_budget(self):
        r = decide(retry_count=1, max_retries=2)
        self.assertEqual(r["outcome"], "BOUNDED_RETRY")

    def test_exhausted_retry_budget_fails(self):
        r = decide(retry_count=2, max_retries=2)
        self.assertEqual(r["outcome"], "FAIL")
        self.assertEqual(r["reason_code"], "RETRY_BUDGET_EXHAUSTED")

    # ---- Requirement: not timed out -> wait (timeout distinguished). -----
    def test_not_timed_out_waits(self):
        r = decide(timed_out=False)
        self.assertEqual(r["outcome"], "WAIT")
        self.assertEqual(r["reason_code"], "NOT_TIMED_OUT")

    # ---- Requirement: replay equivalence + no duplicate effect. ----------
    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-08-18T14:00:00Z")
        second = decide(observed_at="2026-08-18T14:09:00Z")
        self.assertTrue(is_replay_equivalent(first, second))

    def test_replay_keeps_no_duplicate_effect_on_reconcile(self):
        # Re-deciding an identical reconcile scenario must stay reconcile and
        # never flip to a blind dispatch -> guarantees no duplicate effect.
        first = decide(effect_status="INTERRUPTED")
        second = decide(
            effect_status="INTERRUPTED",
            observed_at="2026-08-18T14:30:00Z",
        )
        self.assertTrue(is_replay_equivalent(first, second))
        self.assertEqual(second["outcome"], "RECONCILE")
        self.assertFalse(second["blind_redispatch_allowed"])

    def test_different_effect_status_not_replay_equivalent(self):
        pending = decide(effect_status="PENDING")
        interrupted = decide(effect_status="INTERRUPTED")
        self.assertFalse(is_replay_equivalent(pending, interrupted))

    # ---- Requirement: decision digest is deterministic. ------------------
    def test_decision_digest_deterministic(self):
        a = decide(effect_status="PENDING")
        b = decide(effect_status="PENDING", observed_at="2026-08-18T14:00:00Z")
        self.assertEqual(a["decision_digest"], b["decision_digest"])


if __name__ == "__main__":
    unittest.main()
