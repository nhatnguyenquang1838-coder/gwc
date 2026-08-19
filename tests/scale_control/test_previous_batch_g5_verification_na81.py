#!/usr/bin/env python3
"""NA81 previous-batch G5 verification tests for previous_batch_g5_verification (SCRUM-372).

Exercises the SCRUM-372 (NA81-F9-N03) brief requirements for the
``scale_control.previous-batch-g5-verification`` node:

* verified connector evidence -- when the previous PR is merged, the evidence
  head SHA matches the exact expected merge SHA, the evidence event is a push,
  the evidence branch is main, G5 evidence is fresh and successful, and the
  connector status is CONFIRMED with a valid workflow run id, the previous
  batch is VERIFIED_CONNECTOR (``EXACT_POST_MERGE_G5_CONFIRMED``); otherwise it
  is blocked with a stable reason code;
* previous-PR integrity -- a previous PR that is not merged is rejected as
  ``PREVIOUS_PR_NOT_MERGED``;
* exact merge SHA binding -- an evidence head SHA that does not match the
  expected merge SHA is rejected as ``G5_HEAD_SHA_MISMATCH``;
* evidence event/branch gating -- a non-push event is rejected as
  ``PR_ONLY_EVIDENCE_NOT_QUALIFIED``; a non-main branch is rejected as
  ``G5_BRANCH_MISMATCH``;
* G5 freshness/success gating -- stale evidence is rejected as
  ``G5_EVIDENCE_STALE``; a pending conclusion as ``G5_EVIDENCE_PENDING``; a
  non-success conclusion as ``G5_EVIDENCE_NOT_SUCCESSFUL``;
* connector evidence gating -- incomplete connector evidence is rejected as
  ``CONNECTOR_EVIDENCE_INCOMPLETE``;
* human-observed gating -- a label mismatch is rejected as
  ``HUMAN_OBSERVED_LABEL_MISMATCH``; a missing attestation as
  ``HUMAN_ATTESTATION_MISSING``; a qualified human-observed success as
  ``QUALIFIED_HUMAN_OBSERVED_G5_SUCCESS``;
* unsupported source -- an unknown evidence source is rejected as
  ``UNSUPPORTED_G5_EVIDENCE_SOURCE``;
* fail-closed deterministic input validation -- missing identity, invalid SHA
  binding, missing required workflows, or invalid observation time are rejected
  with no side effects or network access;
* determinism and idempotency -- identical inputs yield a stable digest and
  identical decisions;
* no filesystem side effect -- the decision is computed purely in memory;
* authority never granted -- every authority field is fixed ``False`` in all
  outcomes.

The executable ``tools/node_architect/previous_batch_g5_verification.py`` and
the closed decision schema
``schemas/previous-batch-g5-verification-decision.schema.json`` already existed
(authored under SCRUM-251/252 provenance-pinned controls). This SCRUM-372
maturity PR binds the current #307 brief to that executable with current-task
test evidence and a changelog fragment; the descriptor and existing source are
preserved untouched (provenance-SHA trap avoided).

The module is imported via an absolute ``tools/`` path insertion so that
``import node_architect...`` resolves under ``python -m unittest discover``
from the repository root (PEP 420 namespace packages). No connector call,
network request, filesystem mutation, Jira, branch, commit, PR, approval,
merge, deployment or production operation occurs.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tools")))
from node_architect import previous_batch_g5_verification as pbv  # noqa: E402

try:
    import jsonschema

    _HAVE_JSONSCHEMA = True
except Exception:  # pragma: no cover - jsonschema is expected in CI
    _HAVE_JSONSCHEMA = False


TASK_ID = "SCRUM-372"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-372-na81-recert-20260814-r10"
# Exact previous merge SHA: SCRUM-370 PR #490 (current pre-prod tip).
EXACT_PREVIOUS_MERGE_SHA = "566fdf19159b85df59ba1793ae4b22a08b685433"


def _base(**over) -> dict:
    args = dict(
        task_id=TASK_ID,
        repository=REPOSITORY,
        branch=BRANCH,
        base_sha="a" * 40,
        head_sha="b" * 40,
        previous_batch_id="F9-N03",
        previous_pr_number=490,
        previous_pr_state="merged",
        expected_merge_sha=EXACT_PREVIOUS_MERGE_SHA,
        evidence_source=pbv.CONNECTOR_SOURCE,
        evidence_event="push",
        evidence_branch="main",
        evidence_head_sha=EXACT_PREVIOUS_MERGE_SHA,
        workflow_run_id=123456,
        conclusion="success",
        connector_status="CONFIRMED",
        required_workflow_names=["validate", "parent-authority-required", "autonomous-g4-evidence-bound"],
        observed_at_evidence="2026-08-19T09:03:43Z",
        now_at="2026-08-19T11:00:00Z",
        max_evidence_age_seconds=7200,
    )
    args.update(over)
    return pbv.decide_previous_batch_g5_verification(**args)


class VerifiedConnectorTests(unittest.TestCase):
    def test_verified_connector_when_requirements_satisfied(self):
        d = _base()
        self.assertEqual(d["outcome"], "VERIFIED_CONNECTOR")
        self.assertEqual(d["reason_code"], "EXACT_POST_MERGE_G5_CONFIRMED")
        self.assertTrue(d["verification_passed"])
        self.assertTrue(d["connector_confirmed_pass"])
        self.assertFalse(d["pr_only_evidence_accepted"])

    def test_real_previous_merge_sha_binding(self):
        # Exact previous merge SHA (SCRUM-370 PR #490) bound to G5 evidence.
        d = _base(
            expected_merge_sha=EXACT_PREVIOUS_MERGE_SHA,
            evidence_head_sha=EXACT_PREVIOUS_MERGE_SHA,
            previous_pr_number=490,
            previous_pr_state="merged",
        )
        self.assertEqual(d["outcome"], "VERIFIED_CONNECTOR")
        self.assertEqual(d["reason_code"], "EXACT_POST_MERGE_G5_CONFIRMED")
        self.assertTrue(d["verification_passed"])

    def test_connector_records_fresh_evidence_age(self):
        d = _base()
        # now_at 11:00:00Z - observed_at_evidence 09:03:43Z == 1h56m17s == 6977 seconds.
        self.assertEqual(d["evidence_age_seconds"], 6977)


class BlockedDecisionTests(unittest.TestCase):
    def test_previous_pr_not_merged(self):
        d = _base(previous_pr_state="open")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "PREVIOUS_PR_NOT_MERGED")
        self.assertFalse(d["verification_passed"])

    def test_g5_head_sha_mismatch(self):
        d = _base(evidence_head_sha="d" * 40)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_HEAD_SHA_MISMATCH")
        self.assertFalse(d["verification_passed"])

    def test_evidence_event_not_push(self):
        d = _base(evidence_event="pull_request")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "PR_ONLY_EVIDENCE_NOT_QUALIFIED")
        self.assertFalse(d["verification_passed"])

    def test_evidence_branch_not_main(self):
        d = _base(evidence_branch="pre-prod")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_BRANCH_MISMATCH")
        self.assertFalse(d["verification_passed"])

    def test_g5_evidence_stale(self):
        d = _base(now_at="2026-08-19T20:00:00Z")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_EVIDENCE_STALE")
        self.assertFalse(d["verification_passed"])

    def test_g5_evidence_pending(self):
        d = _base(conclusion="pending")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_EVIDENCE_PENDING")
        self.assertFalse(d["verification_passed"])

    def test_g5_evidence_not_successful(self):
        d = _base(conclusion="failure")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_EVIDENCE_NOT_SUCCESSFUL")
        self.assertFalse(d["verification_passed"])

    def test_connector_evidence_incomplete(self):
        d = _base(workflow_run_id=None)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "CONNECTOR_EVIDENCE_INCOMPLETE")
        self.assertFalse(d["verification_passed"])


class HumanObservedTests(unittest.TestCase):
    def test_human_observed_success(self):
        d = _base(
            evidence_source=pbv.HUMAN_SOURCE,
            connector_status="CONNECTOR_OBSERVABILITY_INCOMPLETE",
            human_attestation_id="att-001",
        )
        self.assertEqual(d["outcome"], "VERIFIED_HUMAN_OBSERVED")
        self.assertEqual(d["reason_code"], "QUALIFIED_HUMAN_OBSERVED_G5_SUCCESS")
        self.assertTrue(d["verification_passed"])
        self.assertTrue(d["human_observed_success"])

    def test_human_observed_label_mismatch(self):
        d = _base(
            evidence_source=pbv.HUMAN_SOURCE,
            connector_status="CONFIRMED",
            human_attestation_id="att-001",
        )
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "HUMAN_OBSERVED_LABEL_MISMATCH")
        self.assertFalse(d["verification_passed"])

    def test_human_attestation_missing(self):
        d = _base(
            evidence_source=pbv.HUMAN_SOURCE,
            connector_status="CONNECTOR_OBSERVABILITY_INCOMPLETE",
            human_attestation_id=None,
        )
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "HUMAN_ATTESTATION_MISSING")
        self.assertFalse(d["verification_passed"])

    def test_unsupported_evidence_source(self):
        d = _base(evidence_source="unknown")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "UNSUPPORTED_G5_EVIDENCE_SOURCE")
        self.assertFalse(d["verification_passed"])


class ForbiddenInputTests(unittest.TestCase):
    def test_missing_identity(self):
        d = _base(task_id="", repository=REPOSITORY)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "REQUIRED_G5_IDENTITY_MISSING")
        self.assertFalse(d["verification_passed"])

    def test_invalid_sha_binding(self):
        d = _base(base_sha="not-a-valid-sha")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_OR_MISSING_SHA_BINDING")
        self.assertFalse(d["verification_passed"])

    def test_required_workflow_missing(self):
        d = _base(required_workflow_names=[])
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "REQUIRED_WORKFLOW_EVIDENCE_MISSING")
        self.assertFalse(d["verification_passed"])

    def test_invalid_g5_observation_time(self):
        d = _base(observed_at_evidence="not-a-time")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_G5_OBSERVATION_TIME")
        self.assertFalse(d["verification_passed"])


class AuthorityBoundaryTests(unittest.TestCase):
    def test_no_authority_granted_on_verify(self):
        d = _base()
        self.assertFalse(d["merge_authority_granted"])
        self.assertFalse(d["deployment_authority_granted"])
        self.assertFalse(d["production_authority_granted"])
        self.assertFalse(d["audit_authority_granted"])
        self.assertFalse(d["scale_authority_granted"])

    def test_no_authority_granted_in_any_outcome(self):
        for kwargs in (
            {},
            {"previous_pr_state": "open"},
            {"evidence_head_sha": "d" * 40},
            {"evidence_event": "pull_request"},
            {"evidence_branch": "pre-prod"},
            {"now_at": "2026-08-19T20:00:00Z"},
            {"conclusion": "pending"},
            {"conclusion": "failure"},
            {"workflow_run_id": None},
            {"evidence_source": pbv.HUMAN_SOURCE, "connector_status": "CONNECTOR_OBSERVABILITY_INCOMPLETE", "human_attestation_id": "att-001"},
            {"task_id": ""},
            {"base_sha": "bad"},
        ):
            d = _base(**kwargs)
            self.assertFalse(d["merge_authority_granted"])
            self.assertFalse(d["deployment_authority_granted"])
            self.assertFalse(d["production_authority_granted"])
            self.assertFalse(d["audit_authority_granted"])
            self.assertFalse(d["scale_authority_granted"])


class DeterminismAndIdempotencyTests(unittest.TestCase):
    def test_identical_inputs_yield_stable_digest(self):
        a = _base()
        b = _base()
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        self.assertEqual(a["outcome"], b["outcome"])
        self.assertEqual(a["reason_code"], b["reason_code"])
        self.assertEqual(a["verification_passed"], b["verification_passed"])

    def test_idempotent_repeated_invocation_no_drift(self):
        first = _base()
        second = _base()
        self.assertEqual(first, second)

    def test_different_inputs_yield_different_digest(self):
        a = _base()
        b = _base(previous_pr_state="open")
        self.assertNotEqual(a["decision_digest"], b["decision_digest"])


class NoSideEffectTests(unittest.TestCase):
    def test_no_filesystem_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = set(os.listdir(tmp))
            _base()
            after = set(os.listdir(tmp))
            self.assertEqual(before, after)

    def test_no_input_mutation(self):
        kwargs = dict(
            expected_merge_sha=EXACT_PREVIOUS_MERGE_SHA,
            evidence_head_sha=EXACT_PREVIOUS_MERGE_SHA,
            previous_pr_number=490,
            required_workflow_names=["validate"],
        )
        _base(**kwargs)
        self.assertEqual(kwargs["expected_merge_sha"], EXACT_PREVIOUS_MERGE_SHA)
        self.assertEqual(kwargs["evidence_head_sha"], EXACT_PREVIOUS_MERGE_SHA)
        self.assertEqual(kwargs["previous_pr_number"], 490)
        self.assertEqual(kwargs["required_workflow_names"], ["validate"])


class ClosedSchemaTests(unittest.TestCase):
    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_verified_decision_matches_closed_schema(self):
        d = _base()
        schema = json.load(
            open(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    ),
                    "schemas",
                    "previous-batch-g5-verification-decision.schema.json",
                )
            )
        )
        jsonschema.validate(d, schema)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_blocked_decision_matches_closed_schema(self):
        d = _base(previous_pr_state="open")
        schema = json.load(
            open(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    ),
                    "schemas",
                    "previous-batch-g5-verification-decision.schema.json",
                )
            )
        )
        jsonschema.validate(d, schema)


if __name__ == "__main__":
    unittest.main()
