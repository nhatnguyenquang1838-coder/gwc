from __future__ import annotations

import copy
import unittest

from tools.node_architect.assemble_autonomous_preprod_pr import assemble_pr_body
from tools.node_architect.create_autonomous_task_branch import decide_branch
from tools.node_architect.merge_autonomous_preprod_pr import plan_merge
from tools.node_architect.validate_autonomous_g3_readiness import validate_g3_readiness

MAIN_SHA = "a" * 40
PREPROD_SHA = "b" * 40
HEAD_SHA = "c" * 40
RUN_ID = "run-1"
TASK_ID = "SCRUM-275"
REPO = "nhatnguyenquang1838-coder/gwc"


def _graph(head_sha: str = HEAD_SHA) -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "autonomous-run-graph",
        "run_id": RUN_ID,
        "task_id": TASK_ID,
        "repository": REPO,
        "base_ref": "pre-prod",
        "base_sha": PREPROD_SHA,
        "head_ref": f"auto/{RUN_ID}/{TASK_ID}",
        "head_sha": head_sha,
        "graph_revision": "v1",
        "nodes": [],
        "edges": [],
        "terminal_status": "PASS",
        "graph_digest": "sha256:" + "0" * 64,
    }


def _story(head_sha: str = HEAD_SHA) -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "gate-story",
        "run_id": RUN_ID,
        "task_id": TASK_ID,
        "repository": REPO,
        "head_sha": head_sha,
        "graph_digest": "sha256:" + "0" * 64,
        "gates": [
            {"gate": "G5_DEPLOY", "status": "not_applicable", "purpose": "x", "evidence_refs": [], "authority_not_granted": [], "narrative": "Pending deployment stage."},
            {"gate": "G6_PRODUCTION_DATA", "status": "not_applicable", "purpose": "x", "evidence_refs": [], "authority_not_granted": [], "narrative": "Pending production data access."},

        ],
        "terminal_summary": "x",
        "story_digest": "sha256:" + "1" * 64,
    }


class AutonomousTaskBranchTests(unittest.TestCase):
    def test_valid_autonomous_branch(self):
        d = decide_branch(
            run_id=RUN_ID, task_id=TASK_ID,
            proposed_branch=f"auto/{RUN_ID}/{TASK_ID}",
            base_branch="pre-prod", base_sha=PREPROD_SHA,
        )
        self.assertEqual("CREATE_BRANCH", d["outcome"])
        self.assertFalse(d["merge_authority_granted"])

    def test_main_base_rejected(self):
        d = decide_branch(
            run_id=RUN_ID, task_id=TASK_ID,
            proposed_branch=f"auto/{RUN_ID}/{TASK_ID}",
            base_branch="main", base_sha=MAIN_SHA,
        )
        self.assertEqual("REJECTED", d["outcome"])
        self.assertIn("AUTONOMOUS_MAIN_BASE_FORBIDDEN", d["reason_codes"])

    def test_bad_branch_pattern_rejected(self):
        d = decide_branch(
            run_id=RUN_ID, task_id=TASK_ID,
            proposed_branch="feature/x", base_branch="pre-prod", base_sha=PREPROD_SHA,
        )
        self.assertEqual("REJECTED", d["outcome"])
        self.assertIn("AUTONOMOUS_BRANCH_PATTERN_INVALID", d["reason_codes"])

    def test_protected_branch_rejected(self):
        d = decide_branch(
            run_id=RUN_ID, task_id=TASK_ID,
            proposed_branch="pre-prod", base_branch="pre-prod", base_sha=PREPROD_SHA,
        )
        self.assertEqual("REJECTED", d["outcome"])
        self.assertIn("AUTONOMOUS_TASK_BRANCH_PROTECTED_FORBIDDEN", d["reason_codes"])

    def test_bootstrap_requires_main(self):
        d = decide_branch(
            run_id=RUN_ID, task_id=TASK_ID,
            proposed_branch="pre-prod", base_branch="pre-prod", base_sha=MAIN_SHA,
            bootstrap=True,
        )
        self.assertEqual("REJECTED", d["outcome"])
        self.assertIn("AUTONOMOUS_BOOTSTRAP_REQUIRES_MAIN", d["reason_codes"])


