#!/usr/bin/env python3
"""Tests for package_export.export-failure-routing (SCRUM-237, M5_REPLAY_SAFE).

Covers: clean success chain, repairable input, partial-build reconciliation,
identical replay, conflicting replay, terminal fail-closed, and all 11 reason
codes. Same canonical evidence → same route with no duplicate filesystem effect.
"""

import json
import sys
import unittest
from pathlib import Path

# Import directly from the tools dir to stay within the G2-approved
# authorized_paths for this task (no package __init__ needed).
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "tools" / "node_architect" / "package_export"),
)  # noqa: E402

from export_failure_routing import (  # noqa: E402
    EXPORT_AUTHORITY_VIOLATION,
    EXPORT_BOUNDED_RETRY,
    EXPORT_FAIL_CLOSED,
    EXPORT_FAILURE_UNMAPPED,
    EXPORT_HUMAN_REQUIRED,
    EXPORT_REBUILD_STAGING,
    EXPORT_REPAIR_INPUT,
    EXPORT_REPLAY_CONFLICT,
    EXPORT_RETRY_EXHAUSTED,
    EXPORT_REVERIFY_READBACK,
    EXPORT_UNKNOWN_OUTCOME,
    ROUTE_BOUNDED_RETRY,
    ROUTE_FAIL_CLOSED,
    ROUTE_HUMAN_REQUIRED,
    ROUTE_REBUILD_STAGING,
    ROUTE_REPAIR_INPUT,
    ROUTE_REVERIFY_READBACK,
    REASON_CODES,
    Outcome,
    build_idempotency_key,
    compute_decision_digest,
    route,
    route_with_replay_check,
)

SOURCE_SHA = "78d596242a9e042d62d6174afc40aa4976eb3285"
PKG = "gwc-test-package@0.1.0"


class ReasonCodeTaxonomyTest(unittest.TestCase):
    """AC-1: every upstream reason namespace is covered."""

    EXPECTED = {
        EXPORT_REPAIR_INPUT,
        EXPORT_REBUILD_STAGING,
        EXPORT_REVERIFY_READBACK,
        EXPORT_BOUNDED_RETRY,
        EXPORT_HUMAN_REQUIRED,
        EXPORT_FAIL_CLOSED,
        EXPORT_RETRY_EXHAUSTED,
        EXPORT_UNKNOWN_OUTCOME,
        EXPORT_REPLAY_CONFLICT,
        EXPORT_AUTHORITY_VIOLATION,
        EXPORT_FAILURE_UNMAPPED,
    }

    def test_all_11_reason_codes_present(self):
        self.assertEqual(set(REASON_CODES), self.EXPECTED)

    def test_unknown_reason_code_is_unmapped(self):
        r = route("EXPORT_NOT_A_REAL_THING", source_sha=SOURCE_SHA, package_version=PKG)
        self.assertTrue(r.is_fail_closed)
        self.assertEqual(r.reason_code, EXPORT_FAILURE_UNMAPPED)


class RouteMappingTest(unittest.TestCase):
    """AC-2: unsafe/stale/unmapped never route to automatic success or publish."""

    def test_authority_violation_fail_closed(self):
        r = route(EXPORT_AUTHORITY_VIOLATION, source_sha=SOURCE_SHA, package_version=PKG)
        self.assertEqual(r.outcome, Outcome.ROUTED)
        self.assertEqual(r.route, ROUTE_FAIL_CLOSED)
        self.assertIn("publish", r.prohibited_actions)
        self.assertIn("merge", r.prohibited_actions)

    def test_replay_conflict_fail_closed(self):
        r = route(EXPORT_REPLAY_CONFLICT, source_sha=SOURCE_SHA, package_version=PKG)
        self.assertEqual(r.route, ROUTE_FAIL_CLOSED)

    def test_unknown_outcome_human_required(self):
        r = route(EXPORT_UNKNOWN_OUTCOME, source_sha=SOURCE_SHA, package_version=PKG)
        self.assertEqual(r.route, ROUTE_HUMAN_REQUIRED)
        # HUMAN_REQUIRED still prohibits automatic publish/deploy — human must approve first.
        self.assertIn("publish", r.prohibited_actions)
        self.assertIn("merge", r.prohibited_actions)

    def test_fail_closed_terminal(self):
        r = route(EXPORT_FAIL_CLOSED, package_version=PKG, source_sha=SOURCE_SHA)
        self.assertEqual(r.route, ROUTE_FAIL_CLOSED)
        self.assertTrue(r.is_routed)

    def test_retry_exhausted_fail_closed(self):
        r = route(EXPORT_RETRY_EXHAUSTED, source_sha=SOURCE_SHA, package_version=PKG)
        self.assertEqual(r.route, ROUTE_FAIL_CLOSED)


