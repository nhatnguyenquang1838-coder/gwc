"""Native Universal Runtime v2 continuation facade.

The durable RuntimePlan and RunState are the sole runtime cursor. This module
contains no mailbox/history input and never treats legacy WAIT/HITL as authority.
Transport projection lives in ``universal_runtime_transport``.
"""
from __future__ import annotations

from typing import Any, Mapping

from .universal_run_controller import UniversalController


def continue_from_native_state(
    *,
    profile: Mapping[str, Any],
    runtime_plan: Mapping[str, Any],
    run_state: Mapping[str, Any],
    node_allocation: Mapping[str, Any],
    executor_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recover the controller from native state and make one transport-free decision."""
    controller = UniversalController(
        profile=profile,
        runtime_plan=runtime_plan,
        run_state=run_state,
        node_allocation=node_allocation,
    )
    if executor_receipt is not None:
        return controller.consume_executor_receipt(executor_receipt)
    assignment = controller.assign_current_action()
    owner = assignment.get("actor")
    if owner == "CONTROLLER":
        return {
            "runtime_epoch": profile["runtime_epoch"],
            "run_id": run_state["run_id"],
            "sequence": run_state["sequence"],
            "active_gate": run_state["active_gate"],
            "next_owner": "CONTROLLER",
            "typed_next": assignment["typed_next"],
            "assignment": assignment,
            "mailbox_required": False,
            "authority_granted": False,
            "executed_effects": [],
        }
    if owner != "EXECUTOR":
        raise ValueError("UNIVERSAL_ASSIGNMENT_ACTOR_INVALID")
    return {
        "runtime_epoch": profile["runtime_epoch"],
        "run_id": run_state["run_id"],
        "sequence": run_state["sequence"],
        "active_gate": run_state["active_gate"],
        "next_owner": "EXECUTOR",
        "typed_next": "EXECUTE_UNIVERSAL_ACTION",
        "assignment": assignment,
        "mailbox_required": False,
        "authority_granted": False,
        "executed_effects": [],
    }


def recover_from_native_checkpoint(
    *, profile: Mapping[str, Any], checkpoint: Mapping[str, Any], node_allocation: Mapping[str, Any]
) -> UniversalController:
    """Reconstruct a fresh Controller solely from durable plan and RunState.

    Accepts both shapes: the canonical durable checkpoint document written by
    ``universal_run_persistence.make_checkpoint_document`` (top-level
    ``runtime_plan``) and the historical/projection shape that names it
    ``plan``. A mailbox-only projection, or a document missing either the plan
    or the RunState, still fails closed.
    """
    if not isinstance(checkpoint, Mapping):
        raise ValueError("NATIVE_CHECKPOINT_REQUIRED")
    plan = checkpoint.get("plan")
    if not isinstance(plan, Mapping):
        plan = checkpoint.get("runtime_plan")
    run_state = checkpoint.get("run_state")
    if not isinstance(plan, Mapping) or not isinstance(run_state, Mapping):
        raise ValueError("NATIVE_CHECKPOINT_BINDING_INVALID")
    return UniversalController(
        profile=profile,
        runtime_plan=plan,
        run_state=run_state,
        node_allocation=node_allocation,
    )


__all__ = ["continue_from_native_state", "recover_from_native_checkpoint"]
