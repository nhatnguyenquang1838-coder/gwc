from __future__ import annotations
import os
import sys
import unittest

# SCRUM-323 lesson: insert absolute tools/ into sys.path[0] so CI
# `python -m unittest discover` from repo root can import node_architect
# (Python 3.12 namespace packages make only `tools` importable).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

from node_architect.validate_node_catalog_repo_delivery import decide_pr_blocker_check

REPO = "nhatnguyenquang1838-coder/gwc"
HEAD = "a" * 40
STALE = "b" * 40


class RepoDeliveryPrBlockerCheckNA81Tests(unittest.TestCase):
    """NA81 delta for SCRUM-324: PENDING_RETRY, HUMAN_REQUIRED, and
    no-merge-authority proof on the exact current task brief.

    Historical SCRUM-201 M5 tests are retained separately; this file proves
    the current NA81 requirement→code→test evidence map.
    """

    # --- helpers ---

    def _clear_evidence(self, **kw):
        d = dict(repository=REPO, pr_number=1, head_sha=HEAD,
                 pr={"state": "open", "draft": False, "head_sha": HEAD,
                     "mergeable": True, "merged": False},
                 required_checks=[{"head_sha": HEAD, "status": "completed",
                                   "conclusion": "success"}],
                 review_threads=[{"resolved": True}],
                 reviews=[{"author": "reviewer", "state": "APPROVED",
                           "head_sha": HEAD}])
        d.update(kw)
        return decide_pr_blocker_check(d)

    # --- existing CLEAR path (regression guard) ---

    def test_clear_when_pr_clean(self):
        r = self._clear_evidence()
        self.assertEqual(r["outcome"], "CLEAR")
        self.assertFalse(r["merge_authority_granted"])

    # --- CI pending / non-terminal → PENDING_RETRY ---

    def test_ci_pending_returns_pending_retry(self):
        r = self._clear_evidence(
            required_checks=[{"head_sha": HEAD, "status": "in_progress",
                              "conclusion": "pending"}])
        self.assertEqual(r["outcome"], "PENDING_RETRY")
        self.assertIn("CHECK_NON_TERMINAL", r["reason_codes"])
        self.assertFalse(r["merge_authority_granted"])

    def test_ci_queued_returns_pending_retry(self):
        r = self._clear_evidence(
            required_checks=[{"head_sha": HEAD, "status": "queued",
                              "conclusion": ""}])
        self.assertEqual(r["outcome"], "PENDING_RETRY")
        self.assertIn("CHECK_NON_TERMINAL", r["reason_codes"])

    def test_ci_unavailable_returns_pending_retry(self):
        r = self._clear_evidence(required_checks=[])
        self.assertEqual(r["outcome"], "PENDING_RETRY")
        self.assertIn("REQUIRED_CHECKS_MISSING", r["reason_codes"])

    def test_ci_failure_returns_blocked(self):
        r = self._clear_evidence(
            required_checks=[{"head_sha": HEAD, "status": "completed",
                              "conclusion": "failure"}])
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertIn("CHECK_NOT_SUCCESSFUL", r["reason_codes"])

    # --- unsupported reviewer → HUMAN_REQUIRED ---

    def test_unsupported_reviewer_returns_human_required(self):
        r = self._clear_evidence(
            reviews=[{"author": "", "state": "APPROVED", "head_sha": HEAD}])
        self.assertEqual(r["outcome"], "HUMAN_REQUIRED")
        self.assertIn("UNSUPPORTED_REVIEWER", r["reason_codes"])
        self.assertFalse(r["merge_authority_granted"])

    def test_no_reviews_returns_human_required(self):
        r = self._clear_evidence(reviews=[])
        self.assertEqual(r["outcome"], "HUMAN_REQUIRED")
        self.assertIn("UNSUPPORTED_REVIEWER", r["reason_codes"])

    # --- stale / mixed-head evidence → BLOCKED ---

    def test_stale_check_returns_blocked(self):
        r = self._clear_evidence(
            required_checks=[{"head_sha": STALE, "status": "completed",
                              "conclusion": "success"}])
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertIn("STALE_CHECK_IGNORED", r["reason_codes"])

    def test_head_sha_mismatch_returns_blocked(self):
        r = self._clear_evidence(pr={"state": "open", "draft": False,
                                     "head_sha": STALE, "mergeable": True,
                                     "merged": False})
        self.assertEqual(r["outcome"], "BLOCKED")
        self.assertIn("PR_HEAD_SHA_MISMATCH", r["reason_codes"])

    # --- authority never granted ---

    def test_merge_authority_never_granted(self):
        for outcome in ("CLEAR", "BLOCKED", "PENDING_RETRY", "HUMAN_REQUIRED"):
            with self.subTest(outcome=outcome):
                # Build evidence that yields each outcome
                if outcome == "CLEAR":
                    ev = self._clear_evidence()
                elif outcome == "BLOCKED":
                    ev = self._clear_evidence(
                        required_checks=[{"head_sha": STALE,
                                          "status": "completed",
                                          "conclusion": "success"}])
                elif outcome == "PENDING_RETRY":
                    ev = self._clear_evidence(
                        required_checks=[{"head_sha": HEAD,
                                          "status": "in_progress",
                                          "conclusion": "pending"}])
                else:
                    ev = self._clear_evidence(
                        reviews=[{"author": "", "state": "APPROVED",
                                  "head_sha": HEAD}])
                self.assertFalse(ev["merge_authority_granted"],
                                 f"merge_authority granted for {outcome}")
                self.assertFalse(ev["deployment_authority_granted"])
                self.assertFalse(ev["production_authority_granted"])

    # --- drift / replay idempotency ---

    def test_deterministic_digest(self):
        a = self._clear_evidence()
        b = self._clear_evidence()
        self.assertEqual(a["decision_digest"], b["decision_digest"])

    def test_digest_format(self):
        r = self._clear_evidence()
        import re
        self.assertRegex(r["decision_digest"], r"^sha256:[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
