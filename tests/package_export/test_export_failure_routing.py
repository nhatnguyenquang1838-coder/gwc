#!/usr/bin/env python3
"""Tests for package_export.export-failure-routing (SCRUM-237, M5_REPLAY_SAFE)."""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "node_architect" / "package_export"))

from export_failure_routing import (  # noqa: E402
    REASON_AUTHORITY_VIOLATION,
    REASON_FAILURE_UNMAPPED,
    REASON_REPLAY_CONFLICT,
    REASON_RETRY_EXHAUSTED,
    REASON_UNKNOWN_OUTCOME,
    ROUTE_BOUNDED_RETRY,
    ROUTE_FAIL_CLOSED,
    ROUTE_HUMAN_REQUIRED,
    ROUTE_REBUILD_STAGING,
    ROUTE_REPAIR_INPUT,
    ROUTE_REVERIFY_READBACK,
    RouteDecision,
    RoutingContext,
    compute_decision_digest,
    route_failure,
)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


class TestEveryUpstreamReason(unittest.TestCase):
    """AC-1: decision table covers every upstream reason namespace 229-236."""

    # reason_code -> expected route
    TABLE = {
        # entry-schema
        "SCHEMA_INVALID": ROUTE_REPAIR_INPUT,
        # export-manifest-generation
        "MANIFEST_ENTRY_INVALID": ROUTE_REPAIR_INPUT,
        "MANIFEST_DIGEST_MISMATCH": ROUTE_REPAIR_INPUT,
        "MANIFEST_SOURCE_MISSING": ROUTE_REPAIR_INPUT,
        "MANIFEST_IDEMPOTENT_REPLAY": ROUTE_REVERIFY_READBACK,
        # source-path-safety
        "SOURCE_REQUIRED_MISSING": ROUTE_REPAIR_INPUT,
        "SOURCE_OPTIONAL_MISSING": ROUTE_REVERIFY_READBACK,
        "SOURCE_NOT_REGULAR_FILE": ROUTE_REPAIR_INPUT,
        "SOURCE_READBACK_FAILED": ROUTE_REVERIFY_READBACK,
        "SOURCE_PATH_TRAVERSAL": ROUTE_HUMAN_REQUIRED,
        "SOURCE_PATH_ESCAPES_ROOT": ROUTE_HUMAN_REQUIRED,
        "SOURCE_SYMLINK_ESCAPE": ROUTE_HUMAN_REQUIRED,
        "SOURCE_PATH_ABSOLUTE": ROUTE_HUMAN_REQUIRED,
        "SOURCE_PATH_BACKSLASH": ROUTE_HUMAN_REQUIRED,
        "SOURCE_PATH_EMPTY": ROUTE_HUMAN_REQUIRED,
        # target-path-safety
        "TARGET_DUPLICATE": ROUTE_HUMAN_REQUIRED,
        "TARGET_CASE_COLLISION": ROUTE_HUMAN_REQUIRED,
        "TARGET_OVERWRITE_FORBIDDEN": ROUTE_HUMAN_REQUIRED,
        "TARGET_PREFIX_FORBIDDEN": ROUTE_HUMAN_REQUIRED,
        "TARGET_PATH_TRAVERSAL": ROUTE_HUMAN_REQUIRED,
        "TARGET_PATH_ESCAPES_ROOT": ROUTE_HUMAN_REQUIRED,
        "TARGET_SYMLINK_ESCAPE": ROUTE_HUMAN_REQUIRED,
        "TARGET_PATH_ABSOLUTE": ROUTE_HUMAN_REQUIRED,
        "TARGET_PATH_BACKSLASH": ROUTE_HUMAN_REQUIRED,
        "TARGET_PATH_EMPTY": ROUTE_HUMAN_REQUIRED,
        "TARGET_IDEMPOTENT_EXISTING": ROUTE_REVERIFY_READBACK,
        # governance-tree-build
        "TREE_PARTIAL_OUTPUT": ROUTE_REBUILD_STAGING,
        "TREE_READBACK_MISMATCH": ROUTE_REBUILD_STAGING,
        "TREE_COPY_MISMATCH": ROUTE_REBUILD_STAGING,
        "TREE_STALE_SOURCE": ROUTE_REBUILD_STAGING,
        "TREE_TARGET_COLLISION": ROUTE_REBUILD_STAGING,
        "TREE_REQUIRED_SOURCE_MISSING": ROUTE_REPAIR_INPUT,
        "TREE_REPLAY_CONFLICT": ROUTE_HUMAN_REQUIRED,
        "TREE_IDEMPOTENT_REPLAY": ROUTE_REVERIFY_READBACK,
        # governance-tree-build NA81-F7 topology (SCRUM-356)
        "TREE_DUPLICATE_ENTRY": ROUTE_REPAIR_INPUT,
        "TREE_MISSING_PARENT": ROUTE_REPAIR_INPUT,
        "TREE_AMBIGUOUS_ORDER": ROUTE_REPAIR_INPUT,
        "TREE_CYCLE_DETECTED": ROUTE_HUMAN_REQUIRED,
        # deterministic-hash
        "HASH_TARGET_MISSING": ROUTE_REPAIR_INPUT,
        "HASH_SOURCE_MISMATCH": ROUTE_HUMAN_REQUIRED,
        "HASH_TARGET_MISMATCH": ROUTE_HUMAN_REQUIRED,
        "HASH_BYTE_COUNT_MISMATCH": ROUTE_HUMAN_REQUIRED,
        "HASH_TREE_DIGEST_MISMATCH": ROUTE_REBUILD_STAGING,
        "HASH_UNMANIFESTED_TARGET": ROUTE_REBUILD_STAGING,
        "HASH_ALGORITHM_UNSUPPORTED": ROUTE_HUMAN_REQUIRED,
        "HASH_MANIFEST_DIGEST_MISMATCH": ROUTE_HUMAN_REQUIRED,
        "HASH_REPLAY_CONFLICT": ROUTE_HUMAN_REQUIRED,
        "HASH_IDEMPOTENT_REPLAY": ROUTE_REVERIFY_READBACK,
        # smoke-verification
        "SMOKE_MANIFEST_INVALID": ROUTE_REPAIR_INPUT,
        "SMOKE_REQUIRED_TARGET_MISSING": ROUTE_REPAIR_INPUT,
        "SMOKE_HASH_MISMATCH": ROUTE_HUMAN_REQUIRED,
        "SMOKE_EXTRACTION_FAILED": ROUTE_REPAIR_INPUT,
        "SMOKE_LOAD_FAILED": ROUTE_REPAIR_INPUT,
        "SMOKE_TIMEOUT": ROUTE_BOUNDED_RETRY,
        "SMOKE_RESULT_UNKNOWN": ROUTE_BOUNDED_RETRY,
        "SMOKE_ENVIRONMENT_UNSAFE": ROUTE_HUMAN_REQUIRED,
        "SMOKE_REPLAY_CONFLICT": ROUTE_HUMAN_REQUIRED,
        "SMOKE_VERIFICATION_PASS": ROUTE_REVERIFY_READBACK,
    }

    def test_every_reason_routes(self):
        for reason, expected in self.TABLE.items():
            with self.subTest(reason=reason):
                ctx = RoutingContext(
                    reason_code=reason,
                    idempotency_key="k",
                    checkpoint_reconciled=(reason in ("SMOKE_TIMEOUT", "SMOKE_RESULT_UNKNOWN")),
                )
                d = route_failure(ctx)
                self.assertEqual(d.route, expected, reason)
                self.assertFalse(d.authority_authorized)

    def test_unknown_reason_fails_closed(self):
        d = route_failure(RoutingContext(reason_code="NO_SUCH_REASON", idempotency_key="k"))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)
        self.assertEqual(d.reason_code, REASON_FAILURE_UNMAPPED)


