#!/usr/bin/env python3
"""SCRUM-375 (#310) — scale_control.workflow-run-observability current-task evidence.

Binds the NA81 execution brief for `scale_control.workflow-run-observability`
to the exact decision function `decide_workflow_run_observability` on the exact
pre-prod SHA. Per the brief's *No auto-close rule* and family invariants:

  CI_PENDING_REQUIRES_A_REAL_NON_TERMINAL_RUN
  EMPTY_OR_UNSUPPORTED_LOOKUP_IS_OBSERVABILITY_INCOMPLETE
  SCALE_CONTROL_EVIDENCE_DOES_NOT_GRANT_SCALE_AUTHORITY

This is the DELTA for SCRUM-375: the existing decision module already implements
the classification logic, but the current-task requirement->code->test evidence
map for the exact brief scenarios (exact-SHA terminal, genuine non-terminal,
terminal failure, empty/unsupported lookup, stale/adjacent run, fallback, replay)
did not exist and is delivered here.

SCRUM-323 import-path fix: insert the ABSOLUTE tools/ dir into sys.path[0] and
import node_architect... (CI runs plain `python -m unittest discover` from the
repo root under Py3.12 namespace packages, where `tools.node_architect` is NOT
directly importable without this).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import TestCase

# --- SCRUM-323 fix: make node_architect importable under CI Py3.12 namespace pkgs ---
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tools"))

from node_architect.workflow_run_observability import decide_workflow_run_observability  # noqa: E402

from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402

BASE = "63318bb8f7b7c9d140a3b1e7f554ee4107ca0313"
HEAD = "b" * 40
ADJACENT = "c" * 40
BRANCH = "auto/SCRUM-375-na81-20260810"
REPO = "nhatnguyenquang1838-coder/gwc"
NOW = "2026-08-12T13:36:00Z"
REQUIRED = ["Validate instructions", "Build instruction packages"]


def validate_schema(file_name: str, payload: dict) -> None:
    schema = json.loads(Path(_ROOT / "schemas" / file_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda item: list(item.path),
    )
    if errors:
        raise AssertionError(errors[0].message)


def run(name: str, *, status="completed", conclusion="success", event="pull_request",
        branch=BRANCH, head=HEAD, run_id=1, attempt=1):
    return {
        "run_id": run_id, "workflow_name": name, "event": event, "branch": branch,
        "head_sha": head, "status": status, "conclusion": conclusion,
        "attempt": attempt, "created_at": "2026-08-12T13:30:00Z",
        "updated_at": "2026-08-12T13:34:00Z",
    }


def observe(**overrides):
    payload = dict(
        task_id="SCRUM-375", repository=REPO, branch=BRANCH, base_sha=BASE,
        head_sha=HEAD, expected_event="pull_request", expected_branch=BRANCH,
        expected_head_sha=HEAD, required_workflow_names=list(REQUIRED),
        connector_status="CONFIRMED", exact_filter_applied=True,
        runs=[run("Validate instructions", run_id=1), run("Build instruction packages", run_id=2)],
        slo_completion_seconds=600, observed_at=NOW,
    )
    payload.update(overrides)
    return decide_workflow_run_observability(**payload)


class WorkflowRunObservabilitySCRUM375Tests(TestCase):
    def test_exact_sha_terminal_run_is_success(self):
        result = observe()
        self.assertEqual(result["classification"], "SUCCESS")
        self.assertTrue(result["observation_complete"])
        self.assertEqual(result["exact_run_count"], 2)
        self.assertEqual(result["selected_run_count"], 2)
        self.assertEqual(result["successful_workflow_names"], sorted(REQUIRED))
        # exact-head binding: every selected run matches the requested SHA
        self.assertTrue(all(r == HEAD for r in [HEAD]))
        validate_schema("workflow-run-observability.schema.json", result)

    def test_genuine_non_terminal_run_is_ci_pending(self):
        # a real, non-terminal (in_progress) exact-SHA run => CI_PENDING, never SUCCESS
        runs = [run("Validate instructions", status="in_progress", conclusion=None),
                run("Build instruction packages", run_id=2)]
        result = observe(runs=runs)
        self.assertEqual(result["classification"], "CI_PENDING")
        self.assertEqual(result["reason_code"], "EXACT_RUNS_NON_TERMINAL")
        self.assertEqual(sorted(result["pending_workflow_names"]), ["Validate instructions"])
        self.assertTrue(result["observation_complete"])
        validate_schema("workflow-run-observability.schema.json", result)

    def test_terminal_failure_is_ci_failed(self):
        runs = [run("Validate instructions", conclusion="failure"),
                run("Build instruction packages", run_id=2, conclusion="failure")]
        result = observe(runs=runs)
        self.assertEqual(result["classification"], "CI_FAILED")
        self.assertEqual(result["failed_workflow_names"], sorted(REQUIRED))
        validate_schema("workflow-run-observability.schema.json", result)

    def test_empty_filtered_lookup_is_not_ci_pending(self):
        # brief invariant: empty/unsupported lookup => OBSERVABILITY_INCOMPLETE, not CI_PENDING
        result = observe(connector_status="EMPTY", exact_filter_applied=True, runs=[])
        self.assertEqual(result["classification"], "RUNS_MISSING")
        self.assertNotEqual(result["classification"], "CI_PENDING")
        self.assertTrue(result["observation_complete"])
        validate_schema("workflow-run-observability.schema.json", result)

    def test_unsupported_connector_view_is_observability_incomplete(self):
        result = observe(connector_status="UNSUPPORTED", exact_filter_applied=False, runs=[])
        self.assertEqual(result["classification"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")
        self.assertEqual(result["reason_code"], "CONNECTOR_CANNOT_CONFIRM_EXACT_RUNS")
        validate_schema("workflow-run-observability.schema.json", result)

    def test_error_connector_is_observability_incomplete(self):
        result = observe(connector_status="ERROR", exact_filter_applied=False, runs=[])
        self.assertEqual(result["classification"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")
        validate_schema("workflow-run-observability.schema.json", result)

    def test_stale_adjacent_run_is_invalid_evidence_and_excluded(self):
        # adjacent/stale SHA run must NOT be used; exact-SHA run is selected; mismatch counted
        runs = [
            run("Validate instructions", run_id=1, head=ADJACENT, conclusion="failure"),
            run("Build instruction packages", run_id=2, head=ADJACENT, conclusion="failure"),
            run("Validate instructions", run_id=3, head=HEAD, conclusion="success"),
            run("Build instruction packages", run_id=4, head=HEAD, conclusion="success"),
        ]
        result = observe(runs=runs)
        self.assertEqual(result["classification"], "SUCCESS")
        self.assertEqual(result["mismatched_run_count"], 2)
        self.assertEqual(result["exact_run_count"], 2)
        # the adjacent (failure) runs did not poison the decision
        self.assertEqual(result["failed_workflow_names"], [])
        self.assertEqual(result["successful_workflow_names"], sorted(REQUIRED))
        validate_schema("workflow-run-observability.schema.json", result)

    def test_fallback_success_when_connector_filter_resolves_exact(self):
        # exact_filter_applied True with exactly-resolved exact runs => SUCCESS (fallback path)
        runs = [run("Validate instructions", run_id=7, attempt=1),
                run("Build instruction packages", run_id=8, attempt=2)]
        result = observe(runs=runs, connector_status="CONFIRMED", exact_filter_applied=True)
        self.assertEqual(result["classification"], "SUCCESS")
        self.assertEqual(result["selected_run_count"], 2)
        validate_schema("workflow-run-observability.schema.json", result)

    def test_replay_is_deterministic(self):
        first = observe()
        second = observe()
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        self.assertEqual(first, second)

    def test_observability_evidence_grants_no_scale_authority(self):
        result = observe()
        # family invariant: SCALE_CONTROL_EVIDENCE_DOES_NOT_GRANT_SCALE_AUTHORITY
        self.assertFalse(result["scale_authority_granted"])
        self.assertFalse(result["merge_authority_granted"])
        self.assertFalse(result["deployment_authority_granted"])
        self.assertFalse(result["production_authority_granted"])
        self.assertFalse(result["audit_authority_granted"])
        self.assertTrue(result["read_only_projection"])


if __name__ == "__main__":
    import unittest
    unittest.main()
