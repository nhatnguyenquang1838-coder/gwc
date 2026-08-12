"""SCRUM-323 (current NA81) tests: deterministic Draft->Ready for Review promotion.

Current-task requirement->code->test mapping on exact SHA. Historical SCRUM-200
logic is reuse evidence only; the current brief (SCRUM-323 / GitHub #258) requires
promotion to Ready ONLY when G3 PASS + required CI green + no blockers + same exact
head, failing closed otherwise, and granting no merge authority.
"""
import os
import sys
import unittest

# Make the `node_architect` package importable under multiple run contexts:
#  - `PYTHONPATH=tools python -m unittest ...`  (local dev)
#  - `python -m unittest discover` from repo root (CI, Python 3.12 namespace pkgs)
# Insert the absolute tools/ dir so `import node_architect` resolves.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

from node_architect.promotion_controller import (
    promote_to_ready_for_review,
    autonomous_main_action_allowed,
)

HEAD = "a" * 40
OTHER = "b" * 40


class PromoteReadyForReviewNA81Tests(unittest.TestCase):
    def _good(self, **kw):
        base = dict(promotion_id="P323", head_sha=HEAD, reviewed_head_sha=HEAD,
                    g3_conclusion="pass", required_ci_conclusion="success",
                    blockers=[], draft=True, pr_open=True)
        base.update(kw)
        return promote_to_ready_for_review(**base)

    # valid promotion
    def test_valid_promotion(self):
        r = self._good()
        self.assertEqual(r["outcome"], "READY")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_PROMOTED")
        self.assertEqual(r["action"], "MARK_READY_FOR_REVIEW")
        self.assertFalse(r["main_merge_allowed"])

    def test_no_merge_authority(self):
        r = self._good()
        self.assertNotIn("main_merge_allowed", {True})
        self.assertFalse(r["main_merge_allowed"])

    # mixed / stale head
    def test_mixed_head_blocked(self):
        r = self._good(reviewed_head_sha=OTHER)
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_MIXED_HEAD")
        self.assertEqual(r["observed_head"], HEAD)
        self.assertEqual(r["reviewed_head"], OTHER)

    def test_invalid_sha_blocked(self):
        r = self._good(head_sha="short")
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_SHA_INVALID")

    # not a draft PR
    def test_not_draft_blocked(self):
        r = self._good(draft=False)
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_NOT_DRAFT_PR")

    def test_pr_closed_blocked(self):
        r = self._good(pr_open=False)
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_NOT_DRAFT_PR")

    # stale / pending G3
    def test_stale_g3_blocked(self):
        r = self._good(g3_conclusion="failure")
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_G3_NOT_PASS")

    def test_g3_pending(self):
        r = self._good(g3_conclusion="in_progress")
        self.assertEqual(r["outcome"], "PENDING")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_G3_NOT_PASS")

    # CI fail / pending
    def test_ci_fail_blocked(self):
        r = self._good(required_ci_conclusion="failure")
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_CI_NOT_GREEN")

    def test_ci_pending(self):
        r = self._good(required_ci_conclusion="queued")
        self.assertEqual(r["outcome"], "PENDING")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_CI_NOT_GREEN")

    def test_ci_unavailable_blocked(self):
        r = self._good(required_ci_conclusion="")
        self.assertEqual(r["outcome"], "PENDING")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_CI_NOT_GREEN")

    # blocker present
    def test_blocker_present(self):
        r = self._good(blockers=["SCRUM-321", "SCRUM-342"])
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_BLOCKER_PRESENT")
        self.assertEqual(r["blockers"], ["SCRUM-321", "SCRUM-342"])

    # idempotent replay of already-Ready
    def test_already_ready_replay(self):
        first = self._good()
        r = self._good(existing_ready=first)
        self.assertEqual(r["outcome"], "READY")
        self.assertEqual(r["reason_code"], "AUTONOMOUS_READY_REPLAY")
        self.assertEqual(r["action"], "READBACK_READY_PR")
        self.assertEqual(r["idempotency_key"], first["idempotency_key"])

    # action gate
    def test_mark_ready_action_allowed(self):
        self.assertTrue(autonomous_main_action_allowed("mark_ready_for_review"))
        self.assertFalse(autonomous_main_action_allowed("merge"))


if __name__ == "__main__":
    unittest.main()