class TestUnsafeNeverAutoSuccess(unittest.TestCase):
    """AC-2: unsafe/contradictory/stale/unmapped never route to auto success/publish."""

    def test_unsafe_paths_human_required(self):
        for reason in ("SOURCE_PATH_TRAVERSAL", "TARGET_PATH_ESCAPES_ROOT",
                       "HASH_SOURCE_MISMATCH", "TREE_REPLAY_CONFLICT"):
            with self.subTest(reason=reason):
                d = route_failure(RoutingContext(reason_code=reason, idempotency_key="k"))
                self.assertIn(d.route, (ROUTE_HUMAN_REQUIRED, ROUTE_FAIL_CLOSED))
                self.assertNotIn(d.route, (ROUTE_REPAIR_INPUT, ROUTE_REBUILD_STAGING, ROUTE_BOUNDED_RETRY))

    def test_no_route_grants_authority(self):
        d = route_failure(RoutingContext(reason_code="HASH_TARGET_MISSING", idempotency_key="k"))
        self.assertFalse(d.authority_authorized)
        self.assertEqual(d.prohibited_actions[0], "repair")


class TestBoundedRetry(unittest.TestCase):
    """AC-3: retry bounded by count/deadline, requires reconciled readback."""

    def test_retry_requires_reconciled_readback(self):
        d = route_failure(RoutingContext(reason_code="SMOKE_TIMEOUT", idempotency_key="k",
                                         checkpoint_reconciled=False))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)
        self.assertEqual(d.reason_code, REASON_UNKNOWN_OUTCOME)

    def test_retry_ok_when_reconciled_and_budget_left(self):
        d = route_failure(RoutingContext(reason_code="SMOKE_TIMEOUT", idempotency_key="k",
                                         checkpoint_reconciled=True, retry_count=0))
        self.assertEqual(d.route, ROUTE_BOUNDED_RETRY)
        self.assertEqual(d.retry_count, 1)

    def test_retry_exhausted(self):
        d = route_failure(RoutingContext(reason_code="SMOKE_RESULT_UNKNOWN", idempotency_key="k",
                                         checkpoint_reconciled=True, retry_count=3, max_retry=3))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)
        self.assertEqual(d.reason_code, REASON_RETRY_EXHAUSTED)

    def test_retry_deadline_passed(self):
        d = route_failure(RoutingContext(reason_code="SMOKE_TIMEOUT", idempotency_key="k",
                                         checkpoint_reconciled=True, retry_count=0,
                                         retry_deadline=1000.0, now=2000.0))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)
        self.assertEqual(d.reason_code, REASON_RETRY_EXHAUSTED)


