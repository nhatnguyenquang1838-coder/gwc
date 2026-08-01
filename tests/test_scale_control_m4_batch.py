from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.batch_admission_check import decide_batch_admission
from tools.node_architect.batch_size_limit_check import decide_batch_size_limit
from tools.node_architect.previous_batch_g5_verification import decide_previous_batch_g5_verification

BASE = "e2f8da5263546222228a234867389f613bbed558"
HEAD = "b" * 40
MERGE = "761315f62884e090fc082417f456b050e5fc73b1"
BRANCH = "codex/scrum-247-249-f9-scale-control-m4-20260801"
REPO = "nhatnguyenquang1838-coder/gwc"
OBSERVED = "2026-08-01T10:00:00Z"
NOW = "2026-08-01T10:30:00Z"


def validate_schema(file_name: str, payload: dict) -> None:
    schema = json.loads(Path("schemas", file_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda item: list(item.path),
    )
    if errors:
        raise AssertionError(errors[0].message)


def admission(**overrides):
    payload = dict(
        task_id="SCRUM-247", repository=REPO, branch=BRANCH, base_sha=BASE, head_sha=HEAD,
        previous_batch_id="F8", previous_merge_sha=MERGE, g5_evidence_merge_sha=MERGE,
        g5_status="PASS", g5_evidence_qualified=True, g5_observed_at=OBSERVED, now_at=NOW,
        max_evidence_age_seconds=3600, blocker_status="CLEAR", requested_node_count=3,
        approved_node_budget=9, observed_at=NOW,
    )
    payload.update(overrides)
    return decide_batch_admission(**payload)


def size(**overrides):
    payload = dict(
        task_id="SCRUM-248", repository=REPO, branch=BRANCH, base_sha=BASE, head_sha=HEAD,
        batch_id="F9", node_ids=["n1"], node_batch_ids=["F9"],
        active_implementation_batch_ids=[], max_batch_size=9,
        max_concurrent_implementation_batches=1, observed_at=NOW,
    )
    payload.update(overrides)
    return decide_batch_size_limit(**payload)


def g5(**overrides):
    payload = dict(
        task_id="SCRUM-249", repository=REPO, branch=BRANCH, base_sha=BASE, head_sha=HEAD,
        previous_batch_id="F8", previous_pr_number=144, previous_pr_state="merged",
        expected_merge_sha=MERGE, evidence_source="connector", evidence_event="push",
        evidence_branch="main", evidence_head_sha=MERGE, workflow_run_id=12345,
        conclusion="success", connector_status="CONFIRMED",
        required_workflow_names=["validate-instructions"], observed_at_evidence=OBSERVED,
        now_at=NOW, max_evidence_age_seconds=3600, observed_at=NOW,
    )
    payload.update(overrides)
    return decide_previous_batch_g5_verification(**payload)


class BatchAdmissionM4Tests(unittest.TestCase):
    def test_exact_qualified_g5_and_clear_budget_admits(self):
        result = admission()
        self.assertEqual(result["outcome"], "ADMIT")
        self.assertTrue(result["admission_allowed"])
        self.assertFalse(result["scale_authority_granted"])
        validate_schema("batch-admission-decision.schema.json", result)

    def test_merge_sha_mismatch_blocks(self):
        result = admission(g5_evidence_merge_sha="c" * 40)
        self.assertEqual(result["reason_code"], "G5_MERGE_SHA_MISMATCH")
        self.assertFalse(result["admission_allowed"])

    def test_missing_or_unqualified_g5_blocks(self):
        self.assertEqual(admission(g5_status="PENDING")["reason_code"], "G5_NOT_SUCCESSFUL")
        self.assertEqual(admission(g5_evidence_qualified=False)["reason_code"], "G5_EVIDENCE_UNQUALIFIED")

    def test_stale_g5_blocks(self):
        result = admission(now_at="2026-08-01T12:00:01Z")
        self.assertEqual(result["reason_code"], "G5_EVIDENCE_STALE")

    def test_blocker_or_budget_excess_blocks(self):
        self.assertEqual(admission(blocker_status="BLOCKED")["reason_code"], "ACTIVE_BLOCKER_PRESENT")
        self.assertEqual(admission(requested_node_count=10)["reason_code"], "APPROVED_NODE_BUDGET_EXCEEDED")


class BatchSizeLimitM4Tests(unittest.TestCase):
    def test_one_and_nine_nodes_are_allowed(self):
        self.assertEqual(size()["outcome"], "ALLOW")
        nodes = [f"n{i}" for i in range(9)]
        result = size(node_ids=nodes, node_batch_ids=["F9"] * 9)
        self.assertEqual(result["outcome"], "ALLOW")
        validate_schema("batch-size-limit-decision.schema.json", result)

    def test_zero_and_ten_nodes_are_blocked(self):
        self.assertEqual(size(node_ids=[], node_batch_ids=[])["reason_code"], "EMPTY_BATCH_NOT_ADMITTED")
        nodes = [f"n{i}" for i in range(10)]
        self.assertEqual(size(node_ids=nodes, node_batch_ids=["F9"] * 10)["reason_code"], "BATCH_SIZE_LIMIT_EXCEEDED")

    def test_invalid_types_fail_closed(self):
        result = size(node_ids="n1")
        self.assertEqual(result["reason_code"], "INVALID_BATCH_LIST_INPUT")
        self.assertFalse(result["admission_allowed"])

    def test_mixed_batch_identifiers_and_duplicates_block(self):
        self.assertEqual(size(node_ids=["n1", "n2"], node_batch_ids=["F9", "F8"])["reason_code"], "MIXED_BATCH_IDENTIFIERS")
        self.assertEqual(size(node_ids=["n1", "n1"], node_batch_ids=["F9", "F9"])["reason_code"], "DUPLICATE_NODE_ID")

    def test_second_active_batch_blocks_without_partial_admission(self):
        result = size(active_implementation_batch_ids=["F8"])
        self.assertEqual(result["reason_code"], "ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED")
        self.assertFalse(result["partial_admission_allowed"])


class PreviousBatchG5VerificationM4Tests(unittest.TestCase):
    def test_exact_connector_push_main_success_is_verified(self):
        result = g5()
        self.assertEqual(result["outcome"], "VERIFIED_CONNECTOR")
        self.assertTrue(result["connector_confirmed_pass"])
        validate_schema("previous-batch-g5-verification-decision.schema.json", result)

    def test_human_observed_success_is_qualified_but_not_connector_confirmed(self):
        result = g5(
            evidence_source="human_observed_github_ui", workflow_run_id=None,
            connector_status="CONNECTOR_OBSERVABILITY_INCOMPLETE", human_attestation_id="attestation-144",
        )
        self.assertEqual(result["outcome"], "VERIFIED_HUMAN_OBSERVED")
        self.assertTrue(result["human_observed_success"])
        self.assertFalse(result["connector_confirmed_pass"])
        validate_schema("previous-batch-g5-verification-decision.schema.json", result)

    def test_pr_only_pending_failure_and_wrong_sha_block(self):
        self.assertEqual(g5(evidence_event="pull_request")["reason_code"], "PR_ONLY_EVIDENCE_NOT_QUALIFIED")
        self.assertEqual(g5(conclusion="in_progress")["reason_code"], "G5_EVIDENCE_PENDING")
        self.assertEqual(g5(conclusion="failure")["reason_code"], "G5_EVIDENCE_NOT_SUCCESSFUL")
        self.assertEqual(g5(evidence_head_sha="c" * 40)["reason_code"], "G5_HEAD_SHA_MISMATCH")

    def test_connector_empty_and_stale_evidence_block(self):
        self.assertEqual(g5(workflow_run_id=None)["reason_code"], "CONNECTOR_EVIDENCE_INCOMPLETE")
        self.assertEqual(g5(now_at="2026-08-01T12:00:01Z")["reason_code"], "G5_EVIDENCE_STALE")

    def test_human_observed_requires_explicit_attestation_and_label(self):
        result = g5(evidence_source="human_observed_github_ui", workflow_run_id=None,
                    connector_status="CONNECTOR_OBSERVABILITY_INCOMPLETE")
        self.assertEqual(result["reason_code"], "HUMAN_ATTESTATION_MISSING")
        result = g5(evidence_source="human_observed_github_ui", workflow_run_id=None,
                    connector_status="CONFIRMED", human_attestation_id="attestation-144")
        self.assertEqual(result["reason_code"], "HUMAN_OBSERVED_LABEL_MISMATCH")


if __name__ == "__main__":
    unittest.main()
