from __future__ import annotations

import unittest

from tools.node_architect.stale_session_reconciliation import decide_stale_session_reconciliation, is_replay_equivalent

BASE = "1a27705f221d8095ce30f192b5313f108ea1e830"
HEAD = "d" * 40
SCOPE = "sha256:90956a9b6d2961b4" + "0" * 48


def decide(**overrides):
    payload = dict(task_id="SCRUM-240", repository="nhatnguyenquang1838-coder/gwc", branch="codex/scrum-240-242-failure-recovery-m5-20260731", base_sha=BASE, head_sha=HEAD, scope_hash=SCOPE, session_id="s-1", observed_owner="agent-a", canonical_owner="agent-a", observed_checkpoint_rev=7, canonical_checkpoint_rev=7, lease_status="ACTIVE", working_tree_status="CLEAN", pending_action_status="NONE", observed_at="2026-07-31T00:00:00Z")
    payload.update(overrides)
    return decide_stale_session_reconciliation(**payload)


class StaleSessionReconciliationTests(unittest.TestCase):
    def test_current_session_can_continue(self):
        result = decide()
        self.assertEqual(result["outcome"], "CONTINUE")
        self.assertTrue(result["advance_allowed"])

    def test_stale_owner_supersedes(self):
        result = decide(observed_owner="agent-old", canonical_owner="agent-new")
        self.assertEqual(result["outcome"], "SUPERSEDE")
        self.assertFalse(result["advance_allowed"])

    def test_stale_checkpoint_supersedes(self):
        result = decide(observed_checkpoint_rev=3, canonical_checkpoint_rev=7)
        self.assertEqual(result["outcome"], "SUPERSEDE")

    def test_dirty_worktree_reconciles(self):
        result = decide(working_tree_status="DIRTY")
        self.assertEqual(result["outcome"], "RECONCILE")

    def test_future_checkpoint_requires_human(self):
        result = decide(observed_checkpoint_rev=9, canonical_checkpoint_rev=7)
        self.assertEqual(result["outcome"], "HUMAN_REQUIRED")

    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-07-31T00:00:00Z")
        second = decide(observed_at="2026-07-31T00:01:00Z")
        self.assertTrue(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
