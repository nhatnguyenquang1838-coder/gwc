from __future__ import annotations

import unittest

from tools.node_architect.cas_mismatch_recovery import decide_cas_mismatch_recovery, is_replay_equivalent

BASE = "1a27705f221d8095ce30f192b5313f108ea1e830"
HEAD = "f" * 40
SCOPE = "sha256:fbff96ebbaf33a76" + "0" * 48


def decide(**overrides):
    payload = dict(task_id="SCRUM-242", repository="nhatnguyenquang1838-coder/gwc", branch="codex/scrum-240-242-failure-recovery-m5-20260731", base_sha=BASE, head_sha=HEAD, scope_hash=SCOPE, checkpoint_id="chk-1", expected_revision=7, observed_revision=8, reload_status="VERIFIED", pending_action_status="NONE", retry_count=0, max_retries=1, observed_at="2026-07-31T00:00:00Z")
    payload.update(overrides)
    return decide_cas_mismatch_recovery(**payload)


class CasMismatchRecoveryTests(unittest.TestCase):
    def test_verified_newer_revision_retries_after_reload(self):
        result = decide()
        self.assertEqual(result["outcome"], "RETRY_AFTER_RELOAD")
        self.assertFalse(result["overwrite_allowed"])
        self.assertFalse(result["blind_retry_allowed"])

    def test_unverified_reload_requires_reload(self):
        result = decide(reload_status="UNAVAILABLE")
        self.assertEqual(result["outcome"], "RELOAD")

    def test_pending_action_reconciles(self):
        result = decide(pending_action_status="PENDING")
        self.assertEqual(result["outcome"], "RECONCILE")

    def test_regressed_revision_requires_human(self):
        result = decide(observed_revision=6)
        self.assertEqual(result["outcome"], "HUMAN_REQUIRED")

    def test_no_mismatch_is_explicit(self):
        result = decide(observed_revision=7)
        self.assertEqual(result["outcome"], "NO_MISMATCH")

    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-07-31T00:00:00Z")
        second = decide(observed_at="2026-07-31T00:03:00Z")
        self.assertTrue(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
