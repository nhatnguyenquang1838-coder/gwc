#!/usr/bin/env python3
"""R2: Universal Run G0-G6 lifecycle state machine facade.

C1 (contract identity/version, fixed seven-position lifecycle, illegal-transition
rejection): a deterministic edge matrix over every (gate, state) cell with typed
verdicts per action, plus a pure evaluator that rejects illegal edges with stable
error codes before any effect.

C5 (typed no-op outcomes, execution receipts, effect idempotency, no silent step
execution): every request returns a typed TransitionResult with a NoOpOutcome
reason classification and an execution receipt; identical requests are
idempotent and never perform a silent or untyped effect.

This module is pure and transport-neutral: it never persists state, never grants
authority, never mutates external targets. It composes the E1 kernel's lifecycle
semantics and reuses the committed lifecycle-transition.schema.json shape.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from tools.node_architect.universal_run_kernel import (
    G4_EXPLICIT_OUTCOMES,
    GATES,
    GATE_STATES,
    TERMINAL_STATES,
    UNIVERSAL_PROFILE,
    UniversalRunKernelError,
    transition_lifecycle,
)

PROFILE = UNIVERSAL_PROFILE

ACTIONS = ("ADVANCE", "WAIT", "CONTINUE", "RETRY", "RERUN", "REPAIR", "REPLAN", "COMPLETE", "FAIL", "CANCEL")

# Deterministic legal-action sets per (gate, state). Derived from the kernel's
# transition_lifecycle rules and frozen here so the matrix is certifiable and
# machine-checkable (C1: every (gate,state) cell must appear).
#
# Kernel semantics:
#   FAIL, CANCEL            -> always legal (no precondition)
#   ADVANCE                 -> current_state == PASSED, gate != G6 (target next)
#   WAIT                    -> current_state == ACTIVE
#   CONTINUE                -> current_state in {WAITING, BLOCKED}
#   RETRY/RERUN/REPAIR      -> current_state in {WAITING, BLOCKED, FAILED}
#   REPLAN                  -> current_gate != G0 (any state)
#   COMPLETE                -> current_state == ACTIVE (G4 requires explicit outcome)
_ALWAYS_LEGAL = frozenset({"FAIL", "CANCEL"})
EDGE_MATRIX: dict[tuple[str, str], frozenset[str]] = {}
for gate in GATES:
    for state in GATE_STATES:
        legal: set[str] = set(_ALWAYS_LEGAL)
        if state == "PASSED" and gate != "G6":
            legal.add("ADVANCE")
        if state == "ACTIVE":
            legal.add("WAIT")
            legal.add("COMPLETE")
        if state in {"WAITING", "BLOCKED"}:
            legal.add("CONTINUE")
            legal.add("RETRY")
            legal.add("RERUN")
            legal.add("REPAIR")
        if state in {"WAITING", "BLOCKED", "FAILED"}:
            legal.add("RETRY")
            legal.add("RERUN")
            legal.add("REPAIR")
        if gate != "G0":
            legal.add("REPLAN")
        EDGE_MATRIX[(gate, state)] = frozenset(legal)

# Deterministic no-op reason taxonomy (C5: typed no-op outcomes).
NOOP_REASON_CODES = (
    "NOOP_STATE_UNCHANGED",
    "NOOP_EDGE_UNDECLARED",
    "NOOP_G4_OUTCOME_REQUIRED",
    "NOOP_NO_FORWARD_GATE",
    "NOOP_NOT_STARTED",
)

_NOOP_REASON_BY_CASE: dict[tuple[str, str, str], str] = {}


def _build_noop_reason_map() -> None:
    """Populate the deterministic no-op reason lookup from legal matrix cells."""
    for gate, state in EDGE_MATRIX:
        legal = EDGE_MATRIX[(gate, state)]
        for action in ACTIONS:
            if action not in legal:
                if action == "ADVANCE" and gate == "G6":
                    _NOOP_REASON_BY_CASE[(gate, state, action)] = "NOOP_NO_FORWARD_GATE"
                elif action == "ADVANCE" and state == "NOT_STARTED":
                    _NOOP_REASON_BY_CASE[(gate, state, action)] = "NOOP_NOT_STARTED"
                elif action == "COMPLETE" and gate == "G4" and state == "ACTIVE":
                    _NOOP_REASON_BY_CASE[(gate, state, action)] = "NOOP_G4_OUTCOME_REQUIRED"
                else:
                    _NOOP_REASON_BY_CASE[(gate, state, action)] = "NOOP_EDGE_UNDECLARED"


_build_noop_reason_map()


class LifecycleStateMachineError(ValueError):
    """Deterministic fail-closed lifecycle error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class NoOpOutcome:
    """Typed no-op classification (C5): why no effect was performed."""

    reason_code: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"reason_code": self.reason_code, "detail": self.detail}


