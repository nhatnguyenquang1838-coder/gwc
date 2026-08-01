from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.exact_head_readiness import decide_exact_head_readiness
from tools.node_architect.rollout_progress_projection import decide_rollout_progress_projection
from tools.node_architect.independent_audit_handoff import decide_independent_audit_handoff

BASE = "4c3ca535a3e9d9c71fb4bd0ca7e0f0264e664f3a"
HEAD = "c" * 40
OLD = "d" * 40
BRANCH = "codex/scrum-253-255-f9-scale-control-m4-20260801"
REPO = "nhatnguyenquang1838-coder/gwc"
NOW = "2026-08-01T14:20:00Z"
REV = "sha256:" + "a" * 64


def validate_schema(file_name: str, payload: dict) -> None:
    schema = json.loads(Path("schemas", file_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda item: list(item.path),
    )
    if errors:
        raise AssertionError(errors[0].message)


def check(name, *, head=HEAD, status="completed", conclusion="success"):
    return {"name": name, "status": status, "conclusion": conclusion, "head_sha": head}


def artifact(name, *, head=HEAD, digest=REV):
    return {"name": name, "head_sha": head, "digest": digest}


def exact_head(**overrides):
    payload = dict(
        task_id="SCRUM-253", repository=REPO, branch=BRANCH, base_sha=BASE,
        current_head_sha=HEAD, expected_head_sha=HEAD,
        required_check_names=["Validate instructions", "Build instruction packages"],
        observed_checks=[check("Validate instructions"), check("Build instruction packages")],
        required_artifact_names=["instruction-package-gwc"],
        observed_artifacts=[artifact("instruction-package-gwc")],
        connector_status="CONFIRMED", exact_head_filter_applied=True, observed_at=NOW,
    )
    payload.update(overrides)
    return decide_exact_head_readiness(**payload)


def family_progress(*, completed=81, families=9):
    remaining = completed
    items = []
    for family in range(1, families + 1):
        done = min(9, remaining)
        remaining -= done
        items.append({"family": f"family-{family}", "completed_nodes": max(done, 0), "total_nodes": 9})
    return items


def gate(name, status="PASS", evidence_sha=HEAD):
    return {"gate": name, "status": status, "evidence_sha": evidence_sha}


def rollout(**overrides):
    payload = dict(
        task_id="SCRUM-254", repository=REPO, branch=BRANCH, base_sha=BASE, head_sha=HEAD,
        evidence_revision=REV, expected_revision=REV, family_progress=family_progress(),
        gate_evidence=[gate("G3_PR"), gate("G4_MERGE", "NOT_APPLICABLE"), gate("G5_DEPLOY", "SUCCESS")],
        observed_at=NOW,
    )
    payload.update(overrides)
    return decide_rollout_progress_projection(**payload)


def ci(workflow, conclusion="success", head=HEAD, run_id=1):
    return {"workflow": workflow, "run_id": run_id, "conclusion": conclusion, "head_sha": head}


def audit(**overrides):
    payload = dict(
        task_id="SCRUM-255", repository=REPO, branch=BRANCH, base_sha=BASE, head_sha=HEAD,
        package_revision=REV, expected_revision=REV,
        completeness_manifest={"families": 9, "nodes": 81, "artifacts": ["catalog", "schemas", "tests", "g5-evidence"]},
        ci_evidence=[ci("Validate instructions", run_id=1), ci("Build instruction packages", run_id=2)],
        limitation_disclosures=["no_production_scale_authority", "no_deployment_authority", "independent_audit_required"],
        reviewer="independent-audit-function", observed_at=NOW,
    )
    payload.update(overrides)
    return decide_independent_audit_handoff(**payload)


class ExactHeadReadinessTests(unittest.TestCase):
    def test_exact_head_with_required_checks_and_artifact_is_ready(self):
        result = exact_head()
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["reason_code"], "EXACT_HEAD_READY")
        self.assertFalse(result["scale_authority_granted"])
        validate_schema("exact-head-readiness-decision.schema.json", result)

    def test_stale_expected_head_is_rejected(self):
        self.assertEqual(exact_head(expected_head_sha=OLD)["reason_code"], "STALE_HEAD_REJECTED")

    def test_missing_required_check_blocks(self):
        result = exact_head(observed_checks=[check("Validate instructions")])
        self.assertEqual(result["reason_code"], "REQUIRED_CHECK_MISSING")
        self.assertEqual(result["missing_check_names"], ["Build instruction packages"])

    def test_failed_or_pending_required_check_blocks(self):
        self.assertEqual(exact_head(observed_checks=[check("Validate instructions", conclusion="failure"), check("Build instruction packages")])["reason_code"], "REQUIRED_CHECK_FAILED")
        self.assertEqual(exact_head(observed_checks=[check("Validate instructions", status="in_progress", conclusion=None), check("Build instruction packages")])["reason_code"], "REQUIRED_CHECK_NON_TERMINAL")

    def test_wrong_head_evidence_is_ignored_not_used(self):
        result = exact_head(observed_checks=[check("Validate instructions", head=OLD), check("Build instruction packages", head=OLD)])
        self.assertEqual(result["reason_code"], "REQUIRED_CHECK_MISSING")

    def test_missing_artifact_blocks(self):
        self.assertEqual(exact_head(observed_artifacts=[])["reason_code"], "REQUIRED_ARTIFACT_MISSING")

    def test_connector_visibility_gap_is_fail_closed(self):
        self.assertEqual(exact_head(connector_status="UNSUPPORTED", exact_head_filter_applied=False)["reason_code"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")
        self.assertEqual(exact_head(connector_status="EMPTY", exact_head_filter_applied=False)["reason_code"], "EMPTY_UNFILTERED_CONNECTOR_RESULT")


class RolloutProgressProjectionTests(unittest.TestCase):
    def test_complete_rollout_is_ready_for_audit_handoff(self):
        result = rollout()
        self.assertEqual(result["projection_status"], "READY_FOR_AUDIT_HANDOFF")
        self.assertEqual(result["progress_percent"], 100.0)
        self.assertTrue(result["read_only_projection"])
        self.assertFalse(result["audit_authority_granted"])
        validate_schema("rollout-progress-projection-decision.schema.json", result)

    def test_revision_mismatch_blocks_projection(self):
        self.assertEqual(rollout(expected_revision="sha256:" + "b" * 64)["reason_code"], "EVIDENCE_REVISION_MISMATCH")

    def test_incomplete_nodes_are_in_progress(self):
        result = rollout(family_progress=family_progress(completed=72))
        self.assertEqual(result["projection_status"], "IN_PROGRESS")
        self.assertEqual(result["reason_code"], "ROLLOUT_NODES_INCOMPLETE")

    def test_pending_gate_is_in_progress(self):
        result = rollout(gate_evidence=[gate("G3_PR", "PENDING"), gate("G5_DEPLOY", "SUCCESS")])
        self.assertEqual(result["reason_code"], "ROLLOUT_GATES_PENDING")

    def test_blocked_gate_blocks_projection(self):
        self.assertEqual(rollout(gate_evidence=[gate("G3_PR", "BLOCKED")])["reason_code"], "BLOCKED_GATE_PRESENT")

    def test_family_or_node_count_mismatch_blocks(self):
        self.assertEqual(rollout(family_progress=family_progress(families=8))["reason_code"], "FAMILY_COUNT_MISMATCH")
        bad = family_progress()
        bad[-1]["total_nodes"] = 8
        bad[-1]["completed_nodes"] = 8
        self.assertEqual(rollout(family_progress=bad)["reason_code"], "TOTAL_NODE_COUNT_MISMATCH")


class IndependentAuditHandoffTests(unittest.TestCase):
    def test_complete_revision_bound_package_is_ready(self):
        result = audit()
        self.assertEqual(result["handoff_status"], "READY_FOR_INDEPENDENT_AUDIT")
        self.assertEqual(result["reason_code"], "REVISION_BOUND_AUDIT_HANDOFF_READY")
        self.assertFalse(result["audit_completion_authority_granted"])
        validate_schema("independent-audit-handoff-decision.schema.json", result)

    def test_package_revision_mismatch_blocks(self):
        self.assertEqual(audit(expected_revision="sha256:" + "b" * 64)["reason_code"], "PACKAGE_REVISION_MISMATCH")

    def test_manifest_must_show_exact_81_node_catalog(self):
        self.assertEqual(audit(completeness_manifest={"families": 8, "nodes": 81, "artifacts": ["x"]})["reason_code"], "FAMILY_COUNT_MISMATCH")
        self.assertEqual(audit(completeness_manifest={"families": 9, "nodes": 80, "artifacts": ["x"]})["reason_code"], "NODE_COUNT_MISMATCH")

    def test_required_ci_must_be_successful_and_exact_head(self):
        self.assertEqual(audit(ci_evidence=[ci("Validate instructions", run_id=1), ci("Build instruction packages", conclusion="failure", run_id=2)])["reason_code"], "REQUIRED_CI_FAILED")
        self.assertEqual(audit(ci_evidence=[ci("Validate instructions", run_id=1), ci("Build instruction packages", head=OLD, run_id=2)])["reason_code"], "REQUIRED_CI_EVIDENCE_MISSING")

    def test_limitation_disclosures_are_mandatory(self):
        result = audit(limitation_disclosures=["independent_audit_required"])
        self.assertEqual(result["reason_code"], "LIMITATION_DISCLOSURE_INCOMPLETE")

    def test_reviewer_is_required(self):
        self.assertEqual(audit(reviewer="")["reason_code"], "REQUIRED_IDENTITY_MISSING")


if __name__ == "__main__":
    unittest.main()