class AutonomousPrBodyTests(unittest.TestCase):
    def test_body_rendered_and_bound_to_head(self):
        r = assemble_pr_body(graph=_graph(), story=_story())
        self.assertEqual("PR_BODY_READY", r["outcome"])
        self.assertIn("c" * 40, r["pr_body"])
        self.assertEqual("sha256:" + "0" * 64, r["managed_block_digest"])

    def test_main_base_body_rejected(self):
        g = _graph()
        g["base_ref"] = "main"
        r = assemble_pr_body(graph=g, story=_story())
        self.assertEqual("REJECTED", r["outcome"])
        self.assertIn("AUTONOMOUS_PR_MAIN_BASE_FORBIDDEN", r["reason_codes"])
        self.assertFalse(r["merge_authority_granted"])


class AutonomousG3ReadinessTests(unittest.TestCase):
    def _readback(self, draft: bool = True, head: str = HEAD_SHA) -> dict:
        return {"base": "pre-prod", "head_sha": head, "draft": draft, "merged": False}

    def _checks(self) -> list[dict]:
        return [
            {"name": "validate-g01", "head_sha": HEAD_SHA, "status": "completed", "conclusion": "success"},
            {"name": "validate-gate-action", "head_sha": HEAD_SHA, "status": "completed", "conclusion": "success"},
        ]

    def test_g3_pass(self):
        r = validate_g3_readiness(
            task_id=TASK_ID, repository=REPO, branch=f"auto/{RUN_ID}/{TASK_ID}",
            base_sha=PREPROD_SHA, current_head_sha=HEAD_SHA, expected_head_sha=HEAD_SHA,
            required_check_names=["validate-g01", "validate-gate-action"], observed_checks=self._checks(),
            required_artifact_names=["x"], observed_artifacts=[{"name": "x", "head_sha": HEAD_SHA, "digest": "sha256:" + "0" * 64}],
            connector_status="CONFIRMED", exact_head_filter_applied=True,
            pr_readback=self._readback(), independent_review={"findings_open": 0},
        )
        self.assertTrue(r["g3_pass"])
        self.assertEqual("G3_PASS", r["outcome"])

    def test_g3_blocked_on_main_base(self):
        rb = self._readback()
        rb["base"] = "main"
        r = validate_g3_readiness(
            task_id=TASK_ID, repository=REPO, branch=f"auto/{RUN_ID}/{TASK_ID}",
            base_sha=PREPROD_SHA, current_head_sha=HEAD_SHA, expected_head_sha=HEAD_SHA,
            required_check_names=["validate-g01"], observed_checks=self._checks(),
            required_artifact_names=["x"], observed_artifacts=[{"name": "x", "head_sha": HEAD_SHA, "digest": "sha256:" + "0" * 64}],
            connector_status="CONFIRMED", exact_head_filter_applied=True,
            pr_readback=rb, independent_review={"findings_open": 0},
        )
        self.assertFalse(r["g3_pass"])
        self.assertIn("AUTONOMOUS_G3_PR_MAIN_BASE_FORBIDDEN", r["reason_codes"])

    def test_g3_blocked_on_head_drift(self):
        rb = self._readback(head="d" * 40)
        r = validate_g3_readiness(
            task_id=TASK_ID, repository=REPO, branch=f"auto/{RUN_ID}/{TASK_ID}",
            base_sha=PREPROD_SHA, current_head_sha=HEAD_SHA, expected_head_sha=HEAD_SHA,
            required_check_names=["validate-g01"], observed_checks=self._checks(),
            required_artifact_names=["x"], observed_artifacts=[{"name": "x", "head_sha": HEAD_SHA, "digest": "sha256:" + "0" * 64}],
            connector_status="CONFIRMED", exact_head_filter_applied=True,
            pr_readback=rb, independent_review={"findings_open": 0},
        )
        self.assertFalse(r["g3_pass"])
        self.assertIn("AUTONOMOUS_G3_PR_HEAD_DRIFT", r["reason_codes"])

    def test_g3_blocked_on_open_findings(self):
        r = validate_g3_readiness(
            task_id=TASK_ID, repository=REPO, branch=f"auto/{RUN_ID}/{TASK_ID}",
            base_sha=PREPROD_SHA, current_head_sha=HEAD_SHA, expected_head_sha=HEAD_SHA,
            required_check_names=["validate-g01"], observed_checks=self._checks(),
            required_artifact_names=["x"], observed_artifacts=[{"name": "x", "head_sha": HEAD_SHA, "digest": "sha256:" + "0" * 64}],
            connector_status="CONFIRMED", exact_head_filter_applied=True,
            pr_readback=self._readback(), independent_review={"findings_open": 3},
        )
        self.assertFalse(r["g3_pass"])
        self.assertIn("AUTONOMOUS_G3_FINDINGS_OPEN", r["reason_codes"])


