from __future__ import annotations
import unittest
from tools.node_architect.validate_node_catalog_repo_delivery import decide_ci_failure_repair, decide_pr_blocker_check, decide_ready_for_review_promotion

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "0b05dcce1865cdce58e5fff22ee8784428735df0"
HEAD = "a" * 40
STALE = "b" * 40
BRANCH = "codex/scrum-199-201-f3-repo-delivery-b3-20260802"
SCOPE = "sha256:c66bd6f850a16dbc641a58b8d97e622fbbbc88d1f833ac9d2436c4316ee24d6e"
APPROVED = ["tools/node_architect/validate_node_catalog_repo_delivery.py", "tests/test_repo_delivery_m5_batch_b3.py", "releases/changelog.d/2026-08-02-f3-b3-repo-delivery.md", ".gwc/tasks/SCRUM-199/**", ".gwc/tasks/SCRUM-200/**", ".gwc/tasks/SCRUM-201/**"]

class RepoDeliveryB3Tests(unittest.TestCase):
    def test_ci_failure_repair_allows_exact_head_repository_fix(self):
        d = decide_ci_failure_repair({"repository": REPO, "branch": BRANCH, "base_sha": BASE, "head_sha": HEAD, "scope_hash": SCOPE, "approved_paths": APPROVED, "repair_paths": ["tests/test_repo_delivery_m5_batch_b3.py"], "failure": {"head_sha": HEAD, "status": "completed", "conclusion": "failure", "repository_fixable": True}})
        self.assertEqual(d["outcome"], "REPAIR_ALLOWED")
        self.assertFalse(d["merge_authority_granted"])
        self.assertFalse(d["deployment_authority_granted"])
        self.assertFalse(d["production_authority_granted"])
    def test_ci_failure_repair_blocks_stale_head_and_out_of_scope(self):
        d = decide_ci_failure_repair({"repository": REPO, "branch": BRANCH, "base_sha": BASE, "head_sha": HEAD, "scope_hash": SCOPE, "approved_paths": APPROVED, "repair_paths": ["scripts/unapproved.py"], "failure": {"head_sha": STALE, "status": "completed", "conclusion": "failure", "repository_fixable": True}})
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertIn("STALE_HEAD_FAILURE", d["reason_codes"])
        self.assertIn("OUT_OF_SCOPE_REPAIR_PATH", d["reason_codes"])
    def test_ci_failure_repair_requires_readback_for_unknown_outcome(self):
        d = decide_ci_failure_repair({"repository": REPO, "branch": BRANCH, "base_sha": BASE, "head_sha": HEAD, "scope_hash": SCOPE, "approved_paths": APPROVED, "repair_paths": ["tests/test_repo_delivery_m5_batch_b3.py"], "unknown_external_outcome": True, "failure": {"head_sha": HEAD, "status": "completed", "conclusion": "failure", "repository_fixable": True}})
        self.assertEqual(d["outcome"], "PENDING_READBACK")
    def test_ready_for_review_promotes_only_current_draft_after_g3_pass(self):
        d = decide_ready_for_review_promotion({"repository": REPO, "pr_number": 175, "branch": BRANCH, "head_sha": HEAD, "pr": {"state": "open", "draft": True, "head": BRANCH, "head_sha": HEAD, "merged": False}, "ci": {"outcome": "PASSED", "head_sha": HEAD}, "review": {"outcome": "PASS", "head_sha": HEAD, "unresolved_threads": 0, "scope_drift": False}})
        self.assertEqual(d["outcome"], "PROMOTE_READY_FOR_REVIEW")
        self.assertFalse(d["merge_authority_granted"])
    def test_ready_for_review_blocks_stale_ci_and_threads(self):
        d = decide_ready_for_review_promotion({"repository": REPO, "pr_number": 175, "branch": BRANCH, "head_sha": HEAD, "pr": {"state": "open", "draft": True, "head": BRANCH, "head_sha": HEAD, "merged": False}, "ci": {"outcome": "PASSED", "head_sha": STALE}, "review": {"outcome": "PASS", "head_sha": HEAD, "unresolved_threads": 1}})
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertIn("CI_HEAD_SHA_MISMATCH", d["reason_codes"])
        self.assertIn("UNRESOLVED_REVIEW_THREADS", d["reason_codes"])
    def test_pr_blocker_check_clear_when_current_pr_clean(self):
        d = decide_pr_blocker_check({"repository": REPO, "pr_number": 175, "head_sha": HEAD, "pr": {"state": "open", "draft": False, "head_sha": HEAD, "mergeable": True, "merged": False}, "required_checks": [{"head_sha": HEAD, "status": "completed", "conclusion": "success"}], "review_threads": [{"resolved": True}], "reviews": [{"author": "reviewer", "state": "APPROVED", "head_sha": HEAD}]})
        self.assertEqual(d["outcome"], "CLEAR")
        self.assertFalse(d["merge_authority_granted"])
    def test_pr_blocker_check_classifies_blockers(self):
        d = decide_pr_blocker_check({"repository": REPO, "pr_number": 175, "head_sha": HEAD, "pr": {"state": "open", "draft": True, "head_sha": HEAD, "mergeable": False, "merged": False}, "required_checks": [{"head_sha": HEAD, "status": "completed", "conclusion": "failure"}], "review_threads": [{"resolved": False}], "reviews": [{"author": "reviewer", "state": "CHANGES_REQUESTED", "head_sha": HEAD}]})
        for code in ["PR_STILL_DRAFT", "PR_NOT_MERGEABLE", "CHECK_NOT_SUCCESSFUL", "UNRESOLVED_REVIEW_THREAD", "CHANGES_REQUESTED"]:
            self.assertIn(code, d["reason_codes"])
    def test_pr_blocker_check_records_stale_checks(self):
        d = decide_pr_blocker_check({"repository": REPO, "pr_number": 175, "head_sha": HEAD, "pr": {"state": "open", "draft": False, "head_sha": HEAD, "mergeable": True, "merged": False}, "required_checks": [{"head_sha": STALE, "status": "completed", "conclusion": "success"}]})
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertIn("STALE_CHECK_IGNORED", d["reason_codes"])

if __name__ == "__main__":
    unittest.main()
