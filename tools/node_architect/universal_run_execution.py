"""Universal Run v2 -> Node Architect execution adapter.

This adapter is the bounded execution seam between an immutable RuntimePlan /
RunState / NodeAllocation and the production Agent Host. It derives the active
Q0 gate/action from native RunState, dispatches through canonical route and
instruction validation, records NodeEvidenceLedger evidence, then delegates gate
completion/typed continuation to the shared Universal controller. It grants no
repository, merge, deployment, production-data, or other effect authority.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .agent_runtime_entrypoint import run_agent_runtime_loop
from .live_runtime_bridge import CANONICAL_SOURCE_KIND
from .node_evidence_ledger import NodeEvidenceLedger, digest_payload, emit_complete_node_evidence
from .q0_qualification import Q0_ACTIONS, Q0_RUNTIME_EPOCH, Q0_WORKFLOW_MODE, q0_qualification_profile
from .resolve_gate_node_route import resolve_gate_node_route
from .universal_run_continuation import create_or_recover_runtime_plan, reconcile_controller_continuation
from .universal_run_node import verify_parent_composition
from .universal_run_topology import validate_node_allocation

UNIVERSAL_RUN_NEW_RUNTIME = "UNIVERSAL_RUN_NEW_RUNTIME"
_PLAN_FIELDS = {
    "run_id", "revision", "target_contract_ref", "node_allocations",
    "schema_id", "runtime_epoch", "digest",
}


class UniversalRunExecutionError(ValueError):
    """Fail-closed Universal Run execution binding error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise UniversalRunExecutionError(code, detail)


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _validate_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    _require(isinstance(plan, Mapping), "RUNTIME_PLAN_REQUIRED")
    _require(set(plan) == _PLAN_FIELDS, "RUNTIME_PLAN_FIELDS_INVALID")
    revision = plan.get("revision")
    allocations = plan.get("node_allocations")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise UniversalRunExecutionError("RUNTIME_PLAN_INVALID", "revision")
    if not isinstance(allocations, (list, tuple)) or not all(isinstance(item, str) for item in allocations):
        raise UniversalRunExecutionError("RUNTIME_PLAN_INVALID", "node_allocations")
    try:
        expected = create_or_recover_runtime_plan(
            run_id=str(plan.get("run_id", "")),
            revision=revision,
            target_contract_ref=str(plan.get("target_contract_ref", "")),
            node_allocations=list(allocations),
        )
    except Exception as exc:
        raise UniversalRunExecutionError("RUNTIME_PLAN_INVALID", f"{type(exc).__name__}: {exc}") from exc
    _require(dict(plan) == expected, "RUNTIME_PLAN_DIGEST_INVALID")
    _require(plan.get("runtime_epoch") == Q0_RUNTIME_EPOCH, "RUNTIME_PLAN_EPOCH_MISMATCH")
    return dict(plan)


def _validate_state_and_allocation(
    *, runtime_plan: Mapping[str, Any], run_state: Mapping[str, Any], node_allocation: Mapping[str, Any]
) -> tuple[str, str, int]:
    if not isinstance(run_state, Mapping):
        raise UniversalRunExecutionError("RUN_STATE_REQUIRED")
    run_id = str(runtime_plan.get("run_id", ""))
    if not run_id or run_state.get("schema_id") != "gwc.universal-run.run-state":
        raise UniversalRunExecutionError("RUN_STATE_INVALID")
    _require(run_state.get("run_id") == run_id, "RUN_STATE_PLAN_RUN_MISMATCH")
    _require(run_state.get("runtime_epoch") == Q0_RUNTIME_EPOCH, "RUN_STATE_EPOCH_MISMATCH")
    gate = str(run_state.get("active_gate", ""))
    _require(gate in Q0_ACTIONS, "UNIVERSAL_ACTIVE_GATE_INVALID", gate)
    sequence = run_state.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise UniversalRunExecutionError("RUN_STATE_SEQUENCE_INVALID")

    gate_evidence = run_state.get("gate_evidence")
    if not isinstance(gate_evidence, Mapping):
        raise UniversalRunExecutionError("RUN_STATE_GATE_EVIDENCE_INVALID")
    consumed_receipts = run_state.get("consumed_receipts", [])
    if not isinstance(consumed_receipts, list) or not all(isinstance(item, str) for item in consumed_receipts):
        raise UniversalRunExecutionError("RUN_STATE_CONSUMED_RECEIPTS_INVALID")

    execution_refs_raw = run_state.get("execution_refs")
    if not isinstance(execution_refs_raw, Mapping):
        raise UniversalRunExecutionError("RUN_STATE_PLAN_BINDING_REQUIRED")
    execution_refs = dict(execution_refs_raw)
    _require(bool(execution_refs.get("runtime_plan_ref")), "RUN_STATE_PLAN_REF_REQUIRED")
    _require(execution_refs.get("runtime_plan_digest") == runtime_plan.get("digest"), "RUN_STATE_PLAN_DIGEST_MISMATCH")
    _require(bool(execution_refs.get("cursor_ref")), "RUN_STATE_CURSOR_REF_REQUIRED")

    if not isinstance(node_allocation, Mapping):
        raise UniversalRunExecutionError("NODE_ALLOCATION_REQUIRED")
    try:
        validate_node_allocation(node_allocation)
    except Exception as exc:
        raise UniversalRunExecutionError("NODE_ALLOCATION_INVALID", f"{type(exc).__name__}: {exc}") from exc
    _require(node_allocation.get("run_id") == run_id, "NODE_ALLOCATION_RUN_MISMATCH")
    allocation_id = str(node_allocation.get("node_allocation_id", ""))
    _require(allocation_id in runtime_plan.get("node_allocations", []), "NODE_ALLOCATION_NOT_BOUND_TO_PLAN")
    provenance_raw = node_allocation.get("provenance")
    if not isinstance(provenance_raw, Mapping):
        raise UniversalRunExecutionError("NODE_ALLOCATION_NODE_BINDING_INVALID")
    source_refs = provenance_raw.get("source_refs")
    if not isinstance(source_refs, list) or len(source_refs) != 1 or not isinstance(source_refs[0], str) or not source_refs[0]:
        raise UniversalRunExecutionError("NODE_ALLOCATION_NODE_BINDING_INVALID")
    return run_id, source_refs[0], sequence


