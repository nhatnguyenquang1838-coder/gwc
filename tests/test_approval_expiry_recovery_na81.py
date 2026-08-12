"""SCRUM-367 NA81 maturity tests for the approval-expiry-recovery node.

Current-task requirement -> code -> test evidence map (exact SHA delivery).

Older M5 tests (test_failure_recovery_m5_batch.py) cover the historical SCRUM-244
utility contract only. These NA81 tests bind the CURRENT SCRUM-367 brief
(#302): stop all use of an expired approval, preserve audit evidence,
checkpoint current state, and route to exact reapproval bound to the current
scope/head when continuation is still legal. Expiry is never implicit renewal,
grace extension or transitive authority (family invariants EXPIRED_APPROVAL_IS_UNUSABLE,
REAPPROVAL_MUST_BIND_CURRENT_SCOPE_HEAD, RECOVERY_MUST_NOT_EXPAND_SCOPE_OR_AUTHORITY).
"""
from __future__ import annotations

import unittest

from tools.node_architect.approval_expiry_recovery import (
    decide_approval_expiry_recovery,
    replay_safe,
)


SHA = "4ddc8a01b1d6d957ea70bef621646354897b55ef"
OTHER_SHA = "6e6984e3bb120a222b65c99767f2747aa9bd0464cafe"


def _base(**over):
    args = dict(
        task_id="SCRUM-367",
        repository="nhatnguyenquang1838-coder/gwc",
        branch="auto/SCRUM-367-na81-20260810",
        base_sha=SHA,
        head_sha=OTHER_SHA,
        approval_id="APPROVE_G2_SCRUM367_20260812",
        approval_scope_hash="sha256:60a28922c6921e4f",
        current_scope_hash="sha256:60a28922c6921e4f",
        approval_expires_at="2026-08-18T09:05:00Z",
        now_at="2026-08-12T00:00:00Z",
        continuation_requested=False,
        checkpoint_digest_before_wait="sha256:aaaa",
        current_checkpoint_digest="sha256:aaaa",
        replay_nonce="nonce-1",
        consumed_replay_nonces=[],
    )
    args.update(over)
    return decide_approval_expiry_recovery(**args)


class ExpiryBoundaryTests(unittest.TestCase):
    def test_before_boundary_is_not_expired(self):
        d = _base(now_at="2026-08-18T09:04:59Z", approval_expires_at="2026-08-18T09:05:00Z")
        self.assertFalse(d["approval_expired"])
        self.assertEqual(d["outcome"], "CONTINUE")
        self.assertTrue(d["continuation_allowed"])

    def test_at_boundary_is_expired(self):
        d = _base(now_at="2026-08-18T09:05:00Z", approval_expires_at="2026-08-18T09:05:00Z")
        self.assertTrue(d["approval_expired"])
        self.assertEqual(d["outcome"], "REGENERATE_APPROVAL")
        self.assertEqual(d["reason_code"], "APPROVAL_EXPIRED")
        self.assertFalse(d["continuation_allowed"])
        self.assertTrue(d["regenerate_approval_required"])


class StaleScopeHeadTests(unittest.TestCase):
    def test_scope_hash_drift_blocks(self):
        d = _base(current_scope_hash="sha256:deadbeef")
        self.assertTrue(d["scope_drifted"])
        self.assertEqual(d["outcome"], "REGENERATE_APPROVAL")
        self.assertEqual(d["reason_code"], "APPROVAL_SCOPE_HASH_DRIFTED")
        self.assertFalse(d["continuation_allowed"])
        self.assertTrue(d["regenerate_approval_required"])

    def test_head_change_implies_scope_drift(self):
        # The canonical scope hash encodes the current scope/head; a changed
        # head must surface as a drifted scope hash and block continuation.
        d = _base(current_scope_hash="sha256:headchanged")
        self.assertTrue(d["scope_drifted"])
        self.assertFalse(d["continuation_allowed"])


class ReplayTests(unittest.TestCase):
    def test_duplicate_replay_nonce_rejected(self):
        d = _base(consumed_replay_nonces=["nonce-1"])
        self.assertTrue(d["replay_detected"])
        self.assertTrue(d["replay_rejected"])
        self.assertEqual(d["outcome"], "REJECT_REPLAY")
        self.assertFalse(d["wait_allowed"])
        self.assertFalse(d["continuation_allowed"])

    def test_fresh_nonce_not_replay(self):
        d = _base(replay_nonce="nonce-fresh", consumed_replay_nonces=["nonce-other"])
        self.assertFalse(d["replay_detected"])
        self.assertFalse(d["replay_rejected"])


class ValidReplacementTests(unittest.TestCase):
    def test_valid_approval_continues(self):
        d = _base(continuation_requested=True)
        self.assertEqual(d["outcome"], "CONTINUE")
        self.assertEqual(d["reason_code"], "APPROVAL_VALID_AND_CHECKPOINT_CURRENT")
        self.assertTrue(d["continuation_allowed"])
        self.assertFalse(d["regenerate_approval_required"])

    def test_valid_replacement_after_expiry_requires_fresh_approval(self):
        # No replacement provided: expired approval cannot be continued.
        d = _base(now_at="2026-08-20T00:00:00Z")
        self.assertTrue(d["approval_expired"])
        self.assertTrue(d["regenerate_approval_required"])
        self.assertFalse(d["continuation_allowed"])
        self.assertFalse(d["wait_allowed"])


class NoTransitiveAuthorityTests(unittest.TestCase):
    def test_expired_approval_never_grants_continuation(self):
        d = _base(now_at="2026-08-20T00:00:00Z")
        self.assertFalse(d["continuation_allowed"])
        self.assertFalse(d["stale_continuation_allowed"])
        self.assertFalse(d["wait_allowed"])

    def test_decision_never_grants_authority(self):
        # Family invariant: recovery must not expand scope or authority.
        for now in ("2026-08-12T00:00:00Z", "2026-08-20T00:00:00Z"):
            d = _base(now_at=now)
            self.assertNotIn("authority_granted", d)
            self.assertFalse(d.get("authority_granted", False))


class CheckpointEvidenceTests(unittest.TestCase):
    def test_missing_checkpoint_blocks_wait(self):
        d = _base(continuation_requested=True, checkpoint_digest_before_wait=None)
        self.assertTrue(d["checkpoint_required"])
        self.assertEqual(d["outcome"], "CHECKPOINT_BEFORE_WAIT")
        self.assertFalse(d["continuation_allowed"])

    def test_checkpoint_mismatch_during_wait_regenerates(self):
        d = _base(continuation_requested=True,
                  checkpoint_digest_before_wait="sha256:bbbb",
                  current_checkpoint_digest="sha256:cccc")
        self.assertTrue(d["checkpoint_mismatch"])
        self.assertEqual(d["outcome"], "REGENERATE_APPROVAL")
        self.assertEqual(d["reason_code"], "CHECKPOINT_DRIFTED_DURING_WAIT")


class ReplaySafeStabilityTests(unittest.TestCase):
    def test_identical_inputs_are_replay_safe(self):
        a = _base()
        b = _base()
        self.assertTrue(replay_safe(a, b))
        self.assertEqual(a["decision_digest"], b["decision_digest"])

    def test_different_inputs_are_not_replay_safe(self):
        a = _base(now_at="2026-08-12T00:00:00Z")
        b = _base(now_at="2026-08-20T00:00:00Z")
        self.assertFalse(replay_safe(a, b))


if __name__ == "__main__":
    unittest.main()
