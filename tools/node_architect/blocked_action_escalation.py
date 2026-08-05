"""Pure, replay-safe blocked-action escalation.

Enforces checkpoint-before-wait and minimal exact remediation. The evaluator NEVER
performs the blocked action; it only decides ESCALATE / WAIT / RESOLVE_MINIMAL and
emits a deterministic digest.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

_REASON_RE = re.compile(r"^ESCALATION_[A-Z_]+$")


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


_BLOCKED_ACTIONS = {
    "open_draft_pr", "mark_pr_ready", "merge", "auto_merge", "force_push",
    "branch_deletion", "protected_branch_write", "deploy", "release",
    "production_data_change", "production_config_change", "g3_pr_promotion",
    "g4_merge", "g5_deploy", "g6_production",
}


def escalate_blocked_action(
    *,
    task_id: str,
    repository: str,
    blocked_action: str,
    checkpoint_state: dict[str, object],
    prior_escalation: dict[str, object] | None = None,
    event_id_or_idempotency_key: str,
    decided_at: str | None = None,
) -> dict[str, object]:
    """Return a replay-safe escalation decision (no side effects)."""
    if blocked_action not in _BLOCKED_ACTIONS:
        raise ValueError(f"action {blocked_action!r} is not a recognized blocked action")

    checkpoint_done = bool(checkpoint_state.get("checkpoint_done", False))
    checkpoint_required = not checkpoint_done

    # Replay conflict: same event key, changed decision.
    replay_status = "IDEMPOTENT"
    if prior_escalation and \
            str(prior_escalation.get("event_id_or_idempotency_key")) == event_id_or_idempotency_key:
        replay_status = "CONFLICT"

    if checkpoint_required:
        decision = "WAIT"
        reason_code = "ESCALATION_CHECKPOINT_REQUIRED"
        remediation_scope = None
    else:
        decision = "RESOLVE_MINIMAL"
        reason_code = "ESCALATION_CHECKPOINT_PASSED"
        remediation_scope = f"minimal-exact:{blocked_action}"

    escalation_digest = _digest(
        task_id, repository, blocked_action, checkpoint_done,
        decision, reason_code, event_id_or_idempotency_key,
    )

    return {
        "schema_version": "1.0",
        "artifact_type": "blocked-action-escalation",
        "task_id": task_id,
        "repository": repository,
        "blocked_action": blocked_action,
        "decision": decision,
        "checkpoint_required": checkpoint_required,
        "remediation_scope": remediation_scope,
        "execution_performed": False,
        "reason_code": reason_code,
        "replay_status": replay_status,
        "escalation_digest": escalation_digest,
        "event_id_or_idempotency_key": event_id_or_idempotency_key,
        "decided_at": decided_at,
    }
