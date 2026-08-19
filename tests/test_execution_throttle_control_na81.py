#!/usr/bin/env python3
"""NA81 capacity-control tests for execution_throttle_control (SCRUM-374).

Exercises the SCRUM-374 (NA81-F9-N05) brief requirements for the
``scale_control.execution-throttle-control`` node:

* single sequential batch admission — more than one active implementation
  batch is rejected as a concurrency-limit violation, and an active batch that
  is not the current ``batch_id`` is rejected as ``OTHER_BATCH_ALREADY_ACTIVE``;
* previous-batch terminal gate — a non-terminal previous batch blocks admission;
* deterministic capacity bound — throttling occurs on failure-signal cooldown,
  insufficient capacity, and when the requested rate exceeds what capacity or
  policy allows (``CAPACITY_BOUNDED_THROTTLE``);
* active-lane ordering preserved — the node never reorders or merges batches and
  never grants task/gate authority;
* fail-closed deterministic input validation (no network, no side effects).

The executable ``tools/node_architect/execution_throttle_control.py`` and the
closed decision schema ``schemas/execution-throttle-decision.schema.json``
already existed (authored under SCRUM-251/252 provenance-pinned controls). This
SCRUM-374 maturity PR binds the current #309 brief to that executable with
current-task test evidence and a changelog fragment; the descriptor and
existing source are preserved untouched (provenance-SHA trap avoided).

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
from node_architect import execution_throttle_control as etc  # noqa: E402

try:
    import jsonschema
    _HAVE_JSONSCHEMA = True
except Exception:  # pragma: no cover - jsonschema is expected in CI
    _HAVE_JSONSCHEMA = False


TASK_ID = "SCRUM-374"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-374-na81-recert-20260814-r10"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
BATCH_ID = "F9-N05"


def _base(**over) -> dict:
    args = dict(
        task_id=TASK_ID,
        repository=REPOSITORY,
        branch=BRANCH,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        batch_id=BATCH_ID,
        active_implementation_batch_ids=[],
        requested_parallelism=2,
        max_parallelism=3,
        capacity_units_available=6,
        capacity_units_per_worker=2,
        recent_failure_rate=0.1,
        failure_rate_threshold=0.5,
        cooldown_active=False,
        previous_batch_terminal=True,
    )
    args.update(over)
    return etc.decide_execution_throttle(**args)


class AllowTests(unittest.TestCase):
    def test_bounded_rate_within_capacity_is_allowed(self):
        d = _base()
        self.assertEqual(d["outcome"], "ALLOW")
        self.assertEqual(d["reason_code"], "REQUESTED_RATE_WITHIN_BOUNDS")
        # available_parallelism = 6 // 2 = 3; min(2, 3, 3) = 2
        self.assertEqual(d["available_parallelism"], 3)
        self.assertEqual(d["allowed_parallelism"], 2)
        self.assertTrue(d["execution_allowed"])

    def test_partial_execution_flagged_when_capacity_bounded(self):
        # requested 5, capacity allows 3 (6//2), max 3 -> allowed 3 < requested
        d = _base(requested_parallelism=5, max_parallelism=5)
        self.assertEqual(d["outcome"], "THROTTLE")
        self.assertEqual(d["reason_code"], "CAPACITY_BOUNDED_THROTTLE")
        self.assertEqual(d["allowed_parallelism"], 3)
        self.assertTrue(d["partial_execution_allowed"])
        self.assertTrue(d["execution_allowed"])


class SingleBatchAdmissionTests(unittest.TestCase):
    def test_multiple_active_batches_rejected(self):
        d = _base(active_implementation_batch_ids=["F9-N01", "F9-N05"])
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED")
        self.assertFalse(d["execution_allowed"])

    def test_other_batch_already_active_rejected(self):
        d = _base(active_implementation_batch_ids=["F9-N01"])
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "OTHER_BATCH_ALREADY_ACTIVE")
        self.assertFalse(d["execution_allowed"])

    def test_current_batch_active_is_admitted(self):
        d = _base(active_implementation_batch_ids=[BATCH_ID])
        self.assertTrue(d["execution_allowed"])
        self.assertEqual(d["active_implementation_batch_ids"], [BATCH_ID])

    def test_previous_batch_not_terminal_blocks(self):
        d = _base(previous_batch_terminal=False)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "PREVIOUS_BATCH_NOT_TERMINAL")
        self.assertFalse(d["execution_allowed"])


class ThrottleTests(unittest.TestCase):
    def test_failure_signal_cooldown_throttles(self):
        d = _base(cooldown_active=True)
        self.assertEqual(d["outcome"], "THROTTLE")
        self.assertEqual(d["reason_code"], "FAILURE_SIGNAL_COOLDOWN")
        self.assertEqual(d["allowed_parallelism"], 0)
        self.assertFalse(d["execution_allowed"])

    def test_failure_rate_at_or_above_threshold_throttles(self):
        d = _base(recent_failure_rate=0.5, failure_rate_threshold=0.5)
        self.assertEqual(d["outcome"], "THROTTLE")
        self.assertEqual(d["reason_code"], "FAILURE_SIGNAL_COOLDOWN")
        self.assertFalse(d["execution_allowed"])

    def test_insufficient_capacity_throttles(self):
        d = _base(capacity_units_available=0)
        self.assertEqual(d["outcome"], "THROTTLE")
        self.assertEqual(d["reason_code"], "INSUFFICIENT_CAPACITY")
        self.assertEqual(d["available_parallelism"], 0)
        self.assertFalse(d["execution_allowed"])


class NonAuthorityTests(unittest.TestCase):
    def test_no_authority_granted_on_allow(self):
        d = _base()
        self.assertFalse(d["merge_authority_granted"])
        self.assertFalse(d["deployment_authority_granted"])
        self.assertFalse(d["production_authority_granted"])
        self.assertFalse(d["audit_authority_granted"])
        self.assertFalse(d["scale_authority_granted"])

    def test_no_authority_granted_in_any_outcome(self):
        for kwargs in (
            {},
            {"cooldown_active": True},
            {"previous_batch_terminal": False},
            {"active_implementation_batch_ids": ["F9-N01"]},
            {"capacity_units_available": 0},
        ):
            d = _base(**kwargs)
            self.assertFalse(d["merge_authority_granted"])
            self.assertFalse(d["deployment_authority_granted"])
            self.assertFalse(d["production_authority_granted"])
            self.assertFalse(d["scale_authority_granted"])


class InvalidInputTests(unittest.TestCase):
    def test_missing_identity_is_invalid_input(self):
        d = _base(task_id="", repository=REPOSITORY)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "REQUIRED_IDENTITY_MISSING")
        self.assertFalse(d["execution_allowed"])

    def test_invalid_head_sha_is_invalid_input(self):
        d = _base(head_sha="not-a-valid-sha")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_OR_MISSING_SHA_BINDING")

    def test_invalid_capacity_is_invalid_input(self):
        d = _base(capacity_units_available=-1)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_CAPACITY_INPUT")

    def test_invalid_failure_rate_is_invalid_input(self):
        d = _base(failure_rate_threshold=0.0)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_FAILURE_RATE_INPUT")


class DeterminismAndSchemaTests(unittest.TestCase):
    def test_identical_inputs_yield_stable_digest(self):
        a = _base()
        b = _base()
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        self.assertEqual(a["outcome"], b["outcome"])

    def test_different_inputs_yield_different_digest(self):
        a = _base()
        b = _base(cooldown_active=True)
        self.assertNotEqual(a["decision_digest"], b["decision_digest"])

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_allow_decision_matches_closed_schema(self):
        d = _base()
        schema = json.load(open(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "schemas", "execution-throttle-decision.schema.json")))
        jsonschema.validate(d, schema)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_throttle_decision_matches_closed_schema(self):
        d = _base(cooldown_active=True)
        schema = json.load(open(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "schemas", "execution-throttle-decision.schema.json")))
        jsonschema.validate(d, schema)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_blocked_decision_matches_closed_schema(self):
        d = _base(active_implementation_batch_ids=["F9-N01"])
        schema = json.load(open(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "schemas", "execution-throttle-decision.schema.json")))
        jsonschema.validate(d, schema)


if __name__ == "__main__":
    unittest.main()
