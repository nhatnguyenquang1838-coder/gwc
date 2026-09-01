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
        if expected_plan_digest is not None:
            if self._plan.get("revision") != expected_plan_digest:
                raise PlanBoundRuntimeError("plan digest mismatch: expected does not match live revision")

        # 3. Step must be declared.
        steps = self._plan.get("steps")
        if not isinstance(steps, Mapping) or step_id not in steps:
            raise PlanBoundRuntimeError(f"step {step_id!r} not declared in plan")

        step_raw = steps[step_id]
        if not isinstance(step_raw, Mapping):
            raise PlanBoundRuntimeError(f"step {step_id!r} must be a mapping")

        # 4. Requested action must be in allowed_actions.
        allowed = tuple(_normalize_action(a) for a in step_raw.get("allowed_actions", ()))
        if requested_action is not None:
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

        # 8. Authority revalidation.
        authority_revalidated = False
        if isinstance(authority, Mapping) and authority.get("authority_id"):
            authority_revalidated = True
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
