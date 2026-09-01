from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class PlanBoundRuntimeError(Exception):
    """Raised when a plan-bound runtime step violates the RuntimePlan contract."""


@dataclass
class RuntimePlanStep:
    step_id: str
    semantic_action: str
    allowed_actions: tuple[str, ...] = ()
    edges: dict[str, dict[str, str]] = field(default_factory=dict)
    node_instruction_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "semantic_action": self.semantic_action,
            "allowed_actions": list(self.allowed_actions),
            "edges": self.edges,
            "node_instruction_ref": self.node_instruction_ref,
        }


def _normalize_action(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace(" ", "_")


def _revalidate_authority(
    authority: Mapping[str, Any],
    requested_action: str | None,
    runtime_plan_ref: str,
    step_id: str,
) -> dict[str, Any]:
    """Invoke the canonical GWC authority boundary check (M4).

    Returns ``{"allowed": bool, "reason_code": str}``. The envelope is
    revalidated only when the boundary check does NOT hard-BLOCK the action —
    task/repo/base+head SHA/scope/gate/expiry are all validated by the
    canonical validator, never by ``authority_id`` presence alone.
    """
    from datetime import datetime, timezone

    from tools.node_architect.authority_boundary_check import (
        ACTION_TO_MINIMUM_GATE,
        check_authority_boundary,
    )

    task_id = authority.get("task_id", "")
    repository = authority.get("repository", "")
    base_sha = authority.get("base_sha", "0" * 40)
    head_sha = authority.get("head_sha", "0" * 40)
    scope_hash = authority.get("scope_hash", "sha256:" + "0" * 64)
    current_gate = authority.get("gate", "G0_CONTEXT")
    allowed_actions = list(authority.get("allowed_actions", []))
    excluded_actions = list(authority.get("excluded_actions", []))
    risk_class = authority.get("risk_class", "R0")
    envelope_expires_at = authority.get("expires_at")
    evaluated_at = authority.get("evaluated_at") or datetime.now(timezone.utc).isoformat()
    event_id = f"{authority.get('authority_id', 'auth')}:{runtime_plan_ref}:{step_id}"

    decision = check_authority_boundary(
        task_id=task_id,
        repository=repository,
        requested_action=requested_action or "",
        gate_state_resolution={
            "task_id": task_id,
            "repository": repository,
            "current_base_sha": base_sha,
            "head_sha": head_sha,
            "scope_hash": scope_hash,
            "current_gate": current_gate,
            "gate_status": "PASS",
        },
        scope_identity={
            "task_id": task_id,
            "repository": repository,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "scope_hash": scope_hash,
            "authorized_actions": allowed_actions,
            "excluded_actions": excluded_actions,
            "risk_class": risk_class,
        },
        gate_policy={"action_map": ACTION_TO_MINIMUM_GATE},
        risk_class=risk_class,
        production_scope_applicable=False,
        manual_g5_action=False,
        event_id_or_idempotency_key=event_id,
        evaluated_at=evaluated_at,
        envelope_expires_at=envelope_expires_at,
    )
    allowed = decision.get("decision") not in {"BLOCK", "NOT_APPLICABLE"}
    return {
        "allowed": allowed,
        "reason_code": str(decision.get("primary_reason_code", "AUTHORITY_BLOCKED")),
    }


class PlanBoundRuntimeExecutor:
    """Execute a single RuntimePlan step under strict plan-bound constraints.

    The executor NEVER invents route, next node, authority, plan revision, or
    completion. Every semantic action must be declared by the plan; every
    outcome must be declared by the plan's edge table.
    """

    def __init__(self, plan: Mapping[str, Any], authority: Mapping[str, Any] | None) -> None:
        if not isinstance(plan, Mapping):
            raise PlanBoundRuntimeError("plan must be a mapping")
        self._plan = dict(plan)
        self._authority = dict(authority) if authority else None

    def execute_step(
        self,
        step_id: str,
        payload: Mapping[str, Any],
        authority: Mapping[str, Any] | None,
        *,
        expected_plan_digest: str | None = None,
        requested_action: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        # 1. RuntimePlan reference must exist.
        runtime_plan_ref = self._plan.get("runtime_plan_ref")
        if not isinstance(runtime_plan_ref, str) or not runtime_plan_ref:
            raise PlanBoundRuntimeError("runtime_plan_ref missing from plan")

        # 2. Plan digest must match expected (anti-stale).
        # M4: compare against the runtime_plan_digest field, not `revision`.
        if expected_plan_digest is not None:
            live_digest = self._plan.get("runtime_plan_digest")
            if live_digest is None:
                raise PlanBoundRuntimeError("plan has no runtime_plan_digest field")
            if live_digest != expected_plan_digest:
                raise PlanBoundRuntimeError("plan digest mismatch: expected does not match live digest")

        # 3. Step must be declared.
        steps = self._plan.get("steps")
        if not isinstance(steps, Mapping) or step_id not in steps:
            raise PlanBoundRuntimeError(f"step {step_id!r} not declared in plan")

        step_raw = steps[step_id]
        if not isinstance(step_raw, Mapping):
            raise PlanBoundRuntimeError(f"step {step_id!r} must be a mapping")

        # 4. Requested action must be declared and in allowed_actions.
        # M4: fail-closed semantics:
        #   - None/missing requested_action: tolerated ONLY for read-only steps
        #     (effectful steps require an explicit requested_action for authority
        #     revalidation).
        #   - Empty requested_action: always rejected (caller-supplied but
        #     semantically blank — cannot reach authority validation).
        #   - Supplied requested_action (any non-empty value): MUST be
        #     normalized and validated against step.allowed_actions for EVERY
        #     step, including read-only steps. A read-only step with
        #     requested_action="write" is a plan-allowlist violation regardless
        #     of what the authority envelope says.
        allowed = tuple(_normalize_action(a) for a in step_raw.get("allowed_actions", ()))
        is_read_only = set(allowed) == {"read"} or step_raw.get("read_only") is True

        if requested_action is None:
            if not is_read_only:
                raise PlanBoundRuntimeError(
                    f"requested_action missing in effectful plan step {step_id!r}: "
                    "authority revalidation cannot proceed"
                )
        elif not requested_action or not requested_action.strip():
            raise PlanBoundRuntimeError(
                f"requested_action empty in plan step {step_id!r}: "
                "plan-allowlist validation cannot proceed"
            )
        else:
            norm_requested = _normalize_action(requested_action)
            if norm_requested not in allowed:
                raise PlanBoundRuntimeError(
                    f"requested action {requested_action!r} undeclared in plan step {step_id!r}"
                )

        # 5. Executor must NOT self-claim authority.
        if isinstance(authority, Mapping) and authority.get("authority_granted") is True:
            raise PlanBoundRuntimeError("executor must not claim authority_granted=True")

        # 6. Reject later-gate authority escalation.
        if isinstance(authority, Mapping) and authority.get("later_gate_authority") is True:
            raise PlanBoundRuntimeError(
                "later-gate authority escalation rejected: executor cannot grant future gate authority"
            )

        # 7. Outcome must be declared in step edges.
        edges = step_raw.get("edges") or {}
        if outcome is not None:
            if outcome not in edges:
                raise PlanBoundRuntimeError(
                    f"outcome {outcome!r} not declared in plan step {step_id!r} edges"
                )

        # 8. Authority revalidation — M4: invoke the canonical GWC authority
        # boundary check. `authority_revalidated=True` ONLY when the boundary
        # check confirms the envelope is valid and the action is in scope
        # (decision is not a hard BLOCK). Absent authority + effectful action
        # still fails closed.
        authority_revalidated = False
        if isinstance(authority, Mapping) and authority.get("authority_id"):
            verdict = _revalidate_authority(authority, requested_action, runtime_plan_ref, step_id)
            if verdict["allowed"]:
                authority_revalidated = True
            else:
                raise PlanBoundRuntimeError(
                    "authority revalidation failed: " + verdict["reason_code"]
                )
        elif requested_action and requested_action != "read":
            raise PlanBoundRuntimeError(
                f"effectful action {requested_action!r} requires authority revalidation"
            )

        # 9. Build evidence with exact readback.
        evidence = {
            "readback_exact": {
                "runtime_plan_ref": runtime_plan_ref,
                "step_id": step_id,
                "requested_action": requested_action,
                "outcome": outcome,
                "authority_id": authority.get("authority_id") if isinstance(authority, Mapping) else None,
            }
        }

        return {
            "runtime_plan_ref": runtime_plan_ref,
            "step_id": step_id,
            "node_instruction_ref": step_raw.get("node_instruction_ref", ""),
            "authority_revalidated": authority_revalidated,
            "evidence": evidence,
        }
