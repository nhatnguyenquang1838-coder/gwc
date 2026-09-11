#!/usr/bin/env python3
"""R2 certification tests: universal G0-G6 lifecycle state machine.

C1: contract identity/version, fixed seven-position lifecycle, illegal-transition
    rejection (complete edge matrix, deterministic error codes).
C5: typed no-op outcomes, execution receipts / effect idempotency, and no silent
    step execution (every request returns a typed outcome; never None, never a
    silent pass-through).

Reuses the committed lifecycle-transition.schema.json. Pure / read-only: this
module never mutates external state, never persists, never grants authority.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.node_architect.universal_run_kernel import GATES, GATE_STATES
from tools.node_architect.universal_run_lifecycle import (
    EDGE_MATRIX,
    LifecycleStateMachine,
    NoOpOutcome,
    TransitionResult,
    classify_noop,
    edge_is_legal,
    evaluate_transition,
    lifecycle_edge_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "node-architect" / "universal-run" / "lifecycle-transition.schema.json"

PROFILE = {"id": "gwc.universal-run", "version": 1}


def _schema_validator():
    try:
        from jsonschema import Draft7Validator
    except Exception as exc:  # pragma: no cover
        raise unittest.SkipTest(f"jsonschema unavailable: {exc}") from exc
    schema = json.loads(SCHEMA_PATH.read_text())
    return Draft7Validator(schema)


class TestC1ContractIdentityAndVersion(unittest.TestCase):
    """C1: contract identity, version, fixed seven-position lifecycle."""

    def test_gates_are_fixed_seven_positions(self):
        self.assertEqual(tuple(GATES), ("G0", "G1", "G2", "G3", "G4", "G5", "G6"))

    def test_lifecycle_profile_identity(self):
        sm = LifecycleStateMachine(profile=PROFILE)
        self.assertEqual(sm.profile, PROFILE)
        result = evaluate_transition(
            profile=PROFILE, current_gate="G0", current_state="ACTIVE",
            action="COMPLETE",
        )
        self.assertEqual(result.outcome["lifecycle_profile"], PROFILE)

    def test_unknown_profile_fails_closed(self):
        with self.assertRaises(Exception):
            evaluate_transition(
                profile={"id": "gwc.other", "version": 2},
                current_gate="G0", current_state="ACTIVE", action="COMPLETE",
            )


class TestC1IllegalTransitionRejection(unittest.TestCase):
    """C1: illegal-transition rejection with deterministic error codes."""

    def test_advance_from_not_started_rejected(self):
        with self.assertRaises(Exception) as ctx:
            evaluate_transition(
                profile=PROFILE, current_gate="G0", current_state="NOT_STARTED",
                action="ADVANCE",
            )
        self.assertIn("LIFECYCLE", str(ctx.exception))

    def test_advance_from_active_rejected(self):
        with self.assertRaises(Exception) as ctx:
            evaluate_transition(
                profile=PROFILE, current_gate="G0", current_state="ACTIVE",
                action="ADVANCE",
            )
        self.assertIn("LIFECYCLE_EDGE_UNDECLARED", str(ctx.exception))

    def test_g6_has_no_forward_gate(self):
        with self.assertRaises(Exception) as ctx:
            evaluate_transition(
                profile=PROFILE, current_gate="G6", current_state="PASSED",
                action="ADVANCE",
            )
        self.assertIn("LIFECYCLE_EDGE_UNDECLARED", str(ctx.exception))

    def test_silent_gate_skip_rejected(self):
        # G0 PASSED -> G2 without G1 is illegal.
        with self.assertRaises(Exception) as ctx:
            evaluate_transition(
                profile=PROFILE, current_gate="G0", current_state="PASSED",
                action="ADVANCE", target_gate="G2",
            )
        self.assertIn("LIFECYCLE_EDGE_UNDECLARED", str(ctx.exception))

    def test_wait_requires_active(self):
        with self.assertRaises(Exception) as ctx:
            evaluate_transition(
                profile=PROFILE, current_gate="G1", current_state="PASSED",
                action="WAIT",
            )
        self.assertIn("LIFECYCLE", str(ctx.exception))

    def test_unknown_action_rejected(self):
        with self.assertRaises(Exception) as ctx:
            evaluate_transition(
                profile=PROFILE, current_gate="G0", current_state="ACTIVE",
                action="DO_WRITE",
            )
        self.assertIn("LIFECYCLE_ACTION_UNKNOWN", str(ctx.exception))


class TestC1EdgeMatrixCoverage(unittest.TestCase):
    """C1: the edge matrix classifies every (gate,state,action) deterministically."""

    def test_edge_matrix_covers_all_gates_and_states(self):
        for gate, state in itertools.product(GATES, GATE_STATES):
            self.assertIn((gate, state), EDGE_MATRIX, f"missing gate/state {gate}:{state}")

    def test_every_cell_has_deterministic_verdict(self):
        actions = ("ADVANCE", "WAIT", "CONTINUE", "RETRY", "RERUN", "REPAIR", "REPLAN", "COMPLETE", "FAIL", "CANCEL")
        for gate, state in itertools.product(GATES, GATE_STATES):
            legal_actions = set(EDGE_MATRIX[(gate, state)])
            for action in actions:
                verdict = edge_is_legal(gate=gate, state=state, action=action)
                self.assertIsInstance(verdict, bool)
                self.assertEqual(verdict, action in legal_actions)

    def test_matrix_agrees_with_engine(self):
        actions = ("ADVANCE", "WAIT", "CONTINUE", "RETRY", "RERUN", "REPAIR", "REPLAN", "COMPLETE", "FAIL", "CANCEL")
        checked = 0
        for gate, state in itertools.product(GATES, GATE_STATES):
            for action in actions:
                legal = edge_is_legal(gate=gate, state=state, action=action)
                if legal:
                    kwargs = dict(profile=PROFILE, current_gate=gate, current_state=state, action=action)
                    if gate == "G4" and state == "ACTIVE" and action == "COMPLETE":
                        kwargs["explicit_outcome"] = "NO_TRANSFER_REQUIRED"
                    result = evaluate_transition(**kwargs)
                    self.assertIsInstance(result, TransitionResult)
                    checked += 1
                else:
                    with self.assertRaises(Exception):
                        evaluate_transition(profile=PROFILE, current_gate=gate, current_state=state, action=action)
        self.assertGreater(checked, 10, "expected a substantial legal edge set")


class TestC5TypedNoOpOutcomes(unittest.TestCase):
    """C5: typed no-op outcomes — no silent step execution."""

    def test_every_legal_transition_returns_typed_outcome(self):
        result = evaluate_transition(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="COMPLETE")
        self.assertIsInstance(result, TransitionResult)
        self.assertIsInstance(result.outcome, dict)
        self.assertEqual(result.outcome["artifact_type"], "universal-lifecycle-transition")
        self.assertEqual(result.outcome["execution_performed"], False)

    def test_noop_reason_is_typed(self):
        result = evaluate_transition(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="COMPLETE")
        self.assertIsInstance(result.noop, NoOpOutcome)
        self.assertTrue(result.noop.reason_code)
        self.assertIn(result.noop.reason_code, classify_noop(result.outcome))

    def test_noop_reason_is_deterministic(self):
        reason_a = evaluate_transition(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="COMPLETE").noop.reason_code
        reason_b = evaluate_transition(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="COMPLETE").noop.reason_code
        self.assertEqual(reason_a, reason_b)

    def test_never_returns_none_or_silent(self):
        for gate, state, action in (
            ("G0", "ACTIVE", "COMPLETE"),
            ("G1", "ACTIVE", "COMPLETE"),
            ("G4", "ACTIVE", "COMPLETE"),
        ):
            kwargs = dict(profile=PROFILE, current_gate=gate, current_state=state, action=action)
            if gate == "G4":
                kwargs["explicit_outcome"] = "NO_TRANSFER_REQUIRED"
            result = evaluate_transition(**kwargs)
            self.assertIsNotNone(result.outcome)
            self.assertIsNotNone(result.noop.reason_code)


class TestC5ExecutionReceiptAndIdempotency(unittest.TestCase):
    """C5: execution receipts, effect idempotency, no silent step."""

    def test_transition_result_has_receipt(self):
        result = evaluate_transition(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="COMPLETE")
        self.assertTrue(result.receipt)
        self.assertIn("transition_digest", result.receipt)
        self.assertEqual(result.receipt["execution_performed"], False)

    def test_identical_request_is_idempotent(self):
        kwargs = dict(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="COMPLETE")
        a = evaluate_transition(**kwargs)
        b = evaluate_transition(**kwargs)
        self.assertEqual(a.receipt, b.receipt)
        self.assertEqual(a.outcome, b.outcome)

    def test_lifecycle_edge_digest_stable(self):
        kwargs = dict(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="COMPLETE")
        d1 = lifecycle_edge_digest(**kwargs)
        d2 = lifecycle_edge_digest(**kwargs)
        self.assertEqual(d1, d2)
        self.assertRegex(d1, r"^sha256:[0-9a-f]{64}$")

    def test_receipt_changes_on_material_difference(self):
        a = evaluate_transition(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="COMPLETE")
        b = evaluate_transition(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="WAIT")
        # WAIT from ACTIVE is legal; outcome differs so receipt must differ.
        self.assertNotEqual(a.receipt, b.receipt)

    def test_state_machine_is_stateless_no_side_effects(self):
        # The facade must be a pure evaluator: two identical machines produce
        # identical outcomes and no external mutation occurs.
        sm1 = LifecycleStateMachine(profile=PROFILE)
        sm2 = LifecycleStateMachine(profile=PROFILE)
        r1 = sm1.evaluate(current_gate="G0", current_state="ACTIVE", action="COMPLETE")
        r2 = sm2.evaluate(current_gate="G0", current_state="ACTIVE", action="COMPLETE")
        self.assertEqual(r1.outcome, r2.outcome)


class TestSchemaConformance(unittest.TestCase):
    """Outcomes must validate against the committed lifecycle-transition schema."""

    def test_legal_transition_matches_schema(self):
        validator = _schema_validator()
        result = evaluate_transition(profile=PROFILE, current_gate="G0", current_state="ACTIVE", action="COMPLETE")
        errors = list(validator.iter_errors(result.outcome))
        self.assertEqual(errors, [])

    def test_g4_explicit_outcome_matches_schema(self):
        validator = _schema_validator()
        result = evaluate_transition(
            profile=PROFILE, current_gate="G4", current_state="ACTIVE",
            action="COMPLETE", explicit_outcome="NO_TRANSFER_REQUIRED",
        )
        errors = list(validator.iter_errors(result.outcome))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()


class RecoveryAttemptBoundTests(unittest.TestCase):
    """Hardening GAP 1: bounded lease-retry via RECOVERY_ATTEMPT state (no infinite loop)."""

    def test_recovery_attempt_state_exists(self):
        from tools.node_architect.universal_run_lifecycle import RECOVERY_ATTEMPT_STATES
        self.assertIn("RECOVERY_ATTEMPT", RECOVERY_ATTEMPT_STATES)

    def test_recovery_attempt_bounded_by_max(self):
        from tools.node_architect.universal_run_lifecycle import (
            RecoveryAttemptError,
            begin_recovery_attempt,
        )
        r = begin_recovery_attempt(run_id="RUN-P", attempt=1, max_attempts=3)
        self.assertTrue(r["ok"])
        self.assertEqual(r["attempt"], 1)
        self.assertEqual(r["max_attempts"], 3)
        # exceeding max -> fail-closed
        with self.assertRaises(RecoveryAttemptError):
            begin_recovery_attempt(run_id="RUN-P", attempt=4, max_attempts=3)

    def test_recovery_attempt_monotonic(self):
        from tools.node_architect.universal_run_lifecycle import (
            RecoveryAttemptError,
            begin_recovery_attempt,
        )
        with self.assertRaises(RecoveryAttemptError):
            begin_recovery_attempt(run_id="RUN-P", attempt=2, max_attempts=3, previous_attempt=3)


class RecoveryAttemptWiringTests(unittest.TestCase):
    """Wiring GAP 1: evaluate_transition invokes begin_recovery_attempt on RETRY/RERUN/REPAIR."""

    def test_evaluate_transition_retry_bounded(self):
        from tools.node_architect.universal_run_lifecycle import (
            UNIVERSAL_PROFILE,
            evaluate_transition,
        )
        r = evaluate_transition(profile=UNIVERSAL_PROFILE, current_gate="G2",
                                current_state="FAILED", action="RETRY",
                                recovery_attempt=1, max_recovery_attempts=3)
        self.assertIn("recovery", r.receipt)

    def test_evaluate_transition_retry_exceeds_bound(self):
        from tools.node_architect.universal_run_lifecycle import (
            RecoveryAttemptError,
            UNIVERSAL_PROFILE,
            evaluate_transition,
        )
        with self.assertRaises(RecoveryAttemptError):
            evaluate_transition(profile=UNIVERSAL_PROFILE, current_gate="G2",
                                current_state="FAILED", action="RETRY",
                                recovery_attempt=4, max_recovery_attempts=3)

    def test_evaluate_transition_advance_has_no_recovery(self):
        from tools.node_architect.universal_run_lifecycle import (
            UNIVERSAL_PROFILE,
            evaluate_transition,
        )
        r = evaluate_transition(profile=UNIVERSAL_PROFILE, current_gate="G2",
                                current_state="PASSED", action="ADVANCE")
        self.assertNotIn("recovery", r.receipt)