def _host_event(
    *, runtime_plan: Mapping[str, Any], run_state: Mapping[str, Any], node_allocation: Mapping[str, Any],
    route_id: str, node_id: str, event_kwargs: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    gate = str(run_state["active_gate"])
    action = Q0_ACTIONS[gate]
    run_id = str(run_state["run_id"])
    _require(route_id == UNIVERSAL_RUN_NEW_RUNTIME, "UNIVERSAL_ROUTE_ID_UNSUPPORTED", route_id)
    if not isinstance(event_kwargs, Mapping):
        raise UniversalRunExecutionError("AGENT_HOST_EVENT_REQUIRED")
    event: dict[str, Any] = dict(event_kwargs)
    for key, expected in (("run_id", run_id), ("gate", gate), ("requested_action", action),
                          ("workflow_mode", Q0_WORKFLOW_MODE)):
        if key in event:
            _require(event[key] == expected, "AGENT_HOST_EVENT_BINDING_MISMATCH", key)
        event[key] = expected
    event_id = str(event.get("event_id", ""))
    _require(bool(event_id.strip()), "AGENT_HOST_EVENT_ID_REQUIRED")
    occurrence = event.pop("occurred_at", None) or run_state.get("occurred_at")
    _require(isinstance(occurrence, str) and bool(occurrence), "NODE_EVIDENCE_TIMESTAMP_REQUIRED")

    canonical_state_raw = event.get("canonical_state")
    if not isinstance(canonical_state_raw, Mapping):
        raise UniversalRunExecutionError("CANONICAL_AGENT_STATE_REQUIRED")
    canonical_state: dict[str, Any] = dict(canonical_state_raw)
    _require(canonical_state.get("task_id") == "SCRUM-781", "Q0_TASK_BINDING_MISMATCH")
    _require(canonical_state.get("source_kind") == CANONICAL_SOURCE_KIND, "CANONICAL_AGENT_STATE_SOURCE_REQUIRED")
    canonical_state["runtime_epoch"] = Q0_RUNTIME_EPOCH
    event["canonical_state"] = canonical_state

    profile = q0_qualification_profile()
    payload_raw = event.get("input_payload")
    if not isinstance(payload_raw, Mapping):
        raise UniversalRunExecutionError("AGENT_HOST_INPUT_PAYLOAD_REQUIRED")
    payload: dict[str, Any] = dict(payload_raw)
    if "q0_profile" in payload:
        _require(payload["q0_profile"] == profile, "Q0_PROFILE_BINDING_MISMATCH")
    effect_class = str(payload.get("effect_class", "read_only"))
    _require(effect_class == "read_only", "Q0_ADAPTER_READ_ONLY_REQUIRED", effect_class)
    payload.update({
        "run_id": run_id,
        "active_gate": gate,
        "gate_evidence": copy.deepcopy(dict(run_state.get("gate_evidence") or {})),
        "workflow_mode": Q0_WORKFLOW_MODE,
        "runtime_epoch": Q0_RUNTIME_EPOCH,
        "q0_profile": profile,
        "runtime_plan_digest": runtime_plan["digest"],
        "node_allocation_id": node_allocation["node_allocation_id"],
        "node_id": node_id,
        "route_id": route_id,
        "effect_class": "read_only",
    })
    event["input_payload"] = payload
    event["scenario"] = str(event.get("scenario") or "universal_run_node_execution")
    route_context_raw = event.get("route_context") or {}
    if not isinstance(route_context_raw, Mapping):
        raise UniversalRunExecutionError("AGENT_ROUTE_CONTEXT_INVALID")
    route_context: dict[str, Any] = dict(route_context_raw)
    route_context.update({
        "task_id": "SCRUM-781",
        "run_id": run_id,
        "gate": gate,
        "requested_action": action,
        "workflow_mode": Q0_WORKFLOW_MODE,
        "runtime_epoch": Q0_RUNTIME_EPOCH,
        "q0_profile": profile,
        "effect_class": "read_only",
        "route_id": route_id,
        "node_allocation_id": node_allocation["node_allocation_id"],
        "node_id": node_id,
        "runtime_plan_digest": runtime_plan["digest"],
        "available_connectors": list(route_context.get("available_connectors", ["GitHub.compare_commits"])),
        "context": dict(route_context.get("context") or {}),
    })
    event["route_context"] = route_context
    event.setdefault("route_resolver", resolve_gate_node_route)
    return event, occurrence


def execute_universal_run_node(
    *,
    route_id: str,
    runtime_plan: Mapping[str, Any],
    run_state: Mapping[str, Any],
    node_allocation: Mapping[str, Any],
    event_kwargs: Mapping[str, Any],
    evidence_root: Path | str,
    parent_composition: Mapping[str, Any] | None = None,
    max_iterations: int = 32,
) -> dict[str, Any]:
    """Execute the active Universal Run node through Agent Host and record evidence.

    The run cursor is never mutated here. A successor is a typed continuation
    candidate returned by the shared controller; callers persist it only through
    the canonical RunStateStore contract.
    """
    plan = _validate_plan(runtime_plan)
    run_id, node_id, sequence = _validate_state_and_allocation(
        runtime_plan=plan, run_state=run_state, node_allocation=node_allocation
    )
    event, occurred_at = _host_event(
        runtime_plan=plan, run_state=run_state, node_allocation=node_allocation,
        route_id=route_id, node_id=node_id, event_kwargs=event_kwargs,
    )
    _require(isinstance(max_iterations, int) and max_iterations >= 1, "AGENT_RUNTIME_ITERATION_LIMIT_INVALID")
    canonical_state = event["canonical_state"]
    ledger = NodeEvidenceLedger(
        root=Path(evidence_root),
        task_id="SCRUM-781",
        run_id=run_id,
        node_id=node_id,
        repository=str(canonical_state.get("repository", "")),
        branch=str(canonical_state.get("branch", "")),
        base_sha=str(canonical_state.get("base_sha", "")),
        head_sha=str(canonical_state.get("head_sha", "")),
        scope_hash=str(canonical_state.get("scope_hash", "")),
        idempotency_key=str(event["event_id"]),
        occurred_at=occurred_at,
    )
    summary = ledger.summary()
    artifact_paths = {
        name: str(ledger.node_root / f"{name}.json")
        for name in ("node-start", "node-decision", "node-result", "node-readback", "checkpoint", "next-route-decision")
    }

    host_result = run_agent_runtime_loop(event, max_iterations=max_iterations)
    host_status = str(host_result.get("status", ""))
    if host_result.get("node_id"):
        _require(host_result["node_id"] == node_id, "AGENT_HOST_NODE_ALLOCATION_MISMATCH")
    _require(host_result.get("authority_granted", False) is False, "UNIVERSAL_EXECUTION_AUTHORITY_BOUNDARY_VIOLATION")
    _require(list(host_result.get("executed_effects", []) or []) == [], "UNIVERSAL_EXECUTION_EFFECT_BOUNDARY_VIOLATION")

    receipt_body = {
        "schema_id": "gwc.universal-run.execution-receipt",
        "artifact_type": "universal-run-execution-receipt",
        "run_id": run_id,
        "runtime_epoch": Q0_RUNTIME_EPOCH,
        "route_id": route_id,
        "runtime_plan_digest": plan["digest"],
        "node_allocation_id": node_allocation["node_allocation_id"],
        "node_id": node_id,
        "gate": run_state["active_gate"],
        "sequence": sequence,
        "event_id": event["event_id"],
        "host_status": host_status,
        "host_result_digest": digest_payload(host_result),
        "evidence_refs": artifact_paths,
        "authority_granted": False,
        "executed_effects": [],
    }
    receipt = {**receipt_body, "receipt_digest": _digest(receipt_body)}

    continuation: dict[str, Any] | None = None
    if host_status == "SEMANTIC_NODE_COMPLETE":
        continued_state = copy.deepcopy(dict(run_state))
        gate_evidence = dict(continued_state.get("gate_evidence") or {})
        if run_state["active_gate"] == "UR.G2":
            gate_evidence["EXECUTION_RECEIPT"] = receipt
        continued_state["gate_evidence"] = gate_evidence
        continuation = reconcile_controller_continuation(
            runtime_epoch=Q0_RUNTIME_EPOCH,
            plan=plan,
            run_state=continued_state,
            history_controller=dict(event.get("history_controller") or {}),
            executor_receipts={receipt["receipt_digest"]: receipt} if run_state["active_gate"] == "UR.G2" else {},
            consumer_cursor={"consumed_receipts": list(run_state.get("consumed_receipts") or [])},
            transport_profile=str(event.get("transport_profile") or "local_agent"),
            actor="EXECUTOR",
        )

    parent_result = None
    if parent_composition is not None:
        _require(isinstance(parent_composition, Mapping), "PARENT_COMPOSITION_INPUT_INVALID")
        try:
            parent_result = verify_parent_composition(
                parent_run_id=str(parent_composition.get("parent_run_id", "")),
                acceptance_contract_ref=str(parent_composition.get("acceptance_contract_ref", "")),
                required_child_run_ids=list(parent_composition.get("required_child_run_ids") or []),
                child_results=list(parent_composition.get("child_results") or []),
            )
        except Exception as exc:
            raise UniversalRunExecutionError("PARENT_COMPOSITION_VERIFICATION_ERROR", f"{type(exc).__name__}: {exc}") from exc

    node_next_route = dict(host_result.get("next_route") or {})
    typed_next = str((continuation or {}).get("typed_next") or "UNIVERSAL_NODE_EXECUTION_BLOCKED")
    run_state_digest = _digest(dict(run_state))
    evidence = {
        "node-start": {
            "event_id": event["event_id"], "route_id": route_id,
            "runtime_plan_digest": plan["digest"],
            "node_allocation_id": node_allocation["node_allocation_id"],
            "gate": run_state["active_gate"], "sequence": sequence,
        },
        "node-decision": {
            "host_status": host_status,
            "reason_code": str(host_result.get("reason_code") or ""),
            "route_decision": dict(host_result.get("route_decision") or {}),
            "execution_receipt_digest": receipt["receipt_digest"],
        },
        "node-result": {
            "host_result": host_result,
            "execution_receipt": receipt,
            "parent_composition": parent_result,
        },
        "node-readback": {
            "readback": dict(host_result.get("readback") or {}),
            "authority_granted": host_result.get("authority_granted", False),
            "executed_effects": list(host_result.get("executed_effects", []) or []),
        },
        "checkpoint": {
            "run_state_digest": run_state_digest,
            "runtime_plan_digest": plan["digest"],
            "sequence": sequence,
            "active_gate": run_state["active_gate"],
            "continuation_state_digest": (continuation or {}).get("successor_run_state", {}).get("state_digest"),
        },
        "next-route-decision": {
            "node_next_route": node_next_route,
            "typed_next": typed_next,
            "successor_run_state": (continuation or {}).get("successor_run_state"),
            "gate_advanced": bool((continuation or {}).get("gate_advanced", False)),
        },
    }
    ledger_result = emit_complete_node_evidence(ledger=ledger, evidence=evidence)
    return {
        "status": "UNIVERSAL_RUN_NODE_COMPLETE" if host_status == "SEMANTIC_NODE_COMPLETE" else "UNIVERSAL_RUN_NODE_BLOCKED",
        "run_id": run_id,
        "route_id": route_id,
        "runtime_plan_digest": plan["digest"],
        "node_allocation_id": node_allocation["node_allocation_id"],
        "node_id": node_id,
        "host_result": host_result,
        "execution_receipt": receipt,
        "evidence_ledger": ledger_result,
        "node_next_route": node_next_route,
        "controller_continuation": continuation,
        "typed_next": typed_next,
        "parent_composition": parent_result,
        "authority_granted": False,
        "executed_effects": [],
        "summary": summary,
    }


__all__ = [
    "UNIVERSAL_RUN_NEW_RUNTIME",
    "UniversalRunExecutionError",
    "execute_universal_run_node",
]