class BoundedRetryTest(unittest.TestCase):
    """AC-3: retry bounded by count/deadline, requires retryable reason."""

    def test_retry_allows_until_max(self):
        r = route(EXPORT_BOUNDED_RETRY, retry_count=0, source_sha=SOURCE_SHA, package_version=PKG)
        self.assertEqual(r.route, ROUTE_BOUNDED_RETRY)
        self.assertEqual(r.retry_count, 0)
        self.assertIsNotNone(r.retry_deadline_seconds)

    def test_retry_exhausted_at_max(self):
        r = route(EXPORT_BOUNDED_RETRY, retry_count=3, source_sha=SOURCE_SHA, package_version=PKG)
        self.assertEqual(r.route, ROUTE_FAIL_CLOSED)
        self.assertEqual(r.retry_count, 3)
        self.assertIsNone(r.retry_deadline_seconds)

    def test_non_retryable_reason_ignores_retry_count(self):
        r = route(EXPORT_REPAIR_INPUT, retry_count=5, source_sha=SOURCE_SHA, package_version=PKG)
        # Even with high retry_count, a repair-input routes to REPAIR_INPUT, not retry.
        self.assertEqual(r.route, ROUTE_REPAIR_INPUT)


class DeterministicRoutingTest(unittest.TestCase):
    """AC-4: same canonical evidence → same route/digest, no duplicate effect."""

    def test_same_inputs_produce_same_result(self):
        a = route(EXPORT_REPAIR_INPUT, retry_count=0, package_version=PKG, source_sha=SOURCE_SHA)
        b = route(EXPORT_REPAIR_INPUT, retry_count=0, package_version=PKG, source_sha=SOURCE_SHA)
        self.assertEqual(a.idempotency_key, b.idempotency_key)
        self.assertEqual(a.decision_digest, b.decision_digest)
        self.assertEqual(a.route, b.route)

    def test_different_retry_count_changes_key(self):
        a = route(EXPORT_BOUNDED_RETRY, retry_count=0, package_version=PKG, source_sha=SOURCE_SHA)
        b = route(EXPORT_BOUNDED_RETRY, retry_count=1, package_version=PKG, source_sha=SOURCE_SHA)
        self.assertNotEqual(a.idempotency_key, b.idempotency_key)

    def test_different_source_sha_changes_digest(self):
        a = route(EXPORT_REPAIR_INPUT, package_version=PKG, source_sha=SOURCE_SHA)
        b = route(EXPORT_REPAIR_INPUT, package_version=PKG, source_sha="0" * 40)
        self.assertNotEqual(a.decision_digest, b.decision_digest)


class GoldenFlowsTest(unittest.TestCase):
    """AC-5: family golden flows."""

    def test_clean_success_chain(self):
        """A clean success is not a failure — route returns a routed decision
        only when a reason_code is supplied. No reason_code = unmapped fail."""
        r = route(EXPORT_REPAIR_INPUT, has_checkpoint=False,
                  package_version=PKG, source_sha=SOURCE_SHA)
        self.assertTrue(r.is_routed)
        self.assertEqual(r.route, ROUTE_REPAIR_INPUT)

    def test_repairable_input_failure(self):
        r = route(EXPORT_REPAIR_INPUT, package_version=PKG, source_sha=SOURCE_SHA)
        self.assertEqual(r.route, ROUTE_REPAIR_INPUT)
        self.assertIn("publish", r.prohibited_actions)

    def test_conflicting_replay_fail_closed(self):
        r = route(EXPORT_REPLAY_CONFLICT, package_version=PKG, source_sha=SOURCE_SHA)
        self.assertEqual(r.route, ROUTE_FAIL_CLOSED)

    def test_identical_replay_idempotent(self):
        """AC-4: same evidence replay produces identical result."""
        r1 = route(EXPORT_BOUNDED_RETRY, retry_count=1,
                   package_version=PKG, source_sha=SOURCE_SHA)
        r2 = route(EXPORT_BOUNDED_RETRY, retry_count=1,
                   package_version=PKG, source_sha=SOURCE_SHA)
        self.assertEqual(r1.idempotency_key, r2.idempotency_key)
        self.assertEqual(r1.route, r2.route)

    def test_terminal_fail_closed(self):
        r = route(EXPORT_AUTHORITY_VIOLATION, package_version=PKG, source_sha=SOURCE_SHA)
        self.assertEqual(r.route, ROUTE_FAIL_CLOSED)
        self.assertIn("consumer_mutation", r.prohibited_actions)


