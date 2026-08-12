from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# SCRUM-323 fix: absolute tools/ path so `python -m unittest discover -s tests`
# works without PYTHONPATH (CI runs plain unittest from repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from jsonschema import Draft202012Validator

from node_architect.runtime_checkpoint.state_reconciliation import (
    SOURCE_PRECEDENCE,
    SourceState,
    classify_source_state,
    reconcile_sources,
)


# ---------------------------------------------------------------------------
# SCRUM-332 NA81 acceptance tests for runtime_checkpoint.state-reconciliation
# Three-source reconciliation: persisted checkpoint + external readback +
# canonical task/runtime state, with deterministic source precedence.
# ---------------------------------------------------------------------------

BRANCH = "auto/SCRUM-332-na81-20260810"


def evidence(canonical=None, readback=None, checkpoint=None, ci=None, **extra):
    payload = {
        "task_id": "SCRUM-332",
        "branch": BRANCH,
        "canonical_state": canonical,
        "external_readback": readback,
        "persisted_checkpoint": checkpoint,
    }
    if ci is not None:
        payload["ci"] = ci
    payload.update(extra)
    return payload


def src(status):
    return {"status": status}


class StateReconciliationNA81Tests(unittest.TestCase):
    """SCRUM-332 NA81 acceptance tests."""

    # --- classification ------------------------------------------------
    def test_classify_source_state_maps_aliases(self):
        self.assertEqual(classify_source_state(src("COMPLETED")), SourceState.CONFIRMED)
        self.assertEqual(classify_source_state(src("IN_PROGRESS")), SourceState.PENDING)
        self.assertEqual(classify_source_state(src("ERROR")), SourceState.FAILED)
        self.assertEqual(classify_source_state(src("UNKNOWN")), SourceState.UNKNOWN)
        self.assertEqual(classify_source_state(None), SourceState.ABSENT)
        self.assertEqual(classify_source_state({}), SourceState.UNKNOWN)
        self.assertEqual(classify_source_state("done"), SourceState.CONFIRMED)

    def test_source_precedence_order(self):
        self.assertEqual(
            SOURCE_PRECEDENCE,
            ("canonical_state", "external_readback", "persisted_checkpoint"),
        )

    # --- confirmed ------------------------------------------------------
    def test_confirmed_all_agree_resumes(self):
        r = reconcile_sources(
            evidence(
                canonical=src("CONFIRMED"),
                readback=src("CONFIRMED"),
                checkpoint=src("CONFIRMED"),
            )
        )
        self.assertEqual(r.state, "CONFIRMED")
        self.assertEqual(r.route, "RESUME")
        self.assertEqual(r.outcome, "PASS")
        self.assertTrue(r.retry_allowed)
        self.assertFalse(r.readback_required)
        self.assertFalse(r.conflict)
        self.assertEqual(r.authoritative_source, "canonical_state")

    # --- pending --------------------------------------------------------
    def test_pending_with_readback_resumes(self):
        r = reconcile_sources(
            evidence(
                canonical=src("PENDING"),
                readback=src("PENDING"),
                checkpoint=src("PENDING"),
            )
        )
        self.assertEqual(r.state, "PENDING")
        self.assertEqual(r.route, "RESUME")
        self.assertEqual(r.outcome, "PASS")
        self.assertTrue(r.retry_allowed)

    def test_pending_with_stale_checkpoint_repairs(self):
        # checkpoint claims CONFIRMED while authoritative + readback say PENDING
        r = reconcile_sources(
            evidence(
                canonical=src("PENDING"),
                readback=src("PENDING"),
                checkpoint=src("CONFIRMED"),
            )
        )
        self.assertTrue(r.conflict)
        self.assertEqual(r.state, "PENDING")
        self.assertEqual(r.route, "REPAIR")
        self.assertEqual(r.outcome, "PASS")
        self.assertTrue(r.retry_allowed)

    # --- failed ---------------------------------------------------------
    def test_failed_authoritative_stops(self):
        r = reconcile_sources(
            evidence(
                canonical=src("FAILED"),
                readback=src("FAILED"),
                checkpoint=src("FAILED"),
            )
        )
        self.assertEqual(r.state, "FAILED")
        self.assertEqual(r.route, "STOP_BLOCKED")
        self.assertEqual(r.outcome, "FAIL")
        self.assertFalse(r.retry_allowed)

    # --- unknown / interrupted -----------------------------------------
    def test_unknown_never_completes(self):
        r = reconcile_sources(
            evidence(
                canonical=src("UNKNOWN"),
                readback=src("UNKNOWN"),
                checkpoint=src("UNKNOWN"),
            )
        )
        self.assertEqual(r.state, "UNKNOWN")
        self.assertEqual(r.outcome, "FAIL")
        self.assertTrue(r.readback_required)
        self.assertFalse(r.retry_allowed)
        self.assertFalse(r.authority_granted)

    def test_all_absent_is_unknown(self):
        r = reconcile_sources(evidence())
        self.assertEqual(r.state, "UNKNOWN")
        self.assertEqual(r.outcome, "FAIL")
        self.assertTrue(r.readback_required)

    # --- conflicting sources / stale checkpoint -------------------------
    def test_stale_checkpoint_repaired_when_readback_confirms(self):
        r = reconcile_sources(
            evidence(
                canonical=src("CONFIRMED"),
                readback=src("CONFIRMED"),
                checkpoint=src("FAILED"),  # stale / fenced checkpoint
            )
        )
        self.assertTrue(r.conflict)
        self.assertEqual(r.state, "CONFIRMED")
        self.assertEqual(r.route, "REPAIR")
        self.assertEqual(r.outcome, "PASS")
        self.assertTrue(r.retry_allowed)
        self.assertEqual(r.reason, "RECONCILED_REPAIR_STALE_CHECKPOINT")

    def test_conflicting_readback_blocks(self):
        r = reconcile_sources(
            evidence(
                canonical=src("CONFIRMED"),
                readback=src("FAILED"),
                checkpoint=src("CONFIRMED"),
            )
        )
        self.assertTrue(r.conflict)
        self.assertEqual(r.route, "STOP_BLOCKED")
        self.assertEqual(r.outcome, "FAIL")
        self.assertEqual(r.reason, "CONFLICTING_SOURCES")

    # --- readback-before-retry -----------------------------------------
    def test_readback_required_before_retry(self):
        r = reconcile_sources(
            evidence(
                canonical=src("CONFIRMED"),
                readback=None,
                checkpoint=src("CONFIRMED"),
            )
        )
        self.assertEqual(r.state, "CONFIRMED")
        self.assertEqual(r.route, "STOP_BLOCKED")
        self.assertEqual(r.outcome, "FAIL")
        self.assertTrue(r.readback_required)
        self.assertFalse(r.retry_allowed)
        self.assertEqual(r.reason, "READBACK_REQUIRED_BEFORE_RETRY")

    def test_pending_without_readback_blocked(self):
        r = reconcile_sources(
            evidence(
                canonical=src("PENDING"),
                readback=None,
                checkpoint=src("PENDING"),
            )
        )
        self.assertEqual(r.route, "STOP_BLOCKED")
        self.assertEqual(r.outcome, "FAIL")
        self.assertTrue(r.readback_required)

    # --- deterministic source precedence -------------------------------
    def test_precedence_skips_unknown_canonical_to_readback(self):
        r = reconcile_sources(
            evidence(
                canonical=src("UNKNOWN"),
                readback=src("CONFIRMED"),
                checkpoint=src("CONFIRMED"),
            )
        )
        self.assertEqual(r.authoritative_source, "external_readback")
        self.assertEqual(r.state, "CONFIRMED")
        self.assertEqual(r.route, "RESUME")
        self.assertEqual(r.outcome, "PASS")

    def test_precedence_checkpoint_only_blocked_without_readback(self):
        r = reconcile_sources(
            evidence(
                canonical=None,
                readback=None,
                checkpoint=src("CONFIRMED"),
            )
        )
        self.assertEqual(r.authoritative_source, "persisted_checkpoint")
        self.assertEqual(r.state, "CONFIRMED")
        self.assertEqual(r.route, "STOP_BLOCKED")  # readback required before retry
        self.assertEqual(r.outcome, "FAIL")
        self.assertTrue(r.readback_required)

    # --- deterministic replay ------------------------------------------
    def test_deterministic_same_evidence_same_digest(self):
        e = evidence(
            canonical=src("CONFIRMED"),
            readback=src("CONFIRMED"),
            checkpoint=src("CONFIRMED"),
        )
        r1 = reconcile_sources(e)
        r2 = reconcile_sources(e)
        self.assertEqual(r1.result_digest, r2.result_digest)
        self.assertEqual(r1.route, r2.route)
        self.assertEqual(r1.outcome, r2.outcome)

    # --- negative / invalid input --------------------------------------
    def test_invalid_input_does_not_crash(self):
        r = reconcile_sources({"task_id": "SCRUM-332"})  # no sources
        self.assertEqual(r.state, "UNKNOWN")
        self.assertEqual(r.outcome, "FAIL")
        self.assertFalse(r.authority_granted)

    def test_non_mapping_input_safe(self):
        r = reconcile_sources(None)
        self.assertEqual(r.state, "UNKNOWN")
        self.assertEqual(r.outcome, "FAIL")

    # --- schema contract ------------------------------------------------
    def test_result_schema_accepts_all_routes(self):
        schema_path = (
            Path(__file__).resolve().parent.parent
            / "schemas"
            / "state-reconciliation-sources-result.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        cases = (
            evidence(canonical=src("CONFIRMED"), readback=src("CONFIRMED"), checkpoint=src("CONFIRMED")),
            evidence(canonical=src("PENDING"), readback=src("PENDING"), checkpoint=src("PENDING")),
            evidence(canonical=src("FAILED"), readback=src("FAILED"), checkpoint=src("FAILED")),
            evidence(canonical=src("UNKNOWN"), readback=src("UNKNOWN"), checkpoint=src("UNKNOWN")),
            evidence(canonical=src("CONFIRMED"), readback=src("CONFIRMED"), checkpoint=src("FAILED")),
            evidence(canonical=src("CONFIRMED"), readback=None, checkpoint=src("CONFIRMED")),
        )
        for idx, case in enumerate(cases):
            result = reconcile_sources(case)
            errors = sorted(validator.iter_errors(result.to_dict()), key=lambda e: e.message)
            self.assertEqual(
                errors, [], f"case {idx} schema errors: {[e.message for e in errors]}"
            )


if __name__ == "__main__":
    unittest.main()
