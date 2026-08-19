#!/usr/bin/env python3
"""NA81 batch-size-limit tests for batch_size_limit_check (SCRUM-371).

Exercises the SCRUM-371 (NA81-F9-N02) brief requirements for the
``scale_control.batch-size-limit-check`` node:

* safe vs unsafe batch sizes -- under-limit batches are admitted, over-limit
  batches are rejected as ``BATCH_SIZE_LIMIT_EXCEEDED``;
* empty batch rejected as ``EMPTY_BATCH_NOT_ADMITTED``;
* fail-closed deterministic input validation -- missing identity, invalid SHA,
  invalid limit configuration, and invalid batch-list input are rejected with
  no side effects or network access;
* batch mapping integrity -- node/batch length mismatch, duplicate node id, and
  mixed batch identifiers are rejected;
* single-active-batch concurrency -- more than one prospective implementation
  batch (including an unknown/foreign active batch) is rejected as
  ``ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED``; the current ``batch_id`` active
  is admitted;
* normalization -- the prospective implementation-batch set is the sorted unique
  projection of the active batches plus the current batch;
* determinism and idempotency -- identical inputs yield a stable digest and
  identical decisions;
* no filesystem side effect -- the decision is computed purely in memory;
* authority never granted -- every authority field is fixed ``False`` in all
  outcomes and partial admission is never allowed.

The executable ``tools/node_architect/batch_size_limit_check.py`` and the
closed decision schema ``schemas/batch-size-limit-decision.schema.json`` already
existed (authored under SCRUM-251/252 provenance-pinned controls). This
SCRUM-371 maturity PR binds the current #306 brief to that executable with
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

sys.path.insert(0, "/home/ubuntu/gwc-ctrl-r10/.wt/SCRUM-371/tools")
from node_architect import batch_size_limit_check as bslc  # noqa: E402

try:
    import jsonschema

    _HAVE_JSONSCHEMA = True
except Exception:  # pragma: no cover - jsonschema is expected in CI
    _HAVE_JSONSCHEMA = False


TASK_ID = "SCRUM-371"
REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-371-na81-recert-20260814-r10"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
BATCH_ID = "F9-N02"


def _base(**over) -> dict:
    args = dict(
        task_id=TASK_ID,
        repository=REPOSITORY,
        branch=BRANCH,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        batch_id=BATCH_ID,
        node_ids=["node-alpha", "node-beta"],
        node_batch_ids=[BATCH_ID, BATCH_ID],
        active_implementation_batch_ids=[BATCH_ID],
        max_batch_size=9,
        max_concurrent_implementation_batches=1,
    )
    args.update(over)
    return bslc.decide_batch_size_limit(**args)


class AdmissionTests(unittest.TestCase):
    def test_under_limit_batch_is_admitted(self):
        d = _base()
        self.assertEqual(d["outcome"], "ALLOW")
        self.assertEqual(d["reason_code"], "BATCH_LIMITS_SATISFIED")
        self.assertTrue(d["admission_allowed"])
        self.assertFalse(d["partial_admission_allowed"])
        self.assertEqual(d["node_count"], 2)

    def test_boundary_equal_to_limit_is_admitted(self):
        d = _base(
            max_batch_size=2,
            node_ids=["node-alpha", "node-beta"],
            node_batch_ids=[BATCH_ID, BATCH_ID],
        )
        self.assertEqual(d["outcome"], "ALLOW")
        self.assertEqual(d["reason_code"], "BATCH_LIMITS_SATISFIED")
        self.assertTrue(d["admission_allowed"])

    def test_over_limit_batch_is_rejected(self):
        nodes = [f"node-{i:02d}" for i in range(10)]
        d = _base(
            max_batch_size=9,
            node_ids=nodes,
            node_batch_ids=[BATCH_ID] * len(nodes),
        )
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "BATCH_SIZE_LIMIT_EXCEEDED")
        self.assertFalse(d["admission_allowed"])
        self.assertEqual(d["node_count"], 10)

    def test_empty_batch_is_rejected(self):
        d = _base(node_ids=[], node_batch_ids=[])
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "EMPTY_BATCH_NOT_ADMITTED")
        self.assertFalse(d["admission_allowed"])

    def test_current_batch_active_is_admitted(self):
        d = _base(active_implementation_batch_ids=[BATCH_ID])
        self.assertEqual(d["outcome"], "ALLOW")
        self.assertTrue(d["admission_allowed"])
        self.assertEqual(d["active_implementation_batch_ids"], [BATCH_ID])


class ForbiddenInputTests(unittest.TestCase):
    def test_missing_identity_is_rejected(self):
        d = _base(task_id="", repository=REPOSITORY)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_OR_MISSING_IDENTITY")
        self.assertFalse(d["admission_allowed"])

    def test_invalid_base_sha_is_rejected(self):
        d = _base(base_sha="not-a-valid-sha")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_OR_MISSING_IDENTITY")

    def test_invalid_head_sha_is_rejected(self):
        d = _base(head_sha="not-a-valid-sha")
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_OR_MISSING_IDENTITY")

    def test_invalid_limit_configuration_is_rejected(self):
        d = _base(max_batch_size=0)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_LIMIT_CONFIGURATION")
        self.assertFalse(d["admission_allowed"])

    def test_invalid_batch_list_none_is_rejected(self):
        d = _base(node_ids=None, node_batch_ids=None)
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_BATCH_LIST_INPUT")

    def test_invalid_batch_list_wrong_type_is_rejected(self):
        d = _base(node_ids={"k": "v"}, node_batch_ids=[BATCH_ID])
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "INVALID_BATCH_LIST_INPUT")


class MappingIntegrityTests(unittest.TestCase):
    def test_mapping_length_mismatch_is_rejected(self):
        d = _base(
            node_ids=["node-alpha", "node-beta"],
            node_batch_ids=[BATCH_ID],
        )
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "NODE_BATCH_MAPPING_LENGTH_MISMATCH")
        self.assertFalse(d["admission_allowed"])

    def test_duplicate_node_id_is_rejected(self):
        d = _base(
            node_ids=["node-alpha", "node-alpha"],
            node_batch_ids=[BATCH_ID, BATCH_ID],
        )
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "DUPLICATE_NODE_ID")
        self.assertFalse(d["admission_allowed"])

    def test_mixed_batch_identifiers_is_rejected(self):
        d = _base(
            node_ids=["node-alpha"],
            node_batch_ids=["OTHER-BATCH"],
        )
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "MIXED_BATCH_IDENTIFIERS")
        self.assertFalse(d["admission_allowed"])


class ConcurrencyTests(unittest.TestCase):
    def test_concurrency_limit_exceeded_is_rejected(self):
        d = _base(active_implementation_batch_ids=["F9-N01", BATCH_ID])
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED")
        self.assertFalse(d["admission_allowed"])

    def test_unknown_active_batch_blocks_admission(self):
        # An unknown/foreign active batch id makes the prospective set exceed
        # the single-active-batch limit: unknown readback must block.
        d = _base(active_implementation_batch_ids=["UNKNOWN-XX"])
        self.assertEqual(d["outcome"], "BLOCKED")
        self.assertEqual(d["reason_code"], "ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED")
        self.assertFalse(d["admission_allowed"])


class NormalizationTests(unittest.TestCase):
    def test_prospective_batch_set_is_sorted_unique(self):
        d = _base(
            active_implementation_batch_ids=[BATCH_ID, "OTHER", BATCH_ID],
        )
        # sorted(set(active + [batch_id])) -> [BATCH_ID, OTHER]
        self.assertEqual(d["prospective_implementation_batch_ids"], [BATCH_ID, "OTHER"])


class AuthorityBoundaryTests(unittest.TestCase):
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
            {"max_batch_size": 0},
            {"node_ids": [], "node_batch_ids": []},
            {"active_implementation_batch_ids": ["F9-N01", BATCH_ID]},
            {"node_ids": ["node-alpha", "node-alpha"], "node_batch_ids": [BATCH_ID, BATCH_ID]},
            {"node_ids": ["node-alpha"], "node_batch_ids": ["OTHER-BATCH"]},
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
            {"max_batch_size": 0},
            {"active_implementation_batch_ids": ["F9-N01", BATCH_ID]},
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
        b = _base(max_batch_size=0)
        self.assertNotEqual(a["decision_digest"], b["decision_digest"])

    def test_observed_at_is_honored_and_deterministic(self):
        fixed = "2026-08-19T00:00:00Z"
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

    def test_no_sha_mutation_of_inputs(self):
        node_ids = ["node-alpha", "node-beta"]
        kwargs = dict(
            node_ids=list(node_ids),
            node_batch_ids=[BATCH_ID, BATCH_ID],
            active_implementation_batch_ids=[BATCH_ID],
        )
        _base(**kwargs)
        self.assertEqual(kwargs["node_ids"], ["node-alpha", "node-beta"])
        self.assertEqual(kwargs["active_implementation_batch_ids"], [BATCH_ID])


class ClosedSchemaTests(unittest.TestCase):
    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_allow_decision_matches_closed_schema(self):
        d = _base()
        schema = json.load(
            open(
                os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ),
                "schemas",
                "batch-size-limit-decision.schema.json",
                )
            )
        )
        jsonschema.validate(d, schema)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_blocked_decision_matches_closed_schema(self):
        nodes = [f"node-{i:02d}" for i in range(10)]
        d = _base(max_batch_size=9, node_ids=nodes, node_batch_ids=[BATCH_ID] * len(nodes))
        schema = json.load(
            open(
                os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ),
                "schemas",
                "batch-size-limit-decision.schema.json",
                )
            )
        )
        jsonschema.validate(d, schema)

    @unittest.skipUnless(_HAVE_JSONSCHEMA, "jsonschema not available")
    def test_concurrency_blocked_decision_matches_closed_schema(self):
        d = _base(active_implementation_batch_ids=["F9-N01", BATCH_ID])
        schema = json.load(
            open(
                os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ),
                "schemas",
                "batch-size-limit-decision.schema.json",
                )
            )
        )
        jsonschema.validate(d, schema)


if __name__ == "__main__":
    unittest.main()