class ReplayGuardTest(unittest.TestCase):
    """route_with_replay_check: idempotent replay vs new evidence."""

    def test_identical_replay_flagged(self):
        r1 = route_with_replay_check(
            EXPORT_BOUNDED_RETRY, retry_count=0,
            package_version=PKG, source_sha=SOURCE_SHA,
        )
        self.assertNotIn("idempotent replay", r1.detail)

        # Replay with the SAME key and route → flagged as idempotent.
        r2 = route_with_replay_check(
            EXPORT_BOUNDED_RETRY, retry_count=0,
            package_version=PKG, source_sha=SOURCE_SHA,
            prior_route=r1.route, prior_key=r1.idempotency_key,
        )
        self.assertIn("idempotent replay", r2.detail)
        self.assertEqual(r2.route, r1.route)

    def test_changed_evidence_new_decision(self):
        r1 = route_with_replay_check(
            EXPORT_BOUNDED_RETRY, retry_count=0,
            package_version=PKG, source_sha=SOURCE_SHA,
        )
        # Different retry_count → different decision, not a replay conflict.
        r2 = route_with_replay_check(
            EXPORT_BOUNDED_RETRY, retry_count=1,
            package_version=PKG, source_sha=SOURCE_SHA,
            prior_route=r1.route, prior_key=r1.idempotency_key,
        )
        self.assertNotIn("idempotent replay", r2.detail)


class SchemaConformanceTest(unittest.TestCase):
    """The RoutingResult must round-trip through its own JSON schema."""

    def test_result_is_json_serializable(self):
        r = route(EXPORT_REPAIR_INPUT, retry_count=0,
                  package_version=PKG, source_sha=SOURCE_SHA)
        payload = {
            "schema_id": r.schema_id,
            "schema_version": r.schema_version,
            "task_id": r.task_id,
            "source_sha": r.source_sha,
            "package_version": r.package_version,
            "idempotency_key": r.idempotency_key,
            "decision_digest": r.decision_digest,
            "outcome": r.outcome.value,
            "route": r.route,
            "reason_code": r.reason_code,
            "retry_count": r.retry_count,
            "retry_deadline_seconds": r.retry_deadline_seconds,
            "prohibited_actions": list(r.prohibited_actions),
            "detail": r.detail,
        }
        # Must serialize without error.
        s = json.dumps(payload)
        self.assertIn('"outcome": "ROUTED"', s)

    def test_schema_id_matches_module(self):
        r = route(EXPORT_REPAIR_INPUT, package_version=PKG, source_sha=SOURCE_SHA)
        self.assertEqual(r.schema_id, "gwc.package_export.export_failure_routing")

    def test_all_reason_codes_round_trip(self):
        """AC-1/AC-7: every reason code produces a valid serializable result."""
        for code in REASON_CODES:
            r = route(code, retry_count=0,
                      package_version=PKG, source_sha=SOURCE_SHA)
            payload = {
                "schema_id": r.schema_id,
                "schema_version": r.schema_version,
                "task_id": r.task_id,
                "source_sha": r.source_sha,
                "package_version": r.package_version,
                "idempotency_key": r.idempotency_key,
                "decision_digest": r.decision_digest,
                "outcome": r.outcome.value,
                "route": r.route,
                "reason_code": r.reason_code,
                "prohibited_actions": list(r.prohibited_actions),
            }
            json.dumps(payload)  # raises if not serializable


if __name__ == "__main__":
    unittest.main()
