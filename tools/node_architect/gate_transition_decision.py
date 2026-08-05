"""Pure, replay-safe gate transition decision.

Decides PASS/BLOCK/CONTINUE/AWAITING_APPROVAL/NOT_APPLICABLE and identifies the
next permitted preparation node and state transition. The evaluator NEVER performs
the transition; it only records the decision and a deterministic digest.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

_DECISION_RE = re.compile(r"^TRANSITION_[A-Z_]+$")


def _canon(obj: Any) -> str:
    if isinstance(obj, dict):
        return "{" + ",".join(f"{k}:{_canon(v)}" for k, v in sorted(obj.items())) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_canon(v) for v in obj) + "]"
    return str(obj)


def _digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(_canon(p).encode("utf-8"))
    return "sha256:" + h.hexdigest()


# Canonical gate precedence for decision selection.
_PRECEDENCE = [
    "TRANSITION_INPUT_INVALID",
    "TRANSITION_REPLAY_CONFLICT",
    "TRANSITION_BINDING_MISMATCH",
    "TRANSITION_EVIDENCE_MISSING",
    "TRANSITION_EVIDENCE_STALE",
    "TRANSITION_APPROVAL_REQUIRED",
    "TRANSITION_APPROVAL_INVALID",
    "TRANSITION_ENVELOPE_INACTIVE",
    "TRANSITION_READBACK_REQUIRED",
    "TRANSITION_READBACK_MISMATCH",
    "TRANSITION_LATER_GATE_INHERITANCE_REJECTED",
]


def decide_gate_transition(
    *,
    task_id: str,
    repository: str,
    gate_state_resolution: dict[str, object],
    evidence_map: dict[str, object],
    authority_boundary_decision: dict[str, object],
    approval_validation: dict[str, object] | None,
    g2_execution_envelope: dict[str, object] | None,
    observed_task_state: str | None,
    event_id_or_idempotency_key: str,
    prior_decision: dict[str, object] | None = None,
    decided_at: str | None = None,
) -> dict[str, object]:
    """Return a replay-safe gate transition decision (no side effects)."""
    current_gate = str(gate_state_resolution.get("current_gate", ""))
    current_state = str(gate_state_resolution.get("current_state", ""))

    # Detect blocking conditions by precedence.
    decision = None
    reason_code = None
    flags = evidence_map.get("flags", []) if isinstance(evidence_map, dict) else []
    if isinstance(flags, list):
        for code in _PRECEDENCE:
            if code in flags:
                decision = "BLOCK"
                reason_code = code
                break

    if decision is None:
        if approval_validation is None:
            decision = "AWAITING_APPROVAL"
            reason_code = "TRANSITION_APPROVAL_REQUIRED"
        elif g2_execution_envelope is not None and \
                str(g2_execution_envelope.get("activation_state")) != "ACTIVE":
            decision = "BLOCK"
            reason_code = "TRANSITION_ENVELOPE_INACTIVE"
        else:
            # Exact readback required before declaring PASS.
            if observed_task_state is None:
                decision = "CONTINUE"
                reason_code = "TRANSITION_READBACK_REQUIRED"
            elif observed_task_state != current_state:
                decision = "BLOCK"
                reason_code = "TRANSITION_READBACK_MISMATCH"
            else:
                decision = "PASS"
                reason_code = "TRANSITION_PASS"

    requires_human_approval = decision in ("AWAITING_APPROVAL",)
    checkpoint_required = decision in ("CONTINUE", "AWAITING_APPROVAL")
    readback_required = decision == "CONTINUE"

    # Replay conflict: same event key, changed semantic decision.
    replay_status = "IDEMPOTENT"
    if prior_decision:
        if str(prior_decision.get("event_id_or_idempotency_key")) == event_id_or_idempotency_key \
                and prior_decision.get("decision") != decision:
            replay_status = "CONFLICT"
            decision = "BLOCK"
            reason_code = "TRANSITION_REPLAY_CONFLICT"

    decision_digest = _digest(
        task_id, current_gate, current_state, decision, reason_code,
        event_id_or_idempotency_key,
    )

    return {
        "schema_version": "1.0",
        "artifact_type": "gate-transition-decision",
        "task_id": task_id,
        "repository": repository,
        "current_gate": current_gate,
        "current_state": current_state,
        "decision": decision,
        "transition": gate_state_resolution.get("expected_transition"),
        "expected_state": gate_state_resolution.get("expected_state"),
        "readback_required": readback_required,
        "next_gate": gate_state_resolution.get("next_gate"),
        "next_node": gate_state_resolution.get("next_node"),
        "requires_human_approval": requires_human_approval,
        "checkpoint_required": checkpoint_required,
        "evidence_refs": list(evidence_map.get("refs", [])) if isinstance(evidence_map, dict) else [],
        "reason_code": reason_code,
        "replay_status": replay_status,
        "decision_digest": decision_digest,
        "execution_performed": False,
        "event_id_or_idempotency_key": event_id_or_idempotency_key,
        "decided_at": decided_at,
    }
