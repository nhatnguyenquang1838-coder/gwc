"""Resolve one Workflow step under a bound Policy without hidden controller logic."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from tools.node_architect.compile_flow_policy_decision import compile_flow_policy_decision
from tools.node_architect.evaluate_gate_applicability import evaluate_gate_applicability
from tools.node_architect.validate_flow_policy_runtime import validate_flow_policy_runtime
from tools.node_architect.validate_flow_profile_workflow import canonical_edge_kind


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _participant(flow_profile: Mapping[str, Any], node: str) -> Mapping[str, Any] | None:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return None
    matches = [item for item in workflow.get("participants", []) if isinstance(item, Mapping) and item.get("participant") == node]
    return matches[0] if len(matches) == 1 else None


def _participant_gate(flow_profile: Mapping[str, Any], node: str) -> str | None:
    item = _participant(flow_profile, node)
    if item is None:
        return None
    gate = item.get("gate")
    return str(gate) if gate else None


def _terminal_outcome(flow_profile: Mapping[str, Any], node: str) -> str | None:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return None
    matches = [item for item in workflow.get("terminal_nodes", []) if isinstance(item, Mapping) and item.get("node") == node]
    if len(matches) != 1:
        return None
    return str(matches[0].get("outcome") or "TERMINAL")


def _edge_selected(edge: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    if edge.get("runtime_executable") is not True:
        return False
    kind = canonical_edge_kind(str(edge.get("kind") or ""))
    if kind == "continue":
        return True
    if kind == "conditional":
        conditions = context.get("conditions")
        condition_id = str(edge.get("condition_id") or "")
        return isinstance(conditions, Mapping) and conditions.get(condition_id) is True
    if kind in {"retry", "compensate", "blocked", "human_required", "terminal"}:
        return context.get("transition_kind") == kind
    return False


def _next_step(flow_profile: Mapping[str, Any], current_node: str, context: Mapping[str, Any]) -> tuple[list[str], str | None, list[str]]:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return [], None, ["WORKFLOW_CONTRACT_MISSING"]
    outgoing = [edge for edge in workflow.get("edges", []) if isinstance(edge, Mapping) and edge.get("source") == current_node and _edge_selected(edge, context)]
    terminal = _terminal_outcome(flow_profile, current_node)
    if terminal is not None:
        if outgoing:
            return [], None, ["WORKFLOW_TERMINAL_HAS_ROUTE"]
        return [], terminal, []
    if not outgoing:
        return [], None, ["WORKFLOW_NEXT_ROUTE_MISSING"]
    targets = list(dict.fromkeys(str(edge.get("target")) for edge in outgoing if edge.get("target")))
    if len(targets) != 1:
        return [], None, ["WORKFLOW_NEXT_ROUTE_AMBIGUOUS"]
    return targets, None, []


def _blocked(*, reasons: list[str], activation: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_type": "flow-policy-runtime-resolution",
        "outcome": "BLOCKED",
        "reason_codes": list(dict.fromkeys(reasons)),
        "activation_decision": dict(activation),
        "workflow_policy_decision": None,
    }
    payload["decision_digest"] = _digest(payload)
    return payload


def resolve_flow_policy_runtime(
    *, runtime_profile: Mapping[str, Any], flow_profile: Mapping[str, Any],
    policy_registry: Mapping[str, Any], route_profile: Mapping[str, Any],
    current_node: str, current_gate: str, context: Mapping[str, Any], root: Path,
) -> dict[str, Any]:
    """Return a deterministic Flow+Policy resolution artifact; execute nothing."""
    activation = validate_flow_policy_runtime(
        runtime_profile=runtime_profile, flow_profile=flow_profile,
        policy_registry=policy_registry, route_profile=route_profile, root=root,
    )
    if activation.get("outcome") != "ACTIVATABLE":
        return _blocked(reasons=list(activation.get("reason_codes", ["RUNTIME_NOT_ACTIVATABLE"])), activation=activation)

    participant = _participant(flow_profile, current_node)
    if participant is None:
        return _blocked(reasons=["WORKFLOW_PARTICIPANT_UNBOUND"], activation=activation)
    bound_gate = participant.get("gate")
    if bound_gate is not None and str(bound_gate) != current_gate:
        return _blocked(reasons=["WORKFLOW_GATE_CONTEXT_MISMATCH"], activation=activation)

    applicability = evaluate_gate_applicability(
        flow_profile=flow_profile, policy_registry=policy_registry,
        gate=current_gate, context=dict(context),
    )
    next_nodes, terminal, route_reasons = _next_step(flow_profile, current_node, context)
    target_gate = _participant_gate(flow_profile, next_nodes[0]) if len(next_nodes) == 1 else None
    if target_gate == current_gate:
        target_gate = None

    compiled = compile_flow_policy_decision(
        flow_profile=flow_profile, policy_registry=policy_registry,
        current_node=current_node, current_gate=current_gate,
        applicability_decision=applicability, context=context,
        next_nodes=next_nodes, next_gate=target_gate,
        terminal_disposition=terminal,
    )
    if route_reasons and compiled.get("outcome") != "BLOCKED":
        compiled = dict(compiled)
        compiled["outcome"] = "BLOCKED"
        compiled["applicability"] = "BLOCKED"
        compiled["next_nodes"] = []
        compiled["next_gate"] = None
        compiled["terminal_disposition"] = None
        compiled["reason_codes"] = list(dict.fromkeys(route_reasons + list(compiled.get("reason_codes", []))))
        compiled["decision_digest"] = _digest({k: v for k, v in compiled.items() if k != "decision_digest"})

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_type": "flow-policy-runtime-resolution",
        "outcome": compiled.get("outcome", "BLOCKED"),
        "reason_codes": list(compiled.get("reason_codes", ["FLOW_POLICY_RUNTIME_BLOCKED"])),
        "activation_decision": activation,
        "workflow_policy_decision": compiled,
    }
    payload["decision_digest"] = _digest(payload)
    return payload


__all__ = ["resolve_flow_policy_runtime"]
