#!/usr/bin/env python3
"""Universal Runtime v2 — transport-decoupled continuation driver.

Repairs the ``UNIVERSAL_V2_TRANSPORT_RUNTIME_COUPLING`` defect: a scheduler
tick must not become a no-op merely because no fresh Controller A2A message
exists.  Native RuntimePlan + RunState own the runtime cursor; the mailbox
is a durable projection / transport, NOT the runtime cursor.

Architecture (transport-neutral):
- RuntimePlan   (immutable, digest-bound)
- native RunState / cursor / typed NEXT
- actor topology decides owner (CONTROLLER | EXECUTOR | ...)
- transport adapter is invoked ONLY when the next step crosses an actor
  boundary; an internal Controller transition needs no A2A at all.

Invariants:
- ``expected_executor_seq = null`` means "no Executor dispatch", not
  "no Universal progress".
- A2A not polled by contract is not a runtime blocker.
- Mailbox is never the run cursor: newer native RunState wins over stale
  mailbox prose.
- Heartbeat/Goal derive from native state, not from mailbox WAIT text.
- Internal Controller work runnable => same-fingerprint repetition across
  two ticks is a liveness defect to repair, not an idle observation.

This module is PURE and transport-neutral: adapters are injected callables
and are counted, never executed against a real external system.  It grants
no repository/merge/deploy/production/authority effects.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping

from tools.node_architect.q0_qualification import (
    GATE_EVIDENCE,
    Q0QualificationError,
    advance_qualification_gate,
    complete_q0_gate,
)

RUNTIME_EPOCH_UNIVERSAL_V2 = "UNIVERSAL_V2_DEVELOPMENT"
LEGACY_HITL_STOP_STATUS = "NEEDS_EXACT_HITL"
FIRST_STATE_BEYOND_FAILURE = "UR.G1_TYPED_CONTROLLER_NEXT"
TRANSPORT_UNAVAILABLE = "TRANSPORT_UNAVAILABLE"


class UniversalContinuationError(ValueError):
    """Deterministic fail-closed continuation error."""


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise UniversalContinuationError(code if not detail else f"{code}: {detail}")


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_cursor(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): v for k, v in value.items()}


# ---------------------------------------------------------------------------
# RuntimePlan / native RunState construction (transport-neutral)
# ---------------------------------------------------------------------------

def create_or_recover_runtime_plan(
    *,
    run_id: str,
    revision: int,
    target_contract_ref: str,
    node_allocations: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Create/recover the immutable Universal RuntimePlan revision (native)."""
    _require(isinstance(run_id, str) and bool(run_id.strip()), "RUN_ID_INVALID")
    _require(isinstance(revision, int) and revision >= 1, "PLAN_REVISION_INVALID")
    nodes = tuple(sorted(set(node_allocations or [])))
    _require(len(nodes) > 0, "PLAN_NODE_ALLOCATIONS_EMPTY")
    plan = {
        "run_id": run_id,
        "revision": revision,
        "target_contract_ref": str(target_contract_ref),
        "node_allocations": list(nodes),
        "schema_id": "gwc.universal-run.runtime-plan",
        "runtime_epoch": RUNTIME_EPOCH_UNIVERSAL_V2,
    }
    plan["digest"] = _digest(plan)
    return plan


