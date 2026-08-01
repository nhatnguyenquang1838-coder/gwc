from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from tools.node_architect.catalog_cardinality_readiness import decide_catalog_cardinality_readiness
from tools.node_architect.execution_throttle_control import decide_execution_throttle
from tools.node_architect.workflow_run_observability import decide_workflow_run_observability

BASE = "63318bb8f7b7c9d140a3b1e7f554ee4107ca0313"
HEAD = "b" * 40
BRANCH = "codex/scrum-250-252-f9-scale-control-m4-20260801"
REPO = "nhatnguyenquang1838-coder/gwc"
NOW = "2026-08-01T13:00:00Z"
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


def expected_catalog() -> tuple[dict[str, list[str]], list[str]]:
    mapping = {
        f"family-{family}": [f"family-{family}.node-{node}" for node in range(1, 10)]
        for family in range(1, 10)
    }
    expected = [node for nodes in mapping.values() for node in nodes]
    return mapping, expected


def cardinality(**overrides):
    mapping, expected = expected_catalog()
    payload = dict(
        task_id="SCRUM-250", repository=REPO, branch=BRANCH, base_sha=BASE,
        head_sha=HEAD, catalog_revision=REV, expected_revision=REV,
        family_node_ids=mapping, expected_node_ids=expected, observed_at=NOW,
    )
    payload.update(overrides)
    return decide_catalog_cardinality_readiness(**payload)


def throttle(**overrides):
    payload = dict(
        task_id="SCRUM-251", repository=REPO, branch=BRANCH, base_sha=BASE,
        head_sha=HEAD, batch_id="F9-B2", active_implementation_batch_ids=[],
        requested_parallelism=2, max_parallelism=3, capacity_units_available=6,
        capacity_units_per_worker=2, recent_failure_rate=0.1,
        failure_rate_threshold=0.5, cooldown_active=False,
        previous_batch_terminal=True, observed_at=NOW,
    )
    payload.update(overrides)
    return decide_execution_throttle(**payload)


def run(name: str, *, status="completed", conclusion="success", event="pull_request",
        branch=BRANCH, head=HEAD, run_id=1, attempt=1):
    return {
        "run_id": run_id, "workflow_name": name, "event": event, "branch": branch,
        "head_sha": head, "status": status, "conclusion": conclusion,
        "attempt": attempt, "created_at": "2026-08-01T12:55:00Z",
        "updated_at": "2026-08-01T12:58:00Z",
    }


def observe(**overrides):
    payload = dict(
        task_id="SCRUM-252", repository=REPO, branch=BRANCH, base_sha=BASE,
        head_sha=HEAD, expected_event="pull_request", expected_branch=BRANCH,
        expected_head_sha=HEAD, required_workflow_names=["Validate instructions", "Build instruction packages"],
        connector_status="CONFIRMED", exact_filter_applied=True,
        runs=[run("Validate instructions", run_id=1), run("Build instruction packages", run_id=2)],
        slo_completion_seconds=600, observed_at=NOW,
    )
    payload.update(overrides)
    return decide_workflow_run_observability(**payload)


class CatalogCardinalityReadinessTests(unittest.TestCase):
    def test_exact_nine_by_nine_catalog_is_ready(self):
        result = cardinality()
        self.assertEqual(result["outcome"], "READY")
        self.assertEqual(result["observed_unique_node_count"], 81)
        self.assertFalse(result["audit_authority_granted"])
        validate_schema("catalog-cardinality-readiness-decision.schema.json", result)

    def test_revision_mismatch_blocks(self):
        self.assertEqual(cardinality(expected_revision="sha256:" + "c" * 64)["reason_code"], "CATALOG_REVISION_MISMATCH")

    def test_family_count_and_family_size_fail_closed(self):
        mapping, expected = expected_catalog()
        mapping.pop("family-9")
        self.assertEqual(cardinality(family_node_ids=mapping, expected_node_ids=expected)["reason_code"], "FAMILY_COUNT_MISMATCH")
        mapping, expected = expected_catalog()
        mapping["family-1"] = mapping["family-1"][:-1]
        self.assertEqual(cardinality(family_node_ids=mapping, expected_node_ids=expected)["reason_code"], "FAMILY_CARDINALITY_MISMATCH")

    def test_duplicate_node_is_detected(self):
        mapping, expected = expected_catalog()
        mapping["family-2"][0] = mapping["family-1"][0]
        self.assertEqual(cardinality(family_node_ids=mapping, expected_node_ids=expected)["reason_code"], "DUPLICATE_NODE_ID")

    def test_missing_and_unexpected_nodes_are_reported(self):
        mapping, expected = expected_catalog()
        replacement = "family-1.unexpected"
        mapping["family-1"][0] = replacement
        result = cardinality(family_node_ids=mapping, expected_node_ids=expected)
        self.assertEqual(result["reason_code"], "CANONICAL_NODE_MISSING")
        self.assertEqual(len(result["missing_node_ids"]), 1)
        self.assertEqual(result["unexpected_node_ids"], [replacement])