@dataclass(frozen=True)
class TransitionResult:
    """Typed outcome + execution receipt for one lifecycle request."""

    outcome: dict[str, Any]
    noop: NoOpOutcome
    receipt: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": copy.deepcopy(self.outcome),
            "noop": self.noop.to_dict(),
            "receipt": copy.deepcopy(self.receipt),
        }


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        from tools.node_architect.canonical_digest.reference_canonicalizer import canonical_json_bytes
        return canonical_json_bytes(value)
    except Exception:
        return json_bytes_fallback(value)


def json_bytes_fallback(value: Any) -> bytes:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(_canonical_json_bytes(part))
    return "sha256:" + h.hexdigest()


def edge_is_legal(*, gate: str, state: str, action: str) -> bool:
    """Machine-checkable verdict for one (gate, state, action) cell."""
    if gate not in GATES or state not in GATE_STATES:
        return False
    action = str(action).upper()
    if action not in ACTIONS:
        return False
    return action in EDGE_MATRIX.get((gate, state), frozenset())


def classify_noop(outcome: Mapping[str, Any]) -> list[str]:
    """Return the typed no-op reason code(s) for an outcome."""
    current_gate = str(outcome.get("current_gate", ""))
    current_state = str(outcome.get("current_state", ""))
    action = str(outcome.get("action", ""))
    code = _NOOP_REASON_BY_CASE.get((current_gate, current_state, action))
    return [code] if code else ["NOOP_STATE_UNCHANGED"]


def lifecycle_edge_digest(*, profile: Mapping[str, Any] | str, current_gate: str, current_state: str, action: str, target_gate: str | None = None, explicit_outcome: str | None = None) -> str:
    """Stable digest over the request identity — used for idempotency receipts."""
    return _sha256_digest(
        profile, current_gate, current_state, str(action).upper(),
        target_gate, explicit_outcome,
    )


def evaluate_transition(
    *,
    profile: Mapping[str, Any] | str,
    current_gate: str,
    current_state: str,
    action: str,
    target_gate: str | None = None,
    explicit_outcome: str | None = None,
) -> TransitionResult:
    """Pure evaluator: returns a typed outcome or raises a deterministic error.

    C5 no-silent-step: this function always returns a TransitionResult with a
    typed no-op reason and an execution receipt; it never returns None and never
    performs an untyped effect. Illegal edges raise LifecycleStateMachineError
    (wrapping the kernel's stable error code) BEFORE any receipt is produced.
    """
    # Fail-closed identity checks before delegating to the kernel.
    try:
        from tools.node_architect.universal_run_kernel import _normalize_profile
        normalized = _normalize_profile(profile)
    except Exception:
        normalized = dict(profile) if isinstance(profile, Mapping) else {"id": str(profile), "version": 1}
    if normalized.get("id") != UNIVERSAL_PROFILE["id"]:
        raise LifecycleStateMachineError("LIFECYCLE_PROFILE_UNSUPPORTED", str(normalized.get("id")))
    if normalized.get("version") != UNIVERSAL_PROFILE["version"]:
        raise LifecycleStateMachineError("LIFECYCLE_PROFILE_UNSUPPORTED", f"version {normalized.get('version')}")
    if current_gate not in GATES:
        raise LifecycleStateMachineError("LIFECYCLE_GATE_UNKNOWN", str(current_gate))
    if current_state not in GATE_STATES:
        raise LifecycleStateMachineError("LIFECYCLE_STATE_UNKNOWN", str(current_state))
    action = str(action).upper()
    if action not in ACTIONS:
        raise LifecycleStateMachineError("LIFECYCLE_ACTION_UNKNOWN", action)
    if target_gate is not None and target_gate not in GATES:
        raise LifecycleStateMachineError("LIFECYCLE_GATE_UNKNOWN", str(target_gate))
    # ADVANCE is deterministic: it always targets the next gate in the fixed
    # seven-position lifecycle. The facade infers it when omitted.
    if action == "ADVANCE" and target_gate is None:
        idx = GATES.index(current_gate)
        if idx >= len(GATES) - 1:
            raise LifecycleStateMachineError("LIFECYCLE_EDGE_UNDECLARED", "G6 has no forward gate")
        target_gate = GATES[idx + 1]

    try:
        outcome = transition_lifecycle(
            lifecycle_profile=profile,
            current_gate=current_gate,
            current_state=current_state,
            action=action,
            target_gate=target_gate,
            explicit_outcome=explicit_outcome,
        )
    except UniversalRunKernelError as exc:
        raise LifecycleStateMachineError(exc.code, exc.detail or "") from exc

    reason_codes = classify_noop(outcome)
    noop = NoOpOutcome(
        reason_code=reason_codes[0] if reason_codes else "NOOP_STATE_UNCHANGED",
        detail=f"edge_kind={outcome.get('edge_kind')} next={outcome.get('next_gate')}:{outcome.get('next_state')}",
    )
    receipt = {
        "artifact_type": "universal-lifecycle-execution-receipt",
        "lifecycle_profile": copy.deepcopy(dict(outcome.get("lifecycle_profile", {}))),
        "current_gate": outcome.get("current_gate"),
        "current_state": outcome.get("current_state"),
        "action": outcome.get("action"),
        "edge_kind": outcome.get("edge_kind"),
        "next_gate": outcome.get("next_gate"),
        "next_state": outcome.get("next_state"),
        "explicit_outcome": outcome.get("explicit_outcome"),
        "execution_performed": bool(outcome.get("execution_performed", False)),
        "transition_digest": lifecycle_edge_digest(
            profile=profile, current_gate=current_gate, current_state=current_state,
            action=action, target_gate=target_gate, explicit_outcome=explicit_outcome,
        ),
        "noop_reason": noop.reason_code,
    }
    return TransitionResult(outcome=outcome, noop=noop, receipt=receipt)