class TestReplayStability(unittest.TestCase):
    """AC-4 + rule 6: same evidence + key -> same route/digest, no duplicate effect."""

    def test_identical_evidence_same_digest(self):
        base = dict(reason_code="HASH_TARGET_MISSING", reason_namespace="deterministic-hash",
                    idempotency_key="k", retry_count=0, checkpoint_reconciled=False,
                    authority_granted_actions=[], package_identity={"source_sha": "abc"})
        d1 = route_failure(RoutingContext(**base))
        d2 = route_failure(RoutingContext(**base))
        self.assertEqual(d1.decision_digest, d2.decision_digest)
        self.assertEqual(d1.route, d2.route)

    def test_different_evidence_different_digest(self):
        d1 = route_failure(RoutingContext(reason_code="HASH_TARGET_MISSING", idempotency_key="k",
                                          package_identity={"source_sha": "abc"}))
        d2 = route_failure(RoutingContext(reason_code="HASH_TARGET_MISSING", idempotency_key="k",
                                          package_identity={"source_sha": "xyz"}))
        self.assertNotEqual(d1.decision_digest, d2.decision_digest)

    def test_interrupted_without_reconciliation_conflict(self):
        d = route_failure(RoutingContext(reason_code="HASH_TARGET_MISSING", idempotency_key="k",
                                         checkpoint_interrupted=True, checkpoint_reconciled=False,
                                         retry_count=1))
        self.assertEqual(d.route, ROUTE_HUMAN_REQUIRED)
        self.assertEqual(d.reason_code, REASON_REPLAY_CONFLICT)


class TestFamilyGoldenFlows(unittest.TestCase):
    """AC-5: clean success chain, repairable input, partial-build reconciliation,
    identical replay, conflicting replay, terminal fail-closed."""

    def test_clean_success_chain(self):
        # A passing smoke outcome routes to reverify (no publication).
        d = route_failure(RoutingContext(reason_code="SMOKE_VERIFICATION_PASS", idempotency_key="k"))
        self.assertEqual(d.route, ROUTE_REVERIFY_READBACK)

    def test_repairable_input_failure(self):
        d = route_failure(RoutingContext(reason_code="MANIFEST_ENTRY_INVALID", idempotency_key="k"))
        self.assertEqual(d.route, ROUTE_REPAIR_INPUT)

    def test_partial_build_reconciliation(self):
        d = route_failure(RoutingContext(reason_code="TREE_PARTIAL_OUTPUT", idempotency_key="k",
                                         checkpoint_reconciled=True))
        self.assertEqual(d.route, ROUTE_REBUILD_STAGING)

    def test_terminal_fail_closed(self):
        d = route_failure(RoutingContext(reason_code="NO_SUCH_REASON", idempotency_key="k"))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)

    def test_authority_violation_fail_closed(self):
        d = route_failure(RoutingContext(reason_code="HASH_TARGET_MISSING", idempotency_key="k",
                                         authority_granted_actions=["merge"]))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)
        self.assertEqual(d.reason_code, REASON_AUTHORITY_VIOLATION)


class TestSchemaValidity(unittest.TestCase):
    def test_schema_is_closed(self):
        import jsonschema
        import json as _json
        schema = _json.load(open(Path(__file__).resolve().parents[2] /
                                 "schemas/node-architect/package-export/export-failure-routing.schema.json"))
        # Build a sample decision from a routing call and validate it.
        d = route_failure(RoutingContext(reason_code="HASH_TARGET_MISSING", idempotency_key="k")).to_dict()
        jsonschema.validate(d, schema)


if __name__ == "__main__":
    unittest.main()