class ExecutionThrottleControlTests(unittest.TestCase):
    def test_rate_within_bounds_is_allowed(self):
        result = throttle()
        self.assertEqual(result["outcome"], "ALLOW")
        self.assertEqual(result["allowed_parallelism"], 2)
        self.assertFalse(result["scale_authority_granted"])
        validate_schema("execution-throttle-decision.schema.json", result)

    def test_capacity_reduces_parallelism(self):
        result = throttle(requested_parallelism=4, capacity_units_available=4)
        self.assertEqual(result["outcome"], "THROTTLE")
        self.assertEqual(result["allowed_parallelism"], 2)
        self.assertTrue(result["partial_execution_allowed"])

    def test_zero_capacity_pauses_execution(self):
        result = throttle(capacity_units_available=0)
        self.assertEqual(result["reason_code"], "INSUFFICIENT_CAPACITY")
        self.assertFalse(result["execution_allowed"])

    def test_failure_signal_or_cooldown_pauses(self):
        self.assertEqual(throttle(recent_failure_rate=0.5)["reason_code"], "FAILURE_SIGNAL_COOLDOWN")
        self.assertEqual(throttle(cooldown_active=True)["reason_code"], "FAILURE_SIGNAL_COOLDOWN")

    def test_other_or_multiple_active_batches_block(self):
        self.assertEqual(throttle(active_implementation_batch_ids=["F8"])["reason_code"], "OTHER_BATCH_ALREADY_ACTIVE")
        self.assertEqual(throttle(active_implementation_batch_ids=["F8", "F7"])["reason_code"], "ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED")

    def test_previous_batch_must_be_terminal(self):
        self.assertEqual(throttle(previous_batch_terminal=False)["reason_code"], "PREVIOUS_BATCH_NOT_TERMINAL")


class WorkflowRunObservabilityTests(unittest.TestCase):
    def test_exact_successful_workflow_set_is_success(self):
        result = observe()
        self.assertEqual(result["classification"], "SUCCESS")
        self.assertTrue(result["observation_complete"])
        self.assertEqual(result["slo_ready_metrics"]["attempts_total"], 2)
        self.assertFalse(result["deployment_authority_granted"])
        validate_schema("workflow-run-observability.schema.json", result)

    def test_pending_exact_run_is_ci_pending(self):
        runs = [run("Validate instructions", status="in_progress", conclusion=None),
                run("Build instruction packages", run_id=2)]
        self.assertEqual(observe(runs=runs)["classification"], "CI_PENDING")

    def test_terminal_failure_is_ci_failed(self):
        runs = [run("Validate instructions", conclusion="failure"),
                run("Build instruction packages", run_id=2)]
        self.assertEqual(observe(runs=runs)["classification"], "CI_FAILED")

    def test_wrong_event_or_sha_is_missing_not_success(self):
        runs = [run("Validate instructions", event="push"),
                run("Build instruction packages", head="c" * 40, run_id=2)]
        result = observe(runs=runs)
        self.assertEqual(result["classification"], "RUNS_MISSING")
        self.assertEqual(result["mismatched_run_count"], 2)

    def test_connector_visibility_gap_is_not_ci_pending(self):
        result = observe(connector_status="UNSUPPORTED", exact_filter_applied=False, runs=[])
        self.assertEqual(result["classification"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")
        result = observe(connector_status="EMPTY", exact_filter_applied=False, runs=[])
        self.assertEqual(result["classification"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")

    def test_empty_exact_filtered_result_is_runs_missing(self):
        result = observe(connector_status="EMPTY", exact_filter_applied=True, runs=[])
        self.assertEqual(result["classification"], "RUNS_MISSING")
        self.assertTrue(result["observation_complete"])

    def test_latest_attempt_is_selected_deterministically(self):
        runs = [
            run("Validate instructions", conclusion="failure", run_id=1, attempt=1),
            run("Validate instructions", conclusion="success", run_id=3, attempt=2),
            run("Build instruction packages", run_id=2),
        ]
        result = observe(runs=runs)
        self.assertEqual(result["classification"], "SUCCESS")
        self.assertEqual(result["superseded_run_count"], 1)
        self.assertEqual(result["slo_ready_metrics"]["attempts_total"], 3)


if __name__ == "__main__":
    unittest.main()
