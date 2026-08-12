"""NA81 current-task tests for SCRUM-362 (failure_recovery.crash-checkpoint-recovery).

These tests validate the current brief's additional requirements that are NOT
proven by the historical SCRUM-239 test suite:
- SCRUM-362 / pre-prod / R4 binding (not SCRUM-239)
- missing resume_token/head_sha/checkpoint_id blocks recovery (BLOCKED)
- observed head drift reconciles before replay
- partial checkpoint and partial-crash pending-action reconcile
- invalid checkpoint revision still fails closed
- unknown effect / readback unavailable reconcile (current-task binding)
- duplicate replay equivalence on current evidence
- blocked/human-required routes never allow duplicate effects
"""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from node_architect.crash_checkpoint_recovery import (
    decide_crash_checkpoint_recovery,
    is_replay_equivalent,
)

TASK = "SCRUM-362"
REPO = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-362-na81-20260810"
BASE = "dfbd831dd2d455fdedeec752390f082d200d6f6c"
HEAD = "a" * 40
SCOPE = "sha256:60a28922c6921e4fe6172aebef5a10a48f419427da132dc3e41f60c0856bcfa3"


def decide(**overrides):
    payload = dict(
        task_id=TASK,
        repository=REPO,
        branch=BRANCH,
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash=SCOPE,
        run_id="SCRUM-288-NA81-20260811-R4",
        checkpoint_id="checkpoint-362-1",
        checkpoint_revision=1,
        checkpoint_status="CANONICAL",
        pending_action_status="NONE",
        readback_status="VERIFIED",
        effect_status="ZERO_EFFECT",
        idempotency_key="idem-362",
        resume_token="resume-362",
    )
    payload.update(overrides)
    return decide_crash_checkpoint_recovery(**payload)


class CrashCheckpointRecoveryNa81Tests(unittest.TestCase):
    def test_clean_resume_with_no_pending_action(self):
        result = decide()
        self.assertEqual(result["outcome"], "RESUME")
        self.assertEqual(result["reason_code"], "NO_PENDING_ACTION")
        self.assertTrue(result["checkpoint_required"])
        self.assertTrue(result["readback_required_before_effect"])
        # No prior effect to duplicate, so duplicate effect is allowed (safe no-op resume)
        self.assertTrue(result["duplicate_effect_allowed"])

    def test_missing_resume_token_blocks_recovery(self):
        result = decide(resume_token="")
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "MISSING_RESUME_TOKEN")

    def test_missing_head_sha_blocks_recovery(self):
        result = decide(head_sha="")
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "MISSING_HEAD_SHA")

    def test_invalid_checkpoint_id_blocks_recovery(self):
        result = decide(checkpoint_id="")
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertEqual(result["reason_code"], "INVALID_CHECKPOINT_ID")

    def test_head_drift_reconciles_before_replay(self):
        result = decide(observed_head_sha="b" * 40)
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "HEAD_DRIFT")
        self.assertFalse(result["duplicate_effect_allowed"])

    def test_partial_checkpoint_reconciles(self):
        result = decide(checkpoint_status="PARTIAL")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "PARTIAL_CHECKPOINT")

    def test_partial_crash_pending_action_reconciles(self):
        result = decide(pending_action_status="PARTIAL")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "PARTIAL_CRASH_PENDING_ACTION")

    def test_unknown_prior_effect_reconciles(self):
        result = decide(
            pending_action_status="IN_FLIGHT",
            effect_status="UNKNOWN",
        )
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "UNKNOWN_EXTERNAL_EFFECT_AFTER_CRASH")
        self.assertFalse(result["duplicate_effect_allowed"])

    def test_committed_pending_requires_human(self):
        result = decide(
            pending_action_status="IN_FLIGHT",
            effect_status="COMMITTED",
        )
        self.assertEqual(result["outcome"], "HUMAN_REQUIRED")
        self.assertEqual(result["reason_code"], "PENDING_ACTION_MAY_HAVE_COMMITTED")
        self.assertFalse(result["duplicate_effect_allowed"])

    def test_invalid_checkpoint_revision_fails_closed(self):
        result = decide(checkpoint_revision=-1)
        self.assertEqual(result["outcome"], "FAIL")
        self.assertEqual(result["reason_code"], "INVALID_CHECKPOINT_REVISION")

    def test_readback_unverified_reconciles_before_resume(self):
        result = decide(
            pending_action_status="IN_FLIGHT",
            readback_status="UNAVAILABLE",
            effect_status="ZERO_EFFECT",
        )
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "READBACK_NOT_VERIFIED")

    def test_duplicate_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-08-11T23:00:00Z")
        second = decide(observed_at="2026-08-11T23:05:00Z")
        self.assertTrue(is_replay_equivalent(first, second))

    def test_blocked_route_never_allows_duplicate_effect(self):
        result = decide(resume_token="")
        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertFalse(result["duplicate_effect_allowed"])
        self.assertTrue(result["checkpoint_required"])
        self.assertTrue(result["readback_required_before_effect"])

    def test_confirmed_failed_pending_action_fails(self):
        result = decide(
            pending_action_status="IN_FLIGHT",
            effect_status="FAILED",
        )
        self.assertEqual(result["outcome"], "FAIL")
        self.assertEqual(result["reason_code"], "PENDING_ACTION_CONFIRMED_FAILED")


if __name__ == "__main__":
    unittest.main()