class LifecycleStateMachine:
    """Stateless facade: same inputs -> same typed outcomes, no side effects."""

    def __init__(self, profile: Mapping[str, Any] | str = PROFILE) -> None:
        self.profile = dict(profile) if isinstance(profile, Mapping) else dict(PROFILE)

    def evaluate(
        self,
        *,
        current_gate: str,
        current_state: str,
        action: str,
        target_gate: str | None = None,
        explicit_outcome: str | None = None,
    ) -> TransitionResult:
        return evaluate_transition(
            profile=self.profile,
            current_gate=current_gate,
            current_state=current_state,
            action=action,
            target_gate=target_gate,
            explicit_outcome=explicit_outcome,
        )


RECOVERY_ATTEMPT_STATES = ("RECOVERY_ATTEMPT",)


class RecoveryAttemptError(LifecycleStateMachineError):
    """Typed error when a lease-recovery attempt is invalid or exceeds its bound (hardening)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("RECOVERY_ATTEMPT_BOUND_EXCEEDED", detail)


def begin_recovery_attempt(
    *,
    run_id: str,
    attempt: int,
    max_attempts: int,
    previous_attempt: int | None = None,
) -> dict[str, Any]:
    """Begin a bounded lease-recovery attempt (hardening GAP 1).

    Fail-closed: attempt must be >= 1, <= max_attempts, and strictly greater than
    any previous_attempt (monotonic). Prevents an infinite lease-retry loop by
    bounding recovery attempts before escalation to the Controller.
    """
    if not (isinstance(run_id, str) and run_id.strip()):
        raise LifecycleStateMachineError("RUN_ID_INVALID", "run_id")
    if not (isinstance(attempt, int) and attempt >= 1):
        raise RecoveryAttemptError(f"run={run_id} attempt={attempt} invalid")
    if not (isinstance(max_attempts, int) and max_attempts >= 1):
        raise RecoveryAttemptError(f"run={run_id} max_attempts={max_attempts} invalid")
    if attempt > max_attempts:
        raise RecoveryAttemptError(
            f"run={run_id} attempt={attempt} exceeds max_attempts={max_attempts}"
        )
    if previous_attempt is not None and attempt <= previous_attempt:
        raise RecoveryAttemptError(
            f"run={run_id} attempt={attempt} must exceed previous_attempt={previous_attempt}"
        )
    return {
        "run_id": run_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "state": "RECOVERY_ATTEMPT",
        "ok": True,
    }



__all__ = [
    "ACTIONS",
    "RECOVERY_ATTEMPT_STATES",
    "RecoveryAttemptError",
    "begin_recovery_attempt",
    "EDGE_MATRIX",
    "LifecycleStateMachine",
    "LifecycleStateMachineError",
    "NoOpOutcome",
    "TransitionResult",
    "classify_noop",
    "edge_is_legal",
    "evaluate_transition",
    "lifecycle_edge_digest",
]
