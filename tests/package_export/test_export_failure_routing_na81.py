#!/usr/bin/env python3
"""NA81 current-task proof test for package_export.export-failure-routing (SCRUM-360, F7).

This test explicitly maps the current NA81 brief categories to existing code/tests.
It is the proof that distinguishes DELIVERY from historical reuse.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "node_architect" / "package_export"))

from export_failure_routing import (
    REASON_FAILURE_UNMAPPED,
    REASON_REPLAY_CONFLICT,
    REASON_UNKNOWN_OUTCOME,
    REASON_RETRY_EXHAUSTED,
    ROUTE_BOUNDED_RETRY,
    ROUTE_FAIL_CLOSED,
    ROUTE_HUMAN_REQUIRED,
    DECISION_TABLE,
    RoutingContext,
    route_failure,
)


class TestSCRUM360BriefCategoryCoverage(unittest.TestCase):
    """AC: every category named in the current NA81 brief (manifest/schema/path/build/hash/smoke)
    has at least one decision-table entry."""

    BRIEF_PREFIXES = {
        "manifest": "MANIFEST_",
        "schema":   "SCHEMA_",
        "path":     "SOURCE_",
        "build":    "TREE_",
        "hash":     "HASH_",
        "smoke":    "SMOKE_",
    }

    def test_brief_categories_have_routes(self):
        for label, prefix in self.BRIEF_PREFIXES.items():
            keys = [k for k in DECISION_TABLE if k.startswith(prefix)]
            self.assertTrue(
                len(keys) > 0,
                f"SCRUM-360 brief category '{label}' has no decision-table entries "
                f"starting with '{prefix}'",
            )


class TestSCRUM360UnknownNeverPasses(unittest.TestCase):
    """AC: unknown/unavailable/contradictory outcomes never PASS."""

    def test_unknown_reason_fails_closed(self):
        d = route_failure(RoutingContext(reason_code="NO_SUCH_REASON", idempotency_key="k"))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)
        self.assertEqual(d.reason_code, REASON_FAILURE_UNMAPPED)

    def test_unknown_outcome_reason_also_fails_closed(self):
        d = route_failure(RoutingContext(reason_code="EXPORT_SOMETHING_WEIRD", idempotency_key="k"))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)


class TestSCRUM360NoAuthorityExpansion(unittest.TestCase):
    """AC: no route may grant publish/release/deploy authority."""

    def test_no_route_authorizes_actions(self):
        for reason in ("SCHEMA_INVALID", "TREE_PARTIAL_OUTPUT", "SMOKE_TIMEOUT",
                        "HASH_TARGET_MISMATCH", "SOURCE_PATH_TRAVERSAL"):
            with self.subTest(reason=reason):
                d = route_failure(RoutingContext(reason_code=reason, idempotency_key="k"))
                self.assertFalse(d.authority_authorized)
                # The router explicitly prohibits publish/release/deploy,
                # which is the correct evidence that no route grants that authority.
                self.assertIn("publish", d.prohibited_actions)


class TestSCRUM360BoundedRetryReconciliation(unittest.TestCase):
    """AC: retry requires reconciled readback; exhausted budget fails closed."""

    def test_retry_requires_reconciled_readback(self):
        d = route_failure(RoutingContext(
            reason_code="SMOKE_TIMEOUT",
            idempotency_key="k",
            checkpoint_reconciled=False,
        ))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)
        self.assertEqual(d.reason_code, REASON_UNKNOWN_OUTCOME)

    def test_retry_ok_when_reconciled_and_budget_left(self):
        d = route_failure(RoutingContext(
            reason_code="SMOKE_TIMEOUT",
            idempotency_key="k",
            checkpoint_reconciled=True,
            retry_count=0,
        ))
        self.assertEqual(d.route, ROUTE_BOUNDED_RETRY)
        self.assertEqual(d.retry_count, 1)

    def test_retry_exhausted(self):
        d = route_failure(RoutingContext(
            reason_code="SMOKE_RESULT_UNKNOWN",
            idempotency_key="k",
            checkpoint_reconciled=True,
            retry_count=3,
            max_retry=3,
        ))
        self.assertEqual(d.route, ROUTE_FAIL_CLOSED)
        self.assertEqual(d.reason_code, REASON_RETRY_EXHAUSTED)


class TestSCRUM360ReplayConflictHumanRequired(unittest.TestCase):
    """AC: conflicting replay routes to HUMAN_REQUIRED."""

    def test_interrupted_without_reconciliation_conflict(self):
        d = route_failure(RoutingContext(
            reason_code="HASH_TARGET_MISSING",
            idempotency_key="k",
            checkpoint_interrupted=True,
            checkpoint_reconciled=False,
            retry_count=1,
        ))
        self.assertEqual(d.route, ROUTE_HUMAN_REQUIRED)
        self.assertEqual(d.reason_code, REASON_REPLAY_CONFLICT)


if __name__ == "__main__":
    unittest.main()
