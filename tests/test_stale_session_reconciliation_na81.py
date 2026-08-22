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

from node_architect.stale_session_reconciliation import (  # noqa: E402
    decide_stale_session_reconciliation,
    is_replay_equivalent,
)

BASE = "1a27705f221d8095ce30f192b5313f108ea1e830"
HEAD = "d" * 40
SCOPE = "sha256:90956a9b6d2961b4" + "0" * 48


def decide(**overrides):
    payload = dict(
        task_id="SCRUM-363", repository="nhatnguyenquang1838-coder/gwc",
        branch="auto/SCRUM-363-na81-20260810", base_sha=BASE, head_sha=HEAD,
        scope_hash=SCOPE, session_id="s-363", observed_owner="agent-a",
        canonical_owner="agent-a", observed_checkpoint_rev=7,
        canonical_checkpoint_rev=7, lease_status="ACTIVE",
        working_tree_status="CLEAN", pending_action_status="NONE",
        observed_at="2026-08-12T00:00:00Z",
    )
    payload.update(overrides)
    return decide_stale_session_reconciliation(**payload)


class StaleSessionReconciliationNA81Tests(unittest.TestCase):
    # --- brief: "stale base/head" ---
    def test_stale_base_supersedes(self):
        result = decide(observed_base_sha="aaa", canonical_base_sha="bbb")
        self.assertEqual(result["outcome"], "SUPERSEDE")
        self.assertTrue(result["stale_base"])
        self.assertTrue(result["rebind_to_canonical"])

    def test_stale_head_supersedes(self):
        result = decide(observed_head_sha="ccc", canonical_head_sha="ddd")
        self.assertEqual(result["outcome"], "SUPERSEDE")
        self.assertTrue(result["stale_head"])
        self.assertTrue(result["rebind_to_canonical"])

    def test_current_base_head_continues(self):
        result = decide(observed_base_sha=BASE, canonical_base_sha=BASE,
                        observed_head_sha=HEAD, canonical_head_sha=HEAD)
        self.assertEqual(result["outcome"], "CONTINUE")
        self.assertFalse(result["stale_base"])
        self.assertFalse(result["stale_head"])

    # --- brief: "expired/wrong lease" ---
    def test_expired_lease_supersedes(self):
        result = decide(lease_status="EXPIRED")
        self.assertEqual(result["outcome"], "SUPERSEDE")

    def test_missing_lease_supersedes(self):
        result = decide(lease_status="MISSING")
        self.assertEqual(result["outcome"], "SUPERSEDE")

    # --- brief: "stale checkpoint" ---
    def test_stale_checkpoint_supersedes(self):
        result = decide(observed_checkpoint_rev=3, canonical_checkpoint_rev=7)
        self.assertEqual(result["outcome"], "SUPERSEDE")
        self.assertTrue(result["stale_checkpoint"])

    # --- brief: "foreign dirty files" ---
    def test_foreign_dirty_files_reconcile(self):
        result = decide(working_tree_status="DIRTY")
        self.assertEqual(result["outcome"], "RECONCILE")
        self.assertEqual(result["reason_code"], "WORKING_TREE_NOT_CLEAN")

    # --- brief: "conflicting session" (foreign owner held under active lease) ---
    def test_conflicting_session_supersedes(self):
        result = decide(observed_owner="agent-old", canonical_owner="agent-new",
                        lease_status="ACTIVE")
        self.assertEqual(result["outcome"], "SUPERSEDE")
        self.assertTrue(result["stale_owner"])
        self.assertTrue(result["rebind_to_canonical"])

    # --- brief: "safe rebind" ---
    def test_safe_rebind_allowed_only_on_supersede(self):
        stale = decide(observed_owner="agent-old", canonical_owner="agent-new")
        self.assertTrue(stale["rebind_to_canonical"])
        current = decide()
        self.assertFalse(current["rebind_to_canonical"])

    # --- brief: "replay" ---
    def test_replay_equivalent_ignores_observation_time(self):
        first = decide(observed_at="2026-08-12T00:00:00Z")
        second = decide(observed_at="2026-08-12T00:01:00Z")
        self.assertTrue(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
