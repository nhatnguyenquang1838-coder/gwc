from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from tools.node_architect.diff_readback import decide_diff_readback
from tools.node_architect.draft_pr_creation import decide_draft_pr_creation
from tools.node_architect.ci_run_capture import decide_ci_run_capture

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "3acf169b91fa2d4c4c32f573fa3318d00dad9088"
HEAD = "a" * 40
STALE = "b" * 40
BRANCH = "codex/scrum-196-198-f3-repo-delivery-b2-20260801"
APPROVED = [
    ".gwc/tasks/SCRUM-196/**",
    ".gwc/tasks/SCRUM-197/**",
    ".gwc/tasks/SCRUM-198/**",
    "schemas/diff-readback-decision.schema.json",
    "schemas/draft-pr-creation-decision.schema.json",
    "schemas/ci-run-capture-decision.schema.json",
    "tools/node_architect/diff_readback.py",
    "tools/node_architect/draft_pr_creation.py",
    "tools/node_architect/ci_run_capture.py",
    "tests/test_repo_delivery_m5_batch_b2.py",
    "releases/changelog.d/2026-08-01-f3-repo-delivery-b2.md",
]


def load_schema(name: str) -> dict:
    return json.loads(Path("schemas", name).read_text())


class RepoDeliveryB2Tests(unittest.TestCase):
    def test_schemas_are_valid(self) -> None:
        for name in [
            "diff-readback-decision.schema.json",
            "draft-pr-creation-decision.schema.json",
            "ci-run-capture-decision.schema.json",
        ]:
            Draft202012Validator.check_schema(load_schema(name))

    def test_diff_readback_passes_for_approved_paths(self) -> None:
        decision = decide_diff_readback({
            "repository": REPO,
            "base_sha": BASE,
            "head_sha": HEAD,
            "branch": BRANCH,
            "connector_status": "available",
            "compare_status": "ahead",
            "ahead_by": 17,
            "behind_by": 0,
            "approved_paths": APPROVED,
            "changed_files": [
                {"filename": "tools/node_architect/diff_readback.py", "status": "added", "additions": 10, "deletions": 0},
                {"filename": ".gwc/tasks/SCRUM-196/g2/execution-envelope.yaml", "status": "added", "additions": 5, "deletions": 0},
            ],
        })
        self.assertEqual(decision["outcome"], "PASS")
        self.assertFalse(decision["merge_authority_granted"])
        Draft202012Validator(load_schema("diff-readback-decision.schema.json")).validate(decision)

    def test_diff_readback_blocks_out_of_scope_path(self) -> None:
        decision = decide_diff_readback({
            "repository": REPO, "base_sha": BASE, "head_sha": HEAD, "branch": BRANCH,
            "connector_status": "available", "compare_status": "ahead", "ahead_by": 1, "behind_by": 0,
            "approved_paths": APPROVED,
            "changed_files": [{"filename": "scripts/unapproved.py", "status": "added"}],
        })
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("OUT_OF_SCOPE_PATH", decision["reason_codes"])

    def test_diff_readback_blocks_base_drift(self) -> None:
        decision = decide_diff_readback({
            "repository": REPO, "base_sha": BASE, "head_sha": HEAD, "branch": BRANCH,
            "connector_status": "available", "compare_status": "ahead", "ahead_by": 1, "behind_by": 2,
            "approved_paths": APPROVED,
            "changed_files": [{"filename": "tools/node_architect/diff_readback.py", "status": "added"}],
        })
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("BASE_DRIFT", decision["reason_codes"])

    def test_diff_readback_requires_human_on_unavailable_connector(self) -> None:
        decision = decide_diff_readback({
            "repository": REPO, "base_sha": BASE, "head_sha": HEAD, "branch": BRANCH,
            "connector_status": "unavailable", "compare_status": "ahead", "ahead_by": 1, "behind_by": 0,
            "approved_paths": APPROVED,
            "changed_files": [{"filename": "tools/node_architect/diff_readback.py", "status": "added"}],
        })
        self.assertEqual(decision["outcome"], "HUMAN_REQUIRED")

    def test_draft_pr_creation_requests_create_when_no_pr(self) -> None:
        decision = decide_draft_pr_creation({
            "repository": REPO, "base_branch": "main", "branch": BRANCH,
            "base_sha": BASE, "head_sha": HEAD, "connector_status": "available", "pr": None,
        })
        self.assertEqual(decision["outcome"], "CREATE_DRAFT_PR")
        self.assertFalse(decision["merge_authority_granted"])
        Draft202012Validator(load_schema("draft-pr-creation-decision.schema.json")).validate(decision)

    def test_draft_pr_creation_binds_existing_draft(self) -> None:
        decision = decide_draft_pr_creation({
            "repository": REPO, "base_branch": "main", "branch": BRANCH,
            "base_sha": BASE, "head_sha": HEAD, "connector_status": "available",
            "pr": {"number": 160, "state": "open", "base": "main", "head": BRANCH, "head_sha": HEAD, "draft": True, "merged": False},
        })
        self.assertEqual(decision["outcome"], "DRAFT_PR_BOUND")
        self.assertEqual(decision["pr_number"], 160)

    def test_draft_pr_creation_requires_readback_after_unknown_create(self) -> None:
        decision = decide_draft_pr_creation({
            "repository": REPO, "base_branch": "main", "branch": BRANCH,
            "base_sha": BASE, "head_sha": HEAD, "connector_status": "available",
            "last_action_state": "unknown", "pr": None,
        })
        self.assertEqual(decision["outcome"], "PENDING_READBACK")
        self.assertIn("UNKNOWN_CREATE_OUTCOME_REQUIRES_READBACK", decision["reason_codes"])

    def test_draft_pr_creation_blocks_non_draft_pr(self) -> None:
        decision = decide_draft_pr_creation({
            "repository": REPO, "base_branch": "main", "branch": BRANCH,
            "base_sha": BASE, "head_sha": HEAD,
            "pr": {"number": 160, "state": "open", "base": "main", "head": BRANCH, "head_sha": HEAD, "draft": False, "merged": False},
        })
        self.assertEqual(decision["outcome"], "BLOCKED")
        self.assertIn("PR_NOT_DRAFT", decision["reason_codes"])

    def test_ci_run_capture_passes_exact_head_success(self) -> None:
        decision = decide_ci_run_capture({
            "repository": REPO,
            "branch": BRANCH,
            "head_sha": HEAD,
            "required_workflows": ["Validate instructions", "Build instruction packages"],
            "runs": [
                {"name": "Validate instructions", "run_id": 1, "attempt": 1, "status": "completed", "conclusion": "success", "head_sha": HEAD},
                {"name": "Build instruction packages", "run_id": 2, "attempt": 1, "status": "completed", "conclusion": "success", "head_sha": HEAD},
            ],
        })
        self.assertEqual(decision["outcome"], "PASSED")
        self.assertEqual(decision["reason_codes"], ["CI_EXACT_HEAD_PASSED"])
        Draft202012Validator(load_schema("ci-run-capture-decision.schema.json")).validate(decision)

    def test_ci_run_capture_ignores_stale_head_and_blocks_missing_current(self) -> None:
        decision = decide_ci_run_capture({
            "repository": REPO,
            "branch": BRANCH,
            "head_sha": HEAD,
            "required_workflows": ["Validate instructions"],
            "runs": [{"name": "Validate instructions", "run_id": 3, "attempt": 1, "status": "completed", "conclusion": "success", "head_sha": STALE}],
        })
        self.assertEqual(decision["outcome"], "UNAVAILABLE")
        self.assertIn("CI_RUN_MISSING", decision["reason_codes"])
        self.assertIn("STALE_HEAD_RUNS_IGNORED", decision["reason_codes"])

    def test_ci_run_capture_non_terminal_is_pending(self) -> None:
        decision = decide_ci_run_capture({
            "repository": REPO,
            "branch": BRANCH,
            "head_sha": HEAD,
            "required_workflows": ["Validate instructions"],
            "runs": [{"name": "Validate instructions", "run_id": 4, "attempt": 1, "status": "in_progress", "conclusion": None, "head_sha": HEAD}],
        })
        self.assertEqual(decision["outcome"], "PENDING")
        self.assertIn("CI_NON_TERMINAL", decision["reason_codes"])

    def test_decisions_have_no_merge_or_production_authority(self) -> None:
        decisions = [
            decide_diff_readback({"repository": REPO, "base_sha": BASE, "head_sha": HEAD, "branch": BRANCH, "compare_status": "ahead", "ahead_by": 1, "behind_by": 0, "approved_paths": APPROVED, "changed_files": [{"filename": "tools/node_architect/diff_readback.py"}]}),
            decide_draft_pr_creation({"repository": REPO, "base_branch": "main", "branch": BRANCH, "base_sha": BASE, "head_sha": HEAD}),
            decide_ci_run_capture({"repository": REPO, "branch": BRANCH, "head_sha": HEAD, "required_workflows": ["Validate instructions"], "runs": [{"name": "Validate instructions", "run_id": 1, "status": "completed", "conclusion": "success", "head_sha": HEAD}]}),
        ]
        for decision in decisions:
            self.assertFalse(decision["merge_authority_granted"])
            self.assertFalse(decision["deployment_authority_granted"])
            self.assertFalse(decision["production_authority_granted"])


if __name__ == "__main__":
    unittest.main()