class AutonomousPreprodMergeTests(unittest.TestCase):
    def test_merge_into_preprod_ok(self):
        d = plan_merge(
            run_id=RUN_ID, task_id=TASK_ID, repository=REPO, pr_number=42,
            target_branch="pre-prod", approved_head_sha=HEAD_SHA, live_head_sha=HEAD_SHA,
        )
        self.assertEqual("MERGE_INTO_PREPROD", d["outcome"])
        self.assertEqual("gh pr merge 42 --squash --branch pre-prod", d["merge_command"])
        self.assertTrue(d["merge_proof"]["merge_proof_digest"].startswith("sha256:"))
        self.assertFalse(d["merge_authority_granted"])

    def test_merge_into_main_rejected(self):
        d = plan_merge(
            run_id=RUN_ID, task_id=TASK_ID, repository=REPO, pr_number=42,
            target_branch="main", approved_head_sha=HEAD_SHA, live_head_sha=HEAD_SHA,
        )
        self.assertEqual("REJECTED", d["outcome"])
        self.assertIn("AUTONOMOUS_MERGE_MAIN_TARGET_FORBIDDEN", d["reason_codes"])

    def test_merge_head_drift_rejected(self):
        d = plan_merge(
            run_id=RUN_ID, task_id=TASK_ID, repository=REPO, pr_number=42,
            target_branch="pre-prod", approved_head_sha=HEAD_SHA, live_head_sha="d" * 40,
        )
        self.assertEqual("REJECTED", d["outcome"])
        self.assertIn("AUTONOMOUS_MERGE_HEAD_DRIFT", d["reason_codes"])


class G3DigestHelperTests(unittest.TestCase):
    """Coverage for the evidence-binding digest helpers cherry-picked from #323."""

    def test_canonical_digest_is_order_independent(self):
        from tools.node_architect.validate_autonomous_g3_readiness import canonical_digest

        a = canonical_digest({"x": 1, "y": 2})
        b = canonical_digest({"y": 2, "x": 1})
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_canonical_digest_changes_with_payload(self):
        from tools.node_architect.validate_autonomous_g3_readiness import canonical_digest

        self.assertNotEqual(canonical_digest({"x": 1}), canonical_digest({"x": 2}))

    def test_evidence_binding_digest_binds_only_required_fields(self):
        from tools.node_architect.validate_autonomous_g3_readiness import (
            evidence_binding_digest,
        )

        evidence = {
            "task_id": TASK_ID,
            "run_id": RUN_ID,
            "repository": REPO,
            "pr_number": 42,
            "base_branch": "pre-prod",
            "base_sha": PREPROD_SHA,
            "head_sha": HEAD_SHA,
            "changed_path_digest": "sha256:" + "0" * 64,
            "ci_conclusions": [],
            "review_receipt": {},
            "pr_body_digest": "sha256:" + "1" * 64,
            "runtime_graph_digest": "sha256:" + "2" * 64,
            "gate_story_digest": "sha256:" + "3" * 64,
            # ignored extra fields
            "note": "should not affect the digest",
        }
        digest = evidence_binding_digest(evidence)
        self.assertEqual(len(digest), 64)

        # Adding an unrelated field must not change the binding digest.
        evidence["note"] = "changed note"
        self.assertEqual(evidence_binding_digest(evidence), digest)

        # Changing a bound field must change the binding digest.
        evidence["head_sha"] = "d" * 40
        self.assertNotEqual(evidence_binding_digest(evidence), digest)


if __name__ == "__main__":
    unittest.main()
