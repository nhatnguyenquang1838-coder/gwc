from __future__ import annotations

import unittest

from tools.node_architect.crash_checkpoint_recovery import (
    decide_crash_checkpoint_recovery,
    is_replay_equivalent,
)

BASE = "b9c6dddf3da4394cc0f3d52e030aeaecf4f5d380"
HEAD = "e" * 40
SCOPE = "sha256:42793641d2d5dd38000000000000000000000000000000000000000000000000"


def decide(**overrides):
    payload = dict(
        task_id="SCRUM-239",
        repository="nhatnguyenquang1838-coder/gwc",
        branch="codex/scrum-239-crash-checkpoint-recovery-m5-20260730",
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash=SCOPE,
        run_id="run-239",
        checkpoint_id="checkpoint-1",
        checkpoint_revision=3,
        checkpoint_status="CANONICAL",
        pending_action_status="IN_FLIGHT",
        readback_status="VERIFIED",
        effect_status="ZERO_EFFECT",
        idempotency_key="idem-239",
        resume_token="resume-239",
        observed_at="2026-07-30T17:00:00Z",
    )
    payload.update(overrides)
    return decide_crash_checkpoint_recovery(**payload)


class CrashCheckpointRecoveryTests(unittest.TestCase):
    def test_zero_effect_pending_action_can_resume_without_duplicate_effect(self):
        result = decide()
        self.assertEqual(result["outcome"], "RESUME")
        self.assertEqual(result["reason_code"], "PENDING_ACTION_ZERO_EFFECT")
        self.assertTrue(result["checkpoint_required"])
        self.assertTrue(result["readback_required_before_effect"])
        self.assertTrue(result["duplicate_effect_allowed"])

    def test_unknown_effect_after_crash_routes_to_reconcile(self):
        result = decide(effect_status="UNKNOWN")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "UNKNOWN_EXTERNAL_EFFECT_AFTER_CRASH")
        self.assertFalse(result["duplicate_effect_allowed"])

    def test_committed_pending_action_requires_human(self):
        result = decide(effect_status="COMMITTED")
        self.assertEqual(result["outcome"], "HUMAN_REQUIRED")
        self.assertEqual(result["reason_code"], "PENDING_ACTION_MAY_HAVE_COMMITTED")
        self.assertFalse(result["duplicate_effect_allowed"])

    def test_noncanonical_checkpoint_reconciles(self):
        result = decide(checkpoint_status="STALE")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "CHECKPOINT_NOT_CANONICAL")
        self.assertFalse(result["duplicate_effect_allowed"])

    def test_readback_unavailable_reconciles_before_resume(self):
        result = decide(readback_status="UNAVAILABLE", effect_status="ZERO_EFFECT")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "READBACK_NOT_VERIFIED")
        self.assertFalse(result["duplicate_effect_allowed"])

    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-07-30T17:00:00Z")
        second = decide(observed_at="2026-07-30T17:05:00Z")
        self.assertTrue(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