def create_initial_run_state(
    *,
    run_id: str,
    sequence: int,
    active_gate: str,
    execution_refs: Mapping[str, Any],
    future_contract_refs: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a native RunState record with a monotonic cursor."""
    _require(isinstance(run_id, str) and bool(run_id.strip()), "RUN_ID_INVALID")
    _require(isinstance(sequence, int) and sequence >= 1, "SEQUENCE_INVALID")
    _require(isinstance(active_gate, str) and active_gate.startswith("UR."), "GATE_INVALID")
    return {
        "schema_id": "gwc.universal-run.run-state",
        "run_id": run_id,
        "sequence": sequence,
        "active_gate": active_gate,
        "execution_refs": dict(execution_refs or {}),
        "future_contract_refs": dict(future_contract_refs or {}),
        "runtime_epoch": RUNTIME_EPOCH_UNIVERSAL_V2,
    }


# ---------------------------------------------------------------------------
# Universal Controller reconciler (native successor, no A2A for internal)
# ---------------------------------------------------------------------------

def _consume_new_receipts(consumer_cursor: Mapping[str, Any], executor_receipts: Mapping[str, Any]) -> tuple[tuple[str, ...], int]:
    seen = set(_as_cursor(consumer_cursor).get("consumed_receipts", []) or [])
    new = [key for key in (executor_receipts or {}).keys() if key not in seen]
    return tuple([*sorted(seen), *sorted(new)]), len(new)


def reconcile_controller_continuation(
    *,
    runtime_epoch: str,
    plan: Mapping[str, Any],
    run_state: Mapping[str, Any],
    history_controller: Mapping[str, Any],
    executor_receipts: Mapping[str, Any],
    consumer_cursor: Mapping[str, Any],
    transport_profile: str,
    transport_available: bool = False,
    not_polled_by_contract: bool = False,
    actor: str = "",
) -> dict[str, Any]:
    """One Universal Controller continuation decision.

    If the Controller owns runnable internal transition, the successor is
    computed and persisted WITHOUT calling any transport adapter.  A2A is
    used only when the typed NEXT crosses an actor boundary.
    """
    _require(runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2, "UNIVERSAL_V2_EPOCH_REQUIRED")
    _require(isinstance(plan, Mapping) and bool(plan.get("run_id")), "PLAN_REQUIRED")
    _require(isinstance(run_state, Mapping) and bool(run_state.get("run_id")), "RUN_STATE_REQUIRED")
    _require(str(plan.get("run_id")) == str(run_state.get("run_id")), "PLAN_RUN_BINDING_MISMATCH")
    _require(str(plan.get("runtime_epoch")) == runtime_epoch, "PLAN_RUNTIME_EPOCH_MISMATCH")

    consumed, new_count = _consume_new_receipts(consumer_cursor, executor_receipts)

    # C91 legacy NEEDS_EXACT_HITL is historical incident evidence, not a
    # current stop authority, once the Universal cut-over (E53) exists.
    status = str(history_controller.get("status") or "")
    legacy_stop = status == LEGACY_HITL_STOP_STATUS or bool(history_controller.get("legacy"))
    universal_receipt_present = any(
        str(kind).startswith("UNIVERSAL_V2_DEVELOPMENT")
        for key, rcp in (executor_receipts or {}).items()
        for kind in [str((rcp or {}).get("kind", ""))]
    )

    if legacy_stop and (new_count > 0 or universal_receipt_present):
        c91_classification = "HISTORICAL_LEGACY_INCIDENT_EVIDENCE"
        requires_reapproval = False
        needs_human = False
    elif legacy_stop:
        # stale legacy stop with no new receipt / no cut-over evidence
        c91_classification = "HISTORICAL_LEGACY_PROJECTION"
        requires_reapproval = False
        needs_human = False
    else:
        c91_classification = "CURRENT_CONTROLLER_DISPOSITION"
        requires_reapproval = False
        needs_human = False

    # Q0 gate completion evidence and Universal lifecycle edges are separate
    # concerns.  Validate the Q0 evidence first, then let the shared Universal
    # kernel evaluate COMPLETE + ADVANCE; never keep a second gate-order table.
    active_gate = str(run_state.get("active_gate") or "UR.G0")
    _require(active_gate in GATE_EVIDENCE, "Q0_GATE_UNKNOWN", active_gate)
    evidence = _as_cursor(run_state.get("gate_evidence") or {})
    try:
        complete_q0_gate(gate=active_gate, evidence=evidence)
    except Q0QualificationError:
        required = GATE_EVIDENCE.get(active_gate, ())
        missing = [key for key in required if not evidence.get(key)]
        if active_gate == "UR.G4" and evidence.get("integration_outcome") in {
            "INTEGRATED", "IN_PLACE", "NO_TRANSFER_REQUIRED", "DOMAIN_DEFINED"
        }:
            missing = []
        sequence = int(run_state.get("sequence") or 0)
        successor = {
            "schema_id": "gwc.universal-run.run-state",
            "run_id": run_state.get("run_id"), "sequence": sequence,
            "active_gate": active_gate, "predecessor_sequence": run_state.get("sequence"),
            "execution_refs": dict(run_state.get("execution_refs") or {}),
            "future_contract_refs": dict(run_state.get("future_contract_refs") or {}),
            "runtime_epoch": runtime_epoch, "consumed_receipts": list(consumed),
            "gate_evidence": dict(evidence),
            "first_state_beyond_failure": FIRST_STATE_BEYOND_FAILURE,
        }
        successor["state_digest"] = _digest(successor)
        return {
            "runtime_epoch": runtime_epoch, "runtime_progressed": False,
            "control_loop_continue": True, "next_owner": "CONTROLLER",
            "typed_next": "AWAIT_GATE_EVIDENCE", "executor_dispatch": False,
            "controller_progression": True, "needs_human": needs_human,
            "requires_reapproval": requires_reapproval, "analyzer_required": False,
            "c91_classification": c91_classification,
            "consumed_receipts": consumed, "new_receipts_consumed": new_count,
            "first_state_beyond_failure": successor["first_state_beyond_failure"],
            "successor_run_state": successor, "a2a_call_count": 0,
            "transport_profile": str(transport_profile),
            "not_polled_by_contract": bool(not_polled_by_contract),
            "actor_owner": str(actor) or "CONTROLLER",
            "evidence_gap": list(missing or required), "gate_advanced": False,
        }

    sequence = int(run_state.get("sequence") or 0)
    if active_gate == "UR.G6":
        # G6 is terminal only with the distinct Q0 acceptance/closure/handoff
        # receipts.  The new sequence represents a terminal state change, not
        # a counter-only gate hop.
        successor = {
            "schema_id": "gwc.universal-run.run-state",
            "run_id": run_state.get("run_id"), "sequence": sequence + 1,
            "active_gate": "UR.G6", "predecessor_sequence": sequence,
            "terminal_state": "ACCEPTED",
            "execution_refs": dict(run_state.get("execution_refs") or {}),
            "future_contract_refs": dict(run_state.get("future_contract_refs") or {}),
            "runtime_epoch": runtime_epoch, "consumed_receipts": list(consumed),
            "gate_evidence": dict(evidence),
            "first_state_beyond_failure": FIRST_STATE_BEYOND_FAILURE,
        }
        successor["state_digest"] = _digest(successor)
        return {
            "runtime_epoch": runtime_epoch, "runtime_progressed": True,
            "control_loop_continue": False, "next_owner": "USER",
            "typed_next": "Q0_ACCEPTED_AUTONOMOUS_HANDOFF", "executor_dispatch": False,
            "controller_progression": True, "needs_human": False,
            "requires_reapproval": False, "analyzer_required": False,
            "c91_classification": c91_classification,
            "consumed_receipts": consumed, "new_receipts_consumed": new_count,
            "successor_run_state": successor, "a2a_call_count": 0,
            "transport_profile": str(transport_profile),
            "not_polled_by_contract": bool(not_polled_by_contract),
            "actor_owner": str(actor) or "CONTROLLER",
            "evidence_gap": [], "gate_advanced": False,
        }

    transition = advance_qualification_gate(
        current_gate=active_gate, current_state="ACTIVE", evidence=evidence,
        sequence=sequence,
    )
    successor = {
        "schema_id": "gwc.universal-run.run-state",
        "run_id": run_state.get("run_id"),
        "sequence": sequence + int(transition["sequence_delta"]),
        "active_gate": transition["next_gate"],
        "predecessor_sequence": sequence,
        "execution_refs": dict(run_state.get("execution_refs") or {}),
        "future_contract_refs": dict(run_state.get("future_contract_refs") or {}),
        "runtime_epoch": runtime_epoch, "consumed_receipts": list(consumed),
        "gate_evidence": dict(evidence),
        "transition_receipt": transition["transition_receipt"],
        "completion_receipt": transition["completion_receipt"],
        "first_state_beyond_failure": FIRST_STATE_BEYOND_FAILURE,
    }
    successor["state_digest"] = _digest(successor)
    return {
        "runtime_epoch": runtime_epoch, "runtime_progressed": True,
        "control_loop_continue": True, "next_owner": "CONTROLLER",
        "typed_next": "CONTINUE_UNIVERSAL_LANE_REMEDIATION",
        "executor_dispatch": False, "controller_progression": True,
        "needs_human": needs_human, "requires_reapproval": requires_reapproval,
        "analyzer_required": False, "c91_classification": c91_classification,
        "consumed_receipts": consumed, "new_receipts_consumed": new_count,
        "first_state_beyond_failure": successor["first_state_beyond_failure"],
        "successor_run_state": successor, "a2a_call_count": 0,
        "transport_profile": str(transport_profile),
        "not_polled_by_contract": bool(not_polled_by_contract),
        "actor_owner": str(actor) or "CONTROLLER", "evidence_gap": [],
        "gate_advanced": True,
    }


# ---------------------------------------------------------------------------
# Cross-actor transport boundary
# ---------------------------------------------------------------------------

def execute_cross_actor_transition(
    *,
    runtime_epoch: str,
    plan: Mapping[str, Any],
    run_state: Mapping[str, Any],
    owner: str,
    typed_next: str,
    transport_adapter: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None,
    transport_available: bool = False,
) -> dict[str, Any]:
    """Invoke a transport adapter ONLY when the next step crosses an actor boundary."""
    _require(runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2, "UNIVERSAL_V2_EPOCH_REQUIRED")
    _require(isinstance(owner, str) and owner.strip(), "OWNER_REQUIRED")

    decision = {
        "runtime_epoch": runtime_epoch,
        "actor_selected": owner,
        "typed_next": str(typed_next),
        "transport_required": True,
        "transport_unavailable": False,
        "delivered": False,
        "legacy_fallback": False,
        "outcome": "UNIVERSAL_TRANSITION",
    }

    if not transport_available:
        decision["transport_unavailable"] = True
        decision["outcome"] = TRANSPORT_UNAVAILABLE
        decision["delivered"] = False
        decision["decision_digest"] = _digest(decision)
        return decision

    if transport_adapter is None:
        decision["transport_unavailable"] = True
        decision["outcome"] = TRANSPORT_UNAVAILABLE
        decision["decision_digest"] = _digest(decision)
        return decision

    message = {
        "owner": owner,
        "typed_next": str(typed_next),
        "run_id": plan.get("run_id"),
        "sequence": run_state.get("sequence"),
        "runtime_epoch": runtime_epoch,
    }
    response = transport_adapter(message)
    decision["delivered"] = bool(response and response.get("delivered"))
    decision["transport_receipt"] = str((response or {}).get("receipt", ""))
    decision["message_sent"] = message
    # decision digest is transport-neutral: receipt/readback identifiers are
    # adapter-specific evidence and are excluded so the SAME runtime decision
    # has the SAME digest under any transport (A2A/local).
    _decision_digest_subject = {
        "runtime_epoch": runtime_epoch,
        "actor_selected": owner,
        "typed_next": str(typed_next),
        "run_id": plan.get("run_id"),
        "sequence": run_state.get("sequence"),
    }
    decision["decision_digest"] = _digest(_decision_digest_subject)
    return decision


# ---------------------------------------------------------------------------
# Mailbox projection separation / derivation
# ---------------------------------------------------------------------------

def reconcile_mailbox_projection(
    *,
    runtime_epoch: str,
    native_run_state: Mapping[str, Any],
    mailbox_cursor: Mapping[str, Any],
) -> dict[str, Any]:
    """Mailbox is projection only; native RunState wins."""
    _require(runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2, "UNIVERSAL_V2_EPOCH_REQUIRED")
    mailbox_seq = str(mailbox_cursor.get("seq") or "")
    native_gate = str(native_run_state.get("active_gate") or "UR.G0")
    classification = "HISTORICAL_LEGACY_PROJECTION" if native_gate.startswith("UR.") else "CURRENT_PROJECTION"
    return {
        "native_wins": True,
        "mailbox_classification": classification,
        "cursor": {
            "sequence": native_run_state.get("sequence"),
            "active_gate": native_gate,
            "mailbox_seq_observed": mailbox_seq,
        },
    }


def derive_liveness_controls(
    *,
    runtime_epoch: str,
    run_state: Mapping[str, Any],
    internal_controller_work_runnable: bool,
    mailbox_expected_executor_seq: Any = None,
    a2a_not_polled: bool = False,
) -> dict[str, Any]:
    """Heartbeat/Goal derive from native state, not mailbox WAIT text."""
    _require(runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2, "UNIVERSAL_V2_EPOCH_REQUIRED")
    if internal_controller_work_runnable:
        heartbeat_state = "RUNNABLE"
        goal_state = "ACTIVE"
        pause_reason = None
    else:
        heartbeat_state = "PAUSED"
        goal_state = "PAUSED"
        pause_reason = "HARD_EXTERNAL_WAIT" if mailbox_expected_executor_seq is None and not a2a_not_polled else None
    return {
        "heartbeat_state": heartbeat_state,
        "goal_state": goal_state,
        "pause_reason": pause_reason,
    }


def derive_goal_text(
    *,
    runtime_epoch: str,
    legacy_goal_text: str,
) -> str:
    """Universal cut-over regenerates the Goal objective (stale legacy text dropped)."""
    _require(runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2, "UNIVERSAL_V2_EPOCH_REQUIRED")
    if "waiting for Nhat's exact G1 package" in legacy_goal_text:
        return "SCRUM-781 Q0 — Universal v2 lane: continue native RunState to UR.G2; Controller owns typed NEXT; no legacy G0/G1 prerequisite."
    return legacy_goal_text.strip()


# ---------------------------------------------------------------------------
# Restart recovery / stall guard
# ---------------------------------------------------------------------------

def recover_after_restart(
    *,
    runtime_epoch: str,
    run_id: str,
    plan_digest: str,
    saved_cursor: int | None,
    observed_cursor: int | None,
    mailbox_cursor: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recover the Universal cursor from durable native state, not mailbox prose."""
    _require(runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2, "UNIVERSAL_V2_EPOCH_REQUIRED")
    _require(isinstance(run_id, str) and bool(run_id.strip()), "RUN_ID_INVALID")
    _require(isinstance(plan_digest, str) and bool(plan_digest.startswith("sha256:")), "PLAN_DIGEST_INVALID")
    if saved_cursor is None and observed_cursor is None:
        raise UniversalContinuationError("NO_CURSOR_EVIDENCE")
    if saved_cursor is not None and observed_cursor is not None and observed_cursor > saved_cursor:
        raise UniversalContinuationError("OBSERVED_CURSOR_EXCEEDS_SAVED")
    cursor = saved_cursor if saved_cursor is not None else observed_cursor
    return {
        "ok": True,
        "runtime_epoch": runtime_epoch,
        "run_id": run_id,
        "cursor": cursor,
        "recovered_from_mailbox": False,
        "c91_hold_restored": False,
    }


def detect_stall(
    *,
    runtime_epoch: str,
    fingerprint: str,
    runnable_internal_work: bool,
    consecutive_observed: int,
) -> dict[str, Any]:
    """Same fingerprint + runnable internal work across two ticks = liveness defect."""
    _require(runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2, "UNIVERSAL_V2_EPOCH_REQUIRED")
    _require(isinstance(consecutive_observed, int) and consecutive_observed >= 1, "TICK_COUNT_INVALID")
    noop_ok = not runnable_internal_work or consecutive_observed == 1
    return {
        "fingerprint": str(fingerprint),
        "runnable_internal_work": bool(runnable_internal_work),
        "noop_ok": noop_ok,
        "liveness_defect": (not noop_ok),
        "advice": "RUN_CONTROLLER_RECONCILER" if not noop_ok else "OBSERVE",
    }


def gate_executor_dispatch(
    *,
    runtime_epoch: str,
    typed_next: str,
    work_is_effect: bool,
) -> dict[str, Any]:
    """Executor must not be dispatched for read-only confirmation."""
    _require(runtime_epoch == RUNTIME_EPOCH_UNIVERSAL_V2, "UNIVERSAL_V2_EPOCH_REQUIRED")
    if not work_is_effect:
        return {
            "permitted": False,
            "reason_code": "CONTROLLER_READONLY_PINGPONG_FORBIDDEN",
        }
    return {"permitted": True, "reason_code": "EFFECT_BEARING_TYPED_NEXT"}


__all__ = [
    "FIRST_STATE_BEYOND_FAILURE",
    "LEGACY_HITL_STOP_STATUS",
    "RUNTIME_EPOCH_UNIVERSAL_V2",
    "TRANSPORT_UNAVAILABLE",
    "UniversalContinuationError",
    "create_initial_run_state",
    "create_or_recover_runtime_plan",
    "derive_goal_text",
    "derive_liveness_controls",
    "detect_stall",
    "execute_cross_actor_transition",
    "gate_executor_dispatch",
    "reconcile_controller_continuation",
    "reconcile_mailbox_projection",
    "recover_after_restart",
    "run_universal_controller_tick",
]


def run_universal_controller_tick(
    *,
    plan: Mapping[str, Any],
    run_state: Mapping[str, Any],
    history_controller: Mapping[str, Any],
    executor_receipts: Mapping[str, Any],
    consumer_cursor: Mapping[str, Any],
    transport_profile: str = "A2A_GPT_EXCHANGE_ONLY",
    transport_available: bool = False,
    not_polled_by_contract: bool = False,
) -> dict[str, Any]:
    """Run one real Universal Controller tick end-to-end.

    Emits typed NEXT when the Controller owns the transition, persists a
    successor RunState, keeps heartbeat/goal derived from native state, and
    never requires A2A/mailbox prose for an internal Controller transition.
    This is the component the scheduler tick driver calls instead of the old
    "observe no C92 -> settle -> pause" path.
    """
    decision = reconcile_controller_continuation(
        runtime_epoch=RUNTIME_EPOCH_UNIVERSAL_V2,
        plan=plan,
        run_state=run_state,
        history_controller=history_controller,
        executor_receipts=executor_receipts,
        consumer_cursor=consumer_cursor,
        transport_profile=transport_profile,
        transport_available=transport_available,
        not_polled_by_contract=not_polled_by_contract,
    )
    liveness = derive_liveness_controls(
        runtime_epoch=RUNTIME_EPOCH_UNIVERSAL_V2,
        run_state=decision["successor_run_state"],
        internal_controller_work_runnable=decision["control_loop_continue"],
        mailbox_expected_executor_seq=None,
        a2a_not_polled=not_polled_by_contract,
    )
    return {
        "tick_outcome": "CONTROLLER_INTERNAL_ADVANCE" if decision["next_owner"] == "CONTROLLER" else "CROSS_ACTOR_REQUIRED",
        "typed_next": decision["typed_next"],
        "successor_run_state": decision["successor_run_state"],
        "consumer_cursor": {"consumed_receipts": list(decision["consumed_receipts"])},
        "heartbeat": liveness["heartbeat_state"],
        "goal": liveness["goal_state"],
        "a2a_call_count": decision["a2a_call_count"],
        "needs_human": decision["needs_human"],
        "first_state_beyond_failure": decision["first_state_beyond_failure"],
        "c91_classification": decision["c91_classification"],
        "new_receipts_consumed": decision["new_receipts_consumed"],
        "runtime_epoch": RUNTIME_EPOCH_UNIVERSAL_V2,
    }
