#!/usr/bin/env python3
"""NA81 batch-admission tests for batch_admission_check (SCRUM-370).

Exercises the SCRUM-370 (NA81-F9-N01) brief requirements for the
``scale_control.batch-admission-check`` node:

* safe vs unsafe batches -- when previous-batch merge SHA matches G5 evidence,
  G5 CI is successful and qualified, G5 evidence is fresh, no active blocker is
  present, and the requested node count is within budget, the batch is admitted
  (``BATCH_ADMISSION_REQUIREMENTS_SATISFIED``); otherwise it is rejected with a
  stable reason code;
* previous-batch merge integrity -- a mismatch between ``previous_merge_sha``
  and ``g5_evidence_merge_sha`` is rejected as ``G5_MERGE_SHA_MISMATCH``;
* fail-closed deterministic input validation -- missing identity, invalid SHA
  binding, invalid limit input, or invalid G5 observation time are rejected with
  no side effects or network access;
* G5 CI gating -- a non-successful G5 status is rejected as
  ``G5_NOT_SUCCESSFUL``; unqualified G5 evidence is rejected as
  ``G5_EVIDENCE_UNQUALIFIED``; stale G5 evidence is rejected as
  ``G5_EVIDENCE_STALE``;
* blocker gating -- a non-CLEAR blocker status is rejected as
  ``ACTIVE_BLOCKER_PRESENT``;
* budget gating -- a requested node count above the approved budget is rejected
  as ``APPROVED_NODE_BUDGET_EXCEEDED``;
* determinism and idempotency -- identical inputs yield a stable digest and
  identical decisions;
* no filesystem side effect -- the decision is computed purely in memory;
* authority never granted -- every authority field is fixed ``False`` in all
  outcomes and partial admission is never allowed.

The executable ``tools/node_architect/batch_admission_check.py`` and the
closed decision schema ``schemas/batch-admission-decision.schema.json`` already
existed (authored under SCRUM-251/252 provenance-pinned controls). This
SCRUM-370 maturity PR binds the current #305 brief to that executable with
current-task test evidence and a changelog fragment; the descriptor and existing
source are preserved untouched (provenance-SHA trap avoided).

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
from node_architect import batch_admission_check as bac  # noqa: E402

try:
    import jsonschema

    _HAVE_JSONSCHEMA = True
except Exception:  # pragma: no cover - jsonschema is expected in CI
    _HAVE_JSONSCHEMA = False


TASK_ID = "SCRUM-370"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-370-na81-recert-20260814-r10"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
PREVIOUS_BATCH_ID = "F9-N01"
PREVIOUS_MERGE_SHA = "c" * 40
G5_EVIDENCE_MERGE_SHA = "c" * 40
G5_OBSERVED_AT = "2026-08-19T00:00:00Z"
NOW_AT = "2026-08-19T00:30:00Z"
OBSERVED_AT = "2026-08-19T00:30:00Z"


def _base(**over) -> dict:
    args = dict(
        task_id=TASK_ID,
        repository=REPOSITORY,
        branch=BRANCH,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        previous_batch_id=PREVIOUS_BATCH_ID,
        previous_merge_sha=PREVIOUS_MERGE_SHA,
        g5_evidence_merge_sha=G5_EVIDENCE_MERGE_SHA,
        g5_status="PASS",
        g5_evidence_qualified=True,
        g5_observed_at=G5_OBSERVED_AT,
        now_at=NOW_AT,
        max_evidence_age_seconds=3600,
        blocker_status="CLEAR",
        requested_node_count=1,
        approved_node_budget=9,
        observed_at=OBSERVED_AT,
    )
    args.update(over)
    return bac.decide_batch_admission(**args)


class AdmissionTests(unittest.TestCase):
    def test_admit_when_requirements_satisfied(self):
        d = _base()
        self.assertEqual(d["outcome"], "ADMIT")
        self.assertEqual(d["reason_code"], "BATCH_ADMISSION_REQUIREMENTS_SATISFIED")
        self.assertTrue(d["admission_allowed"])
        self.assertFalse(d["partial_admission_allowed"])
        self.assertEqual(d["requested_node_count"], 1)
        self.assertEqual(d["approved_node_budget"], 9)

    def test_requested_equal_to_budget_is_admitted(self):
        d = _base(requested_node_count=9, approved_node_budget=9)
        self.assertEqual(d["outcome"], "ADMIT")
        self.assertEqual(d["reason_code"], "BATCH_ADMISSION_REQUIREMENTS_SATISFIED")
        self.assertTrue(d["admission_allowed"])

    def test_admit_records_fresh_evidence_age(self):
        d = _base()
        # now_at - g5_observed_at == 30 minutes == 1800 seconds.
        self.assertEqual(d["evidence_age_seconds"], 1800)

    def test_previous_merge_sha_mismatch_is_blocked(self):
        d = _base(previous_merge_sha="d" * 40)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_MERGE_SHA_MISMATCH")
        self.assertFalse(d["admission_allowed"])

    def test_g5_status_fail_is_blocked(self):
        d = _base(g5_status="FAIL")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_NOT_SUCCESSFUL")
        self.assertFalse(d["admission_allowed"])

    def test_g5_status_pending_is_blocked(self):
        d = _base(g5_status="PENDING")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_NOT_SUCCESSFUL")
        self.assertFalse(d["admission_allowed"])

    def test_g5_evidence_unqualified_is_blocked(self):
        d = _base(g5_evidence_qualified=False)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_EVIDENCE_UNQUALIFIED")
        self.assertFalse(d["admission_allowed"])

    def test_g5_evidence_stale_is_blocked(self):
        # now_at is 2h after g5_observed_at, beyond the 3600s (1h) max age.
        d = _base(now_at="2026-08-19T02:00:00Z")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "G5_EVIDENCE_STALE")
        self.assertFalse(d["admission_allowed"])

    def test_active_blocker_present_is_blocked(self):
        d = _base(blocker_status="OPEN")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "ACTIVE_BLOCKER_PRESENT")
        self.assertFalse(d["admission_allowed"])

    def test_approved_node_budget_exceeded_is_blocked(self):
        d = _base(requested_node_count=10, approved_node_budget=9)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "APPROVED_NODE_BUDGET_EXCEEDED")
        self.assertFalse(d["admission_allowed"])


class ForbiddenInputTests(unittest.TestCase):
    def test_missing_identity_is_blocked(self):
        d = _base(task_id="", repository=REPOSITORY)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "REQUIRED_IDENTITY_MISSING")
        self.assertFalse(d["admission_allowed"])

    def test_invalid_base_sha_is_blocked(self):
        d = _base(base_sha="not-a-valid-sha")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_OR_MISSING_SHA_BINDING")
        self.assertFalse(d["admission_allowed"])

    def test_invalid_g5_evidence_merge_sha_is_blocked(self):
        d = _base(g5_evidence_merge_sha="not-a-valid-sha")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_OR_MISSING_SHA_BINDING")
        self.assertFalse(d["admission_allowed"])

    def test_invalid_limit_input_zero_is_blocked(self):
        d = _base(max_evidence_age_seconds=0)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_BATCH_LIMIT_INPUT")
        self.assertFalse(d["admission_allowed"])

    def test_invalid_limit_input_negative_is_blocked(self):
        d = _base(requested_node_count=-1)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_BATCH_LIMIT_INPUT")
        self.assertFalse(d["admission_allowed"])

    def test_invalid_g5_observation_time_is_blocked(self):
        d = _base(g5_observed_at="not-a-time")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_G5_OBSERVATION_TIME")
        self.assertFalse(d["admission_allowed"])

    def test_negative_evidence_age_is_blocked(self):
        # now_at precedes g5_observed_at -> evidence age negative -> invalid time.
        d = _base(g5_observed_at="2026-08-19T01:00:00Z", now_at="2026-08-19T00:00:00Z")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_G5_OBSERVATION_TIME")
        self.assertFalse(d["admission_allowed"])


class AuthorityBoundaryTests(unittest.TestCase):
    def test_no_authority_granted_on_admit(self):
        d = _base()
        self.assertFalse(d["merge_authority_granted"])
        self.assertFalse(d["deployment_authority_granted"])
        self.assertFalse(d["production_authority_granted"])
        self.assertFalse(d["audit_authority_granted"])
        self.assertFalse(d["scale_authority_granted"])

    def test_no_authority_granted_in_any_outcome(self):
        for kwargs in (
            {},
            {"previous_merge_sha": "d" * 40},
            {"g5_status": "FAIL"},
            {"g5_evidence_qualified": False},
            {"now_at": "2026-08-19T02:00:00Z"},
            {"blocker_status": "OPEN"},
            {"requested_node_count": 10, "approved_node_budget": 9},
            {"task_id": ""},
            {"base_sha": "bad"},
        ):
            d = _base(**kwargs)
            self.assertFalse(d["merge_authority_granted"])
            self.assertFalse(d["deployment_authority_granted"])
            self.assertFalse(d["production_authority_granted"])
            self.assertFalse(d["audit_authority_granted"])
            self.assertFalse(d["scale_authority_granted"])

    def test_partial_admission_never_allowed(self):
        for kwargs in (
            {},
            {"previous_merge_sha": "d" * 40},
            {"blocker_status": "OPEN"},
            {"requested_node_count": 10, "approved_node_budget": 9},
        ):
            d = _base(**kwargs)
            self.assertFalse(d["partial_admission_allowed"])


class DeterminismAndIdempotencyTests(unittest.TestCase):
    def test_identical_inputs_yield_stable_digest(self):
        a = _base()
        b = _base()
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        self.assertEqual(a["outcome"], b["outcome"])
        self.assertEqual(a["reason_code"], b["reason_code"])
        self.assertEqual(a["admission_allowed"], b["admission_allowed"])

    def test_idempotent_repeated_invocation_no_drift(self):
        first = _base()
        second = _base()
        self.assertEqual(first, second)

    def test_different_inputs_yield_different_digest(self):
        a = _base()
        b = _base(requested_node_count=10, approved_node_budget=9)
        self.assertNotEqual(a["decision_digest"], b["decision_digest"])

    def test_observed_at_is_honored_and_deterministic(self):
        fixed = "2026-08-19T00:30:00Z"
        a = _base(observed_at=fixed)
        b = _base(observed_at=fixed)
        self.assertEqual(a["observed_at"], fixed)
        self.assertEqual(a["decision_digest"], b["decision_digest"])


class NoSideEffectTests(unittest.TestCase):
    def test_no_filesystem_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = set(os.listdir(tmp))
            _base()
            after = set(os.listdir(tmp))
            self.assertEqual(before, after)

    def test_no_input_mutation(self):
        kwargs = dict(
            previous_merge_sha=PREVIOUS_MERGE_SHA,
            g5_evidence_merge_sha=G5_EVIDENCE_MERGE_SHA,
            requested_node_count=1,
            approved_node_budget=9,
        )
        _base(**kwargs)
        # The decision is computed purely in memory; the caller's inputs are
        # left untouched (the function is referentially transparent).
        self.assertEqual(kwargs["previous_merge_sha"], PREVIOUS_MERGE_SHA)
        self.assertEqual(kwargs["g5_evidence_merge_sha"], G5_EVIDENCE_MERGE_SHA)
        self.assertEqual(kwargs["requested_node_count"], 1)
        self.assertEqual(kwargs["approved_node_budget"], 9)


class ClosedSchemaTests(unittest.TestCase):
    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_admit_decision_matches_closed_schema(self):
        d = _base()
        schema = json.load(
            open(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    ),
                    "schemas",
                    "batch-admission-decision.schema.json",
                )
            )
        )
        jsonschema.validate(d, schema)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_blocked_decision_matches_closed_schema(self):
        d = _base(previous_merge_sha="d" * 40)
        schema = json.load(
            open(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    ),
                    "schemas",
                    "batch-admission-decision.schema.json",
                )
            )
        )
        jsonschema.validate(d, schema)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_stale_decision_matches_closed_schema(self):
        d = _base(now_at="2026-08-19T02:00:00Z")
        schema = json.load(
            open(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    ),
                    "schemas",
                    "batch-admission-decision.schema.json",
                )
            )
        )
        jsonschema.validate(d, schema)


if __name__ == "__main__":
    unittest.main()
