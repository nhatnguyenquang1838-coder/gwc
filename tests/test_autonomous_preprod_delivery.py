from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from node_architect.create_autonomous_task_branch import (  # noqa: E402
    BranchPlanError,
    create_task_branch_plan,
    expected_head_ref,
)
from node_architect.validate_autonomous_g3_readiness import (  # noqa: E402
    evidence_binding_digest,
    validate_g3_readiness,
)

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def branch_request() -> dict:
    return {
        "repository": "nhatnguyenquang1838-coder/gwc",
        "run_id": "run-001",
        "task_id": "SCRUM-275",
        "base_branch": "pre-prod",
        "base_sha": BASE_SHA,
        "base_sha_verified": True,
        "worktree_path": "/tmp/wt/scrum-275",
    }


def evidence() -> dict:
    return {
        "task_id": "SCRUM-275",
        "run_id": "run-001",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "pr_number": 321,
        "base_branch": "pre-prod",
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "changed_path_digest": "c" * 64,
        "ci_conclusions": [{"name": "required", "head_sha": HEAD_SHA, "conclusion": "success"}],
        "review_receipt": {"head_sha": HEAD_SHA, "independent": True, "open_findings": []},
        "pr_body_digest": "d" * 64,
        "runtime_graph_digest": "e" * 64,
        "gate_story_digest": "f" * 64,
    }


class TestAutonomousTaskBranch(unittest.TestCase):
    def test_valid_plan(self) -> None:
        plan = create_task_branch_plan(branch_request())
        self.assertEqual(plan["head_ref"], "auto/run-001/SCRUM-275")
        self.assertEqual(plan["base_branch"], "pre-prod")
        self.assertEqual(plan["push_allowed_refs"], ["auto/run-001/SCRUM-275"])

    def test_main_base_is_rejected(self) -> None:
        req = branch_request()
        req["base_branch"] = "main"
        with self.assertRaises(BranchPlanError):
            create_task_branch_plan(req)

    def test_unverified_base_sha_is_rejected(self) -> None:
        req = branch_request()
        req["base_sha_verified"] = False
        with self.assertRaises(BranchPlanError):
            create_task_branch_plan(req)

    def test_force_push_and_deletion_rejected(self) -> None:
        for key in ("force_push", "delete_branch"):
            req = branch_request()
            req[key] = True
            with self.assertRaises(BranchPlanError):
                create_task_branch_plan(req)

    def test_head_ref_shape_enforced(self) -> None:
        req = branch_request()
        req["head_ref"] = "feature/whatever"
        with self.assertRaises(BranchPlanError):
            create_task_branch_plan(req)
        with self.assertRaises(BranchPlanError):
            expected_head_ref("", "SCRUM-275")


class TestG3Readiness(unittest.TestCase):
    def test_pass_on_exact_head(self) -> None:
        decision = validate_g3_readiness(evidence(), HEAD_SHA)
        self.assertEqual(decision["outcome"], "PASS")
        self.assertTrue(decision["ready_for_review"])
        self.assertEqual(decision["evidence_binding_digest"], evidence_binding_digest(evidence()))

    def test_head_drift_blocks(self) -> None:
        decision = validate_g3_readiness(evidence(), "c" * 40)
        self.assertEqual(decision["outcome"], "FAIL")
        self.assertTrue(any("HEAD_DRIFT" in issue for issue in decision["issues"]))

    def test_stale_ci_blocks(self) -> None:
        ev = copy.deepcopy(evidence())
        ev["ci_conclusions"][0]["head_sha"] = "9" * 40
        self.assertEqual(validate_g3_readiness(ev, HEAD_SHA)["outcome"], "FAIL")

    def test_non_independent_or_open_findings_block(self) -> None:
        ev = copy.deepcopy(evidence())
        ev["review_receipt"]["independent"] = False
        self.assertEqual(validate_g3_readiness(ev, HEAD_SHA)["outcome"], "FAIL")
        ev = copy.deepcopy(evidence())
        ev["review_receipt"]["open_findings"] = ["F1"]
        self.assertEqual(validate_g3_readiness(ev, HEAD_SHA)["outcome"], "FAIL")

    def test_main_base_blocks(self) -> None:
        ev = copy.deepcopy(evidence())
        ev["base_branch"] = "main"
        decision = validate_g3_readiness(ev, HEAD_SHA)
        self.assertTrue(any("FORBIDDEN_BASE" in issue for issue in decision["issues"]))

    def test_digest_changes_with_scope(self) -> None:
        ev = copy.deepcopy(evidence())
        ev["changed_path_digest"] = "0" * 64
        self.assertNotEqual(evidence_binding_digest(ev), evidence_binding_digest(evidence()))


if __name__ == "__main__":
    unittest.main()
