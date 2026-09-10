#!/usr/bin/env python3
"""R4 certification tests: hierarchical RuntimePlan revisions, cursor, recovery,
retry/rerun/replan/restart and drift detection.

C4 (G1 RuntimePlan, TargetContract and topology are immutable/digest-bound) and
C9 (retry/rerun/replan/restart, cursor recovery, drift and unknown-effect safety)
per the C1-C15 matrix. Composes E1 kernel digest primitives and E3 topology
manifest-revision; reuses run-manifest-revision.schema.json shape.

Pure / read-only: never persists, never grants authority, never mutates targets.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE
from tools.node_architect.universal_run_plan import (
    CursorRecoveryError,
    DriftError,
    PlanRevision,
    RuntimePlan,
    advance_cursor,
    create_runtime_plan,
    create_plan_revision,
    detect_drift,
    recover_cursor,
    restart_run,
    validate_plan_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "node-architect" / "universal-run" / "run-manifest-revision.schema.json"
PROFILE = UNIVERSAL_PROFILE


def _schema_validator():
    try:
        from jsonschema import Draft7Validator
    except Exception as exc:  # pragma: no cover
        raise unittest.SkipTest(f"jsonschema unavailable: {exc}") from exc
    schema = json.loads(SCHEMA_PATH.read_text())
    return Draft7Validator(schema)


class TestC4RuntimePlanImmutability(unittest.TestCase):
    """C4: RuntimePlan + revisions are immutable/digest-bound."""

    def test_create_plan_with_revision_1(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1",
            node_allocations=["n1", "n2"],
        )
        self.assertIsInstance(plan, RuntimePlan)
        self.assertEqual(plan.revision, 1)
        self.assertIsNotNone(plan.digest)

    def test_plan_digest_deterministic(self):
        a = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        b = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        self.assertEqual(a.digest, b.digest)

    def test_revision_must_increase(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        with self.assertRaises(Exception):
            create_plan_revision(
                previous=plan, run_id="run-1", revision=1,
                target_contract_ref="target:contract:v1", node_allocations=["n1"],
            )

    def test_revision_successor_linked(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        rev2 = create_plan_revision(
            previous=plan, run_id="run-1", revision=2,
            target_contract_ref="target:contract:v2", node_allocations=["n1", "n2"],
        )
        self.assertEqual(rev2.revision, 2)
        self.assertEqual(rev2.previous_digest, plan.digest)

    def test_validate_plan_digest_ok(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        self.assertTrue(validate_plan_digest(plan))

    def test_validate_plan_digest_tamper_fails(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        plan_dict = plan.to_dict()
        plan_dict["target_contract_ref"] = "tampered"
        self.assertFalse(validate_plan_digest(PlanRevision.from_dict(plan_dict)))


class TestC4SchemaConformance(unittest.TestCase):
    """Revision record validates against run-manifest-revision schema."""

    def test_plan_revision_matches_schema(self):
        validator = _schema_validator()
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        rev2 = create_plan_revision(
            previous=plan, run_id="run-1", revision=2,
            target_contract_ref="target:contract:v2", node_allocations=["n1", "n2"],
        )
        # PlanRevision.to_manifest_record emits the manifest-revision shape.
        errors = list(validator.iter_errors(rev2.to_manifest_record()))
        self.assertEqual(errors, [])


class TestC9CursorRecovery(unittest.TestCase):
    """C9: cursor advance and recovery are monotonic, typed, fail-closed."""

    def test_advance_cursor_monotonic(self):
        result = advance_cursor(
            run_id="run-1", current_cursor=1, next_cursor=2,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["cursor"], 2)

    def test_advance_cursor_non_monotonic_rejected(self):
        with self.assertRaises(CursorRecoveryError):
            advance_cursor(
                run_id="run-1", current_cursor=2, next_cursor=1,
            )

    def test_recover_cursor_from_state(self):
        recovered = recover_cursor(
            run_id="run-1", saved_cursor=3,
            observed_cursor=None,
        )
        self.assertEqual(recovered["cursor"], 3)

    def test_recover_cursor_rejects_higher_than_saved(self):
        with self.assertRaises(CursorRecoveryError):
            recover_cursor(
                run_id="run-1", saved_cursor=2, observed_cursor=5,
            )

    def test_recover_cursor_unknown_effect_fails_closed(self):
        # No saved cursor + no observed cursor = unknown state -> fail-closed.
        with self.assertRaises(CursorRecoveryError):
            recover_cursor(
                run_id="run-1", saved_cursor=None, observed_cursor=None,
            )


class TestC9RetryRerunReplanRestart(unittest.TestCase):
    """C9: retry/rerun/replan/restart are typed control receipts, no rewrite."""

    def test_retry_uses_same_plan_digest(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        result = restart_run(
            run_id="run-1", mode="RETRY", plan_digest=plan.digest,
            restart_from_cursor=0,
        )
        self.assertEqual(result["mode"], "RETRY")
        self.assertEqual(result["plan_digest"], plan.digest)
        self.assertEqual(result["restart_from_cursor"], 0)
        self.assertEqual(result["effect"], "NO_REWRITE")

    def test_rerun_uses_same_plan_digest(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        result = restart_run(
            run_id="run-1", mode="RERUN", plan_digest=plan.digest,
            restart_from_cursor=1,
        )
        self.assertEqual(result["effect"], "NO_REWRITE")

    def test_replan_requires_new_revision(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        rev2 = create_plan_revision(
            previous=plan, run_id="run-1", revision=2,
            target_contract_ref="target:contract:v2", node_allocations=["n1"],
        )
        result = restart_run(
            run_id="run-1", mode="REPLAN", plan_digest=rev2.digest,
            restart_from_cursor=0,
        )
        self.assertEqual(result["mode"], "REPLAN")
        self.assertEqual(result["plan_digest"], rev2.digest)

    def test_restart_rejects_unknown_mode(self):
        with self.assertRaises(Exception):
            restart_run(
                run_id="run-1", mode="HACK", plan_digest="x",
                restart_from_cursor=0,
            )

    def test_restart_never_rewrites(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        for mode in ("RETRY", "RERUN", "REPLAN"):
            result = restart_run(
                run_id="run-1", mode=mode, plan_digest=plan.digest,
                restart_from_cursor=0,
            )
            self.assertEqual(result["effect"], "NO_REWRITE")


class TestC9DriftDetection(unittest.TestCase):
    """C9: drift and unknown-effect safety."""

    def test_no_drift(self):
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        result = detect_drift(
            run_id="run-1",
            expected_plan_digest=plan.digest,
            observed_plan_digest=plan.digest,
        )
        self.assertTrue(result["no_drift"])
        self.assertEqual(result["drift_decision"], "NO_DRIFT")

    def test_drift_detected(self):
        plan_a = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1"],
        )
        plan_b = create_runtime_plan(
            run_id="run-1", revision=2,
            target_contract_ref="target:contract:v2", node_allocations=["n2"],
        )
        result = detect_drift(
            run_id="run-1",
            expected_plan_digest=plan_a.digest,
            observed_plan_digest=plan_b.digest,
        )
        self.assertFalse(result["no_drift"])
        self.assertEqual(result["drift_decision"], "DRIFT")
        # Unknown-effect safety: drift raises a typed error when enforced.
        with self.assertRaises(DriftError):
            detect_drift(
                run_id="run-1",
                expected_plan_digest=plan_a.digest,
                observed_plan_digest=plan_b.digest,
                enforce=True,
            )

    def test_drift_digest_immutability_contract(self):
        # A plan's digest must not change across serialization round-trip.
        plan = create_runtime_plan(
            run_id="run-1", revision=1,
            target_contract_ref="target:contract:v1", node_allocations=["n1", "n2"],
        )
        restored = PlanRevision.from_dict(plan.to_dict())
        self.assertEqual(restored.digest, plan.digest)


if __name__ == "__main__":
    unittest.main()
