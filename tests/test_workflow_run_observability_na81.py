#!/usr/bin/env python3
"""NA81 audit-projection tests for workflow_run_observability (SCRUM-375).

Exercises the SCRUM-375 (NA81-F9-N06) brief requirements for the
``scale_control.workflow-run-observability`` node:

* exact task / PR head-SHA evidence binding (runs with a mismatched
  ``head_sha`` are excluded, never counted as evidence);
* distinguishing MISSING runs (``RUNS_MISSING``) from connector visibility
  gaps (``CONNECTOR_OBSERVABILITY_INCOMPLETE``: ``EMPTY`` returned without an
  exact filter, ``ERROR``, ``UNSUPPORTED``);
* empty / unsupported lookup is observability-incomplete, NEVER ``CI_PENDING``
  or ``PASS`` (SUCCESS);
* non-authoritative read-only semantics (every authority field fixed ``False``,
  ``read_only_projection`` fixed ``True``);
* deterministic, schema-valid decision output.

The executable ``tools/node_architect/workflow_run_observability.py`` already
existed (authored under SCRUM-252). This SCRUM-375 maturity PR binds the
current #310 brief to that executable with current-task test evidence and a
changelog fragment; the descriptor and existing source are preserved
untouched (provenance-SHA trap avoided).

The module is imported via an absolute ``tools/`` path insertion so that
``import node_architect...`` resolves under ``python -m unittest discover``
from the repository root (PEP 420 namespace packages). No connector call,
network request, filesystem mutation, Jira, branch, commit, PR, approval,
merge, deployment or production operation occurs.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from node_architect import workflow_run_observability as wro  # noqa: E402

try:
    import jsonschema
    _HAVE_JSONSCHEMA = True
except Exception:  # pragma: no cover - jsonschema is expected in CI
    _HAVE_JSONSCHEMA = False


TASK_ID = "SCRUM-375"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-375-na81-recert-20260814-r10"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
OTHER_SHA = "c" * 40
REQUIRED = ["build", "test"]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _run(
    run_id: int,
    name: str,
    event: str,
    branch: str,
    head_sha: str,
    status: str,
    conclusion=None,
    attempt: int = 1,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> dict:
    r = {
        "run_id": run_id,
        "workflow_name": name,
        "event": event,
        "branch": branch,
        "head_sha": head_sha,
        "status": status,
        "attempt": attempt,
    }
    if conclusion is not None:
        r["conclusion"] = conclusion
    if created_at is not None:
        r["created_at"] = created_at
    if updated_at is not None:
        r["updated_at"] = updated_at
    return r


def _base(**over) -> dict:
    args = dict(
        task_id=TASK_ID,
        repository=REPOSITORY,
        branch=BRANCH,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        expected_event="pull_request",
        expected_branch=BRANCH,
        expected_head_sha=HEAD_SHA,
        required_workflow_names=list(REQUIRED),
        connector_status="CONFIRMED",
        exact_filter_applied=True,
        runs=[],
        slo_completion_seconds=600,
    )
    args.update(over)
    return wro.decide_workflow_run_observability(**args)


class SuccessProjectionTests(unittest.TestCase):
    def test_all_exact_runs_present_is_success(self):
        runs = [
            _run(1, "build", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
            _run(2, "test", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
        ]
        d = _base(runs=runs)
        self.assertEqual(d["classification"], "SUCCESS")
        self.assertEqual(d["reason_code"], "EXACT_WORKFLOW_SET_SUCCESSFUL")
        self.assertEqual(d["selected_run_count"], 2)
        self.assertEqual(sorted(d["successful_workflow_names"]), ["build", "test"])
        self.assertTrue(d["observation_complete"])

    def test_post_merge_push_event_also_observed(self):
        # The node projects across pull-request AND post-merge push events.
        runs = [
            _run(1, "build", "push", BRANCH, HEAD_SHA, "completed", "success"),
            _run(2, "test", "push", BRANCH, HEAD_SHA, "completed", "success"),
        ]
        d = _base(expected_event="push", runs=runs)
        self.assertEqual(d["classification"], "SUCCESS")
        self.assertEqual(d["successful_workflow_names"], ["build", "test"])


class MissingVsConnectorGapTests(unittest.TestCase):
    def test_no_runs_is_runs_missing_not_connector_gap(self):
        # CONFIRMED connector, exact filter applied, but zero matching runs ->
        # missing evidence, not a visibility gap.
        d = _base()
        self.assertEqual(d["classification"], "RUNS_MISSING")
        self.assertEqual(d["reason_code"], "REQUIRED_EXACT_RUNS_MISSING")
        self.assertEqual(sorted(d["missing_workflow_names"]), ["build", "test"])

    def test_connector_empty_without_exact_filter_is_incomplete(self):
        # An empty connector result is only trustworthy when an exact filter was
        # applied; without it the lookup is a visibility gap, NOT missing-runs.
        d = _base(connector_status="EMPTY", exact_filter_applied=False)
        self.assertEqual(d["classification"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")
        self.assertEqual(d["reason_code"], "EMPTY_UNFILTERED_CONNECTOR_RESULT")

    def test_connector_error_is_incomplete(self):
        d = _base(connector_status="ERROR")
        self.assertEqual(d["classification"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")
        self.assertEqual(d["reason_code"], "CONNECTOR_CANNOT_CONFIRM_EXACT_RUNS")

    def test_connector_unsupported_is_incomplete(self):
        d = _base(connector_status="UNSUPPORTED")
        self.assertEqual(d["classification"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")
        self.assertEqual(d["reason_code"], "CONNECTOR_CANNOT_CONFIRM_EXACT_RUNS")

    def test_empty_unsupported_lookup_is_never_pending_or_pass(self):
        # Brief requirement: empty/unsupported lookup is observability-incomplete,
        # not CI_PENDING or PASS (SUCCESS).
        for status in ("EMPTY", "ERROR", "UNSUPPORTED"):
            d = _base(connector_status=status, exact_filter_applied=False)
            self.assertNotEqual(d["classification"], "CI_PENDING")
            self.assertNotEqual(d["classification"], "SUCCESS")
            self.assertEqual(d["classification"], "CONNECTOR_OBSERVABILITY_INCOMPLETE")


class ExactHeadShaBindingTests(unittest.TestCase):
    def test_mismatched_head_sha_excluded_as_missing(self):
        # A run at the right name/event/branch but the WRONG head SHA must not
        # satisfy the exact-head evidence requirement.
        runs = [
            _run(1, "build", "pull_request", BRANCH, OTHER_SHA, "completed", "success"),
            _run(2, "test", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
        ]
        d = _base(runs=runs)
        self.assertEqual(d["classification"], "RUNS_MISSING")
        self.assertEqual(d["mismatched_run_count"], 1)
        self.assertEqual(d["exact_run_count"], 1)
        self.assertEqual(d["selected_run_count"], 1)
        self.assertEqual(d["successful_workflow_names"], ["test"])

    def test_exact_sha_binding_present_counts(self):
        runs = [
            _run(1, "build", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
            _run(2, "test", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
        ]
        d = _base(runs=runs)
        self.assertEqual(d["exact_run_count"], 2)
        self.assertEqual(d["classification"], "SUCCESS")

    def test_invalid_head_sha_input_rejected(self):
        d = _base(head_sha="not-a-valid-sha")
        self.assertEqual(d["classification"], "INVALID_INPUT")
        self.assertEqual(d["reason_code"], "INVALID_OR_MISSING_SHA_BINDING")


class CiStateTests(unittest.TestCase):
    def test_non_terminal_run_is_pending(self):
        runs = [
            _run(1, "build", "pull_request", BRANCH, HEAD_SHA, "in_progress"),
            _run(2, "test", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
        ]
        d = _base(runs=runs)
        self.assertEqual(d["classification"], "CI_PENDING")
        self.assertEqual(d["reason_code"], "EXACT_RUNS_NON_TERMINAL")
        self.assertEqual(d["pending_workflow_names"], ["build"])
        self.assertTrue(d["observation_complete"])

    def test_terminal_failure_is_ci_failed(self):
        runs = [
            _run(1, "build", "pull_request", BRANCH, HEAD_SHA, "completed", "failure"),
            _run(2, "test", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
        ]
        d = _base(runs=runs)
        self.assertEqual(d["classification"], "CI_FAILED")
        self.assertEqual(d["reason_code"], "EXACT_RUN_TERMINAL_FAILURE")
        self.assertEqual(d["failed_workflow_names"], ["build"])
        self.assertTrue(d["observation_complete"])

    def test_superseded_attempt_selected(self):
        # Higher attempt wins for the same workflow name; the lower is superseded.
        runs = [
            _run(1, "build", "pull_request", BRANCH, HEAD_SHA, "completed", "failure", attempt=1),
            _run(2, "build", "pull_request", BRANCH, HEAD_SHA, "completed", "success", attempt=2),
        ]
        # Only "build" is in scope here so the supersession logic is exercised
        # without a spurious RUNS_MISSING for an unrelated required workflow.
        d = _base(runs=runs, required_workflow_names=["build"])
        self.assertEqual(d["superseded_run_count"], 1)
        self.assertEqual(d["selected_run_count"], 1)
        self.assertEqual(d["successful_workflow_names"], ["build"])
        self.assertEqual(d["classification"], "SUCCESS")


class NonAuthoritativeTests(unittest.TestCase):
    def test_read_only_projection_grants_no_authority(self):
        runs = [
            _run(1, "build", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
            _run(2, "test", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
        ]
        d = _base(runs=runs)
        self.assertTrue(d["read_only_projection"])
        self.assertFalse(d["merge_authority_granted"])
        self.assertFalse(d["deployment_authority_granted"])
        self.assertFalse(d["production_authority_granted"])
        self.assertFalse(d["audit_authority_granted"])
        self.assertFalse(d["scale_authority_granted"])

    def test_no_authority_granted_in_any_classification(self):
        for kwargs in (
            {},
            {"connector_status": "ERROR"},
            {"connector_status": "EMPTY", "exact_filter_applied": False},
            {"runs": [_run(1, "build", "pull_request", BRANCH, HEAD_SHA, "in_progress")]},
        ):
            d = _base(**kwargs)
            self.assertFalse(d["merge_authority_granted"])
            self.assertFalse(d["deployment_authority_granted"])
            self.assertFalse(d["production_authority_granted"])
            self.assertFalse(d["scale_authority_granted"])
            self.assertFalse(d["audit_authority_granted"])
            self.assertTrue(d["read_only_projection"])


class DeterminismAndSchemaTests(unittest.TestCase):
    def test_identical_inputs_yield_stable_digest(self):
        a = _base()
        b = _base()
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        self.assertEqual(a["classification"], b["classification"])

    def test_different_inputs_yield_different_digest(self):
        a = _base()
        b = _base(runs=[_run(1, "build", "pull_request", BRANCH, HEAD_SHA, "completed", "success")])
        self.assertNotEqual(a["decision_digest"], b["decision_digest"])

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_decision_matches_closed_schema(self):
        runs = [
            _run(1, "build", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
            _run(2, "test", "pull_request", BRANCH, HEAD_SHA, "completed", "success"),
        ]
        d = _base(runs=runs)
        schema = json.load(open(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "schemas", "workflow-run-observability.schema.json")))
        jsonschema.validate(d, schema)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_connector_gap_matches_closed_schema(self):
        d = _base(connector_status="EMPTY", exact_filter_applied=False)
        schema = json.load(open(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "schemas", "workflow-run-observability.schema.json")))
        jsonschema.validate(d, schema)


class InvalidInputTests(unittest.TestCase):
    def test_missing_identity_is_invalid_input(self):
        d = _base(task_id="", repository=REPOSITORY)
        self.assertEqual(d["classification"], "INVALID_INPUT")
        self.assertEqual(d["reason_code"], "REQUIRED_IDENTITY_MISSING")

    def test_invalid_workflow_set_is_invalid_input(self):
        d = _base(required_workflow_names=["build", "build"])  # not unique
        self.assertEqual(d["classification"], "INVALID_INPUT")
        self.assertEqual(d["reason_code"], "INVALID_REQUIRED_WORKFLOW_SET")

    def test_invalid_run_input_is_invalid_input(self):
        d = _base(runs=[{"run_id": "not-int", "workflow_name": "build",
                         "event": "pull_request", "branch": BRANCH,
                         "head_sha": HEAD_SHA, "status": "completed"}])
        self.assertEqual(d["classification"], "INVALID_INPUT")
        self.assertEqual(d["reason_code"], "INVALID_WORKFLOW_RUN_INPUT")


if __name__ == "__main__":
    unittest.main()
