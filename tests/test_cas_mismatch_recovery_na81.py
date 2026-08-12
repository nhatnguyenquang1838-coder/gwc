from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# SCRUM-323 fix: absolute tools/ path so `python -m unittest discover -s tests`
# works without PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from node_architect.cas_mismatch_recovery import decide_cas_mismatch_recovery, is_replay_equivalent

# ---------------------------------------------------------------------------
# SCRUM-365 / #300 context: failure_recovery.cas-mismatch-recovery NA81 delta
# ---------------------------------------------------------------------------
SCOPE = "sha256:fbff96ebbaf33a76" + "0" * 48
BASE = "1a27705f221d8095ce30f192b5313f108ea1e830"
HEAD = "f" * 40
BRANCH = "auto/SCRUM-365-na81-20260810"


def decide(**overrides):
    payload = dict(
        task_id="SCRUM-365",
        repository="nhatnguyenquang1838-coder/gwc",
        branch=BRANCH,
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash=SCOPE,
        checkpoint_id="chk-365",
        expected_revision=7,
        observed_revision=8,
        reload_status="VERIFIED",
        pending_action_status="NONE",
        retry_count=0,
        max_retries=2,
        observed_at="2026-08-12T00:00:00Z",
    )
    payload.update(overrides)
    return decide_cas_mismatch_recovery(**payload)


class CasMismatchRecoveryNA81Tests(unittest.TestCase):
    # Family invariant: recovery never expands authority and never overwrites.
    def test_no_write_or_blind_retry_under_any_routing(self):
        for o in [
            decide(),
            decide(reload_status="UNAVAILABLE"),
            decide(plan_status="STALE"),
            decide(pending_action_status="PENDING"),
            decide(retry_count=2, max_retries=2),
            decide(observed_revision=6),
            decide(actor_id="agent-b", expected_actor_id="agent-a"),
        ]:
            with self.subTest(outcome=o["outcome"]):
                self.assertFalse(o["overwrite_allowed"])
                self.assertFalse(o["blind_retry_allowed"])

    # Requirement: mismatch with newer compatible state -> deterministic retry after reload.
    def test_newer_compatible_state_retries_after_reload(self):
        r = decide()
        self.assertEqual(r["outcome"], "RETRY_AFTER_RELOAD")
        self.assertTrue(r["authoritative_reread_required"])
        # A checkpoint is captured before the retry write (matches prior semantics).
        self.assertTrue(r["checkpoint_required"])

    # Requirement: conflicting state (reload unavailable) -> authoritative re-read required.
    def test_conflicting_state_requires_reload(self):
        r = decide(reload_status="UNAVAILABLE")
        self.assertEqual(r["outcome"], "RELOAD")
        self.assertTrue(r["authoritative_reread_required"])
        self.assertTrue(r["checkpoint_required"])

    # Requirement: stale actor MUST NOT overwrite newer canonical state.
    def test_stale_actor_denied(self):
        r = decide(actor_id="agent-b", expected_actor_id="agent-a")
        self.assertEqual(r["outcome"], "STALE_WRITER_DENIED")
        self.assertTrue(r["stale_writer_denied"])
        self.assertFalse(r["overwrite_allowed"])
        self.assertTrue(r["checkpoint_required"])

    # Requirement: mismatched fence token is also a stale writer.
    def test_stale_fence_denied(self):
        r = decide(fence_token="tok-b", expected_fence_token="tok-a")
        self.assertEqual(r["outcome"], "STALE_WRITER_DENIED")

    # Stale-writer denial takes precedence over revision logic (even when revisions match).
    def test_stale_writer_precedence_over_matching_revision(self):
        r = decide(observed_revision=7, actor_id="agent-b", expected_actor_id="agent-a")
        self.assertEqual(r["outcome"], "STALE_WRITER_DENIED")

    # Requirement: after authoritative re-read, a stale plan must REPLAN, not blind-retry.
    def test_plan_stale_replans(self):
        r = decide(plan_status="STALE")
        self.assertEqual(r["outcome"], "REPLAN")
        self.assertTrue(r["authoritative_reread_required"])
        self.assertTrue(r["checkpoint_required"])

    # Requirement: repeated mismatch consumes retry budget then fails.
    def test_repeated_mismatch_exhausts_budget(self):
        r = decide(retry_count=2, max_retries=2)
        self.assertEqual(r["outcome"], "FAIL")
        r2 = decide(retry_count=1, max_retries=2)
        self.assertEqual(r2["outcome"], "RETRY_AFTER_RELOAD")

    # Requirement: regressed observed revision is unsafe -> human.
    def test_regressed_revision_requires_human(self):
        r = decide(observed_revision=6)
        self.assertEqual(r["outcome"], "HUMAN_REQUIRED")

    # Requirement: pending/unconfirmed action requires reconcile readback.
    def test_pending_action_reconciles(self):
        r = decide(pending_action_status="PENDING")
        self.assertEqual(r["outcome"], "RECONCILE")

    # Requirement: explicit NO_MISMATCH when revisions agree (no re-read needed).
    def test_no_mismatch_is_explicit(self):
        r = decide(observed_revision=7)
        self.assertEqual(r["outcome"], "NO_MISMATCH")
        self.assertFalse(r["authoritative_reread_required"])

    # Requirement: concurrency replay equivalence ignores observation time but not actor.
    def test_concurrency_replay_equivalent(self):
        first = decide(observed_at="2026-08-12T00:00:00Z")
        second = decide(observed_at="2026-08-12T00:05:00Z")
        self.assertTrue(is_replay_equivalent(first, second))
        different_actor = decide(actor_id="agent-x")
        self.assertFalse(is_replay_equivalent(first, different_actor))


if __name__ == "__main__":
    unittest.main()
