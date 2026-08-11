"""Pure, replay-safe blocked-action escalation (SCRUM-315 / current NA81).

Converts an unauthorized, stale, expired, unsupported or otherwise blocked
action into ONE deterministic outcome:

    BLOCKED        - the action must not proceed; terminal/escalation route
    HUMAN_REQUIRED - a human decision/approval is required before any continue
    WAIT           - a safe checkpoint/CI/readback wait before retrying
    RESOLVE_MINIMAL - checkpoint passed; emit the minimum exact remediation step

The evaluator NEVER performs the blocked action. It performs zero protected
side effects, never manufactures an approval, never broadens scope, and never
blindly retries an unknown outcome. When evidence is unknown/unavailable it
fails closed (BLOCKED + REMEDIATE_EVIDENCE) rather than retrying effects.
Same-identity replay is stable (deterministic digest).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# --- blocked actions (protected, never performed by this evaluator) ----------
_BLOCKED_ACTIONS = {
    "open_draft_pr", "mark_pr_ready", "merge", "auto_merge", "force_push",
    "branch_deletion", "protected_branch_write", "deploy", "release",
    "production_data_change", "production_config_change", "g3_pr_promotion",
    "g4_merge", "g5_deploy", "g6_production",
}

# --- authority / evidence check status codes fed in by the caller ------------
AUTH_UNSUPPORTED = "UNSUPPORTED"          # action not supported by current policy
AUTH_UNAUTHORIZED = "UNAUTHORIZED"        # no valid authority for this action
AUTH_STALE = "STALE"                      # base/head/scope drift detected
AUTH_EXPIRED = "EXPIRED"                  # approval/authority expired
AUTH_UNKNOWN = "UNKNOWN"                  # evidence unknown or unavailable
AUTH_OK = "OK"                            # authority accepted (checkpoint gate next)

_VALID_AUTH = {AUTH_UNSUPPORTED, AUTH_UNAUTHORIZED, AUTH_STALE,
               AUTH_EXPIRED, AUTH_UNKNOWN, AUTH_OK}

# --- decision vocabulary (current NA81) --------------------------------------
DECISION_BLOCKED = "BLOCKED"
DECISION_HUMAN_REQUIRED = "HUMAN_REQUIRED"
DECISION_WAIT = "WAIT"
DECISION_RESOLVE_MINIMAL = "RESOLVE_MINIMAL"

# --- escalation classes (deterministic next-step routing) --------------------
ESC_REMEDIATE_EVIDENCE = "REMEDIATE_EVIDENCE"
ESC_RECAPTURE_BASE_OR_HEAD = "RECAPTURE_BASE_OR_HEAD"
ESC_REVALIDATE_SCOPE = "REVALIDATE_SCOPE"
ESC_REQUEST_G2_APPROVAL = "REQUEST_G2_APPROVAL"
ESC_REQUEST_G4_APPROVAL = "REQUEST_G4_APPROVAL"
ESC_REQUEST_G5_MANUAL_APPROVAL = "REQUEST_G5_MANUAL_APPROVAL"
ESC_REQUEST_G6_APPROVAL = "REQUEST_G6_APPROVAL"
ESC_WAIT_FOR_READBACK = "WAIT_FOR_READBACK"
ESC_WAIT_FOR_CI = "WAIT_FOR_CI"
ESC_REQUEST_HUMAN_INPUT = "REQUEST_HUMAN_INPUT"
ESC_TERMINAL_STOP = "TERMINAL_STOP"

_REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")


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


def escalate_blocked_action(
    *,
    task_id: str,
    repository: str,
    blocked_action: str,
    authority_check: str = AUTH_OK,
    evidence_available: bool = True,
    checkpoint_state: dict[str, object] | None = None,
    prior_escalation: dict[str, object] | None = None,
    event_id_or_idempotency_key: str,
    decided_at: str | None = None,
) -> dict[str, object]:
    """Return a replay-safe escalation decision (no side effects).

    Args:
        task_id: SCRUM-<n> task id.
        repository: ``owner/repo``.
        blocked_action: one of ``_BLOCKED_ACTIONS``.
        authority_check: one of ``_VALID_AUTH`` (UNSUPPORTED/UNAUTHORIZED/STALE/
            EXPIRED/UNKNOWN/OK) describing why the action is blocked.
        evidence_available: whether required dependency/delivery evidence is
            present and readable. Unknown/unavailable evidence fails closed.
        checkpoint_state: optional checkpoint signal(s), e.g. ``checkpoint_done``.
        prior_escalation: prior escalation record for replay conflict detection.
        event_id_or_idempotency_key: deterministic replay key.
        decided_at: optional ISO-8601 UTC decision timestamp.

    Returns a dict with a deterministic decision, escalation_class, reason_code,
    digest and ``execution_performed=False``. The function never mutates inputs.
    """
    if blocked_action not in _BLOCKED_ACTIONS:
        raise ValueError(f"action {blocked_action!r} is not a recognized blocked action")
    if authority_check not in _VALID_AUTH:
        raise ValueError(f"authority_check {authority_check!r} not in {sorted(_VALID_AUTH)}")

    # Replay conflict: identical event key but a changed/prior decision recorded.
    replay_status = "IDEMPOTENT"
    if prior_escalation and \
            str(prior_escalation.get("event_id_or_idempotency_key")) == event_id_or_idempotency_key:
        replay_status = "CONFLICT"

    # --- fail-closed branch: evidence unknown/unavailable ---------------------
    if not evidence_available:
        decision = DECISION_BLOCKED
        reason_code = "ESCALATION_EVIDENCE_UNAVAILABLE"
        escalation_class = ESC_REMEDIATE_EVIDENCE
        remediation_scope = None
    else:
        # --- classified blocked routes (deterministic, no side effects) --------
        if authority_check == AUTH_UNSUPPORTED:
            decision = DECISION_BLOCKED
            reason_code = "ESCALATION_ACTION_UNSUPPORTED"
            escalation_class = ESC_TERMINAL_STOP
            remediation_scope = None
        elif authority_check == AUTH_UNAUTHORIZED:
            decision = DECISION_HUMAN_REQUIRED
            reason_code = "ESCALATION_ACTION_UNAUTHORIZED"
            escalation_class = ESC_REQUEST_HUMAN_INPUT
            remediation_scope = None
        elif authority_check == AUTH_STALE:
            decision = DECISION_BLOCKED
            reason_code = "ESCALATION_BASE_HEAD_STALE"
            escalation_class = ESC_RECAPTURE_BASE_OR_HEAD
            remediation_scope = None
        elif authority_check == AUTH_EXPIRED:
            decision = DECISION_HUMAN_REQUIRED
            reason_code = "ESCALATION_AUTHORITY_EXPIRED"
            escalation_class = ESC_REVALIDATE_SCOPE
            remediation_scope = None
        elif authority_check == AUTH_UNKNOWN:
            decision = DECISION_BLOCKED
            reason_code = "ESCALATION_AUTHORITY_UNKNOWN"
            escalation_class = ESC_REMEDIATE_EVIDENCE
            remediation_scope = None
        else:
            # authority_check == OK -> checkpoint-before-wait gate
            checkpoint_done = bool((checkpoint_state or {}).get("checkpoint_done", False))
            if not checkpoint_done:
                decision = DECISION_WAIT
                reason_code = "ESCALATION_CHECKPOINT_REQUIRED"
                escalation_class = ESC_WAIT_FOR_READBACK
                remediation_scope = None
            else:
                decision = DECISION_RESOLVE_MINIMAL
                reason_code = "ESCALATION_CHECKPOINT_PASSED"
                escalation_class = ESC_WAIT_FOR_CI
                remediation_scope = f"minimal-exact:{blocked_action}"

    escalation_digest = _digest(
        task_id, repository, blocked_action, authority_check, evidence_available,
        decision, reason_code, escalation_class, event_id_or_idempotency_key,
    )

    return {
        "schema_version": "1.0",
        "artifact_type": "blocked-action-escalation",
        "task_id": task_id,
        "repository": repository,
        "blocked_action": blocked_action,
        "authority_check": authority_check,
        "evidence_available": bool(evidence_available),
        "decision": decision,
        "escalation_class": escalation_class,
        "checkpoint_required": decision == DECISION_WAIT,
        "remediation_scope": remediation_scope,
        "execution_performed": False,
        "reason_code": reason_code,
        "replay_status": replay_status,
        "escalation_digest": escalation_digest,
        "event_id_or_idempotency_key": event_id_or_idempotency_key,
        "decided_at": decided_at,
    }
