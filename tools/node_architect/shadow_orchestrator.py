#!/usr/bin/env python3
"""Node Architect shadow orchestrator.

Default runtime never treats scenario/family matching as semantic execution.
It consumes one fail-closed canonical route decision, then invokes only selected
nodes through read-only shadow adapters. Historical family-only replay remains
available only behind ``compatibility_replay=True`` and is explicitly marked
non-semantic so it cannot qualify a node for semantic/runtime promotion.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from tools.node_architect.canonical_shadow_route import resolve_shadow_route
from tools.node_architect.gate_node_routes import nodes_for_event, select_route_pack
from tools.node_architect.semantic_source_resolver import resolve_semantic_source
from tools.node_architect.shadow_adapters import build_adapter_registry, execute_shadow_node

RouteResolver = Callable[..., Mapping[str, Any]]


def _base_terminal(status: str, reason: str, *, route_pack: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "reason_code": reason,
        "route_pack": route_pack,
        "selected_node_count": 0,
        "results": [],
        "rejections": [],
        "semantic_execution": False,
        "authoritative_effect": "NONE",
        "authority_granted": False,
        "automatic_gate_advance": False,
        "decision_authority": False,
    }


def _activation_runtime_error(activation: Mapping[str, Any]) -> tuple[str, str] | None:
    if activation.get("enabled") is not True:
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_NOT_ENABLED"
    if activation.get("kill_switch_engaged") is True:
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_KILL_SWITCH_ENGAGED"
    if activation.get("mode") != "shadow_readonly" or activation.get("authority") != "none":
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_ACTIVATION_INVALID"
    if activation.get("output_effect") != "observe_only":
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_ACTIVATION_INVALID"
    if activation.get("decision_authority") is not False or activation.get("automatic_gate_advance") is not False:
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_ACTIVATION_INVALID"
    if activation.get("fail_closed") is not True or activation.get("exact_revision_binding") is not True:
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_ACTIVATION_INVALID"
    if activation.get("canonical_population") != "canonical_81":
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_ACTIVATION_INVALID"
    return None


def _terminal_from_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    output = _base_terminal(
        str(decision.get("status") or "SHADOW_DISABLED_FAIL_CLOSED"),
        str(decision.get("reason_code") or "SHADOW_ROUTE_RESOLUTION_FAILED"),
        route_pack=decision.get("route_pack") if isinstance(decision.get("route_pack"), str) else None,
    )
    output.update({
        "rejections": list(decision.get("rejections", []) or []),
        "profile_revision": decision.get("profile_revision"),
        "graph_revision": decision.get("graph_revision"),
        "node_registry_revision": decision.get("node_registry_revision"),
        "policy_revision": decision.get("policy_revision"),
        "gate_applicability": decision.get("gate_applicability"),
    })
    return output


def _execute_selected(
    *,
    event: Mapping[str, Any],
    registry: Mapping[str, Any],
    selected_ids: list[str],
) -> list[dict[str, Any]]:
    adapter_registry = build_adapter_registry(dict(registry))
    by_id = {
        node.get("id"): node
        for node in registry.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    results: list[dict[str, Any]] = []
    for node_id in selected_ids:
        node = by_id.get(node_id)
        if node is None:
            results.append({
                "node_id": node_id,
                "applicability": "BLOCKED",
                "outcome": "NODE_UNAVAILABLE",
                "reason_code": "SHADOW_SELECTED_NODE_UNAVAILABLE",
                "executed_effects": [],
                "proposed_effects": [],
                "authority_granted": False,
            })
            continue
        if node_id not in adapter_registry:
            results.append({
                "node_id": node_id,
                "applicability": "BLOCKED",
                "outcome": "ADAPTER_UNAVAILABLE",
                "reason_code": "SHADOW_ADAPTER_UNAVAILABLE",
                "executed_effects": [],
                "proposed_effects": [],
                "authority_granted": False,
            })
            continue
        results.append(execute_shadow_node(node, dict(event), dict(event.get("input_payload") or {})))
    return results


def _run_compatibility_replay(
    event: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    scenario = str(event.get("scenario", ""))
    route_id = select_route_pack(scenario)
    if route_id is None:
        return _base_terminal("SHADOW_NO_APPLICABLE_ROUTE", "SHADOW_SCENARIO_UNMAPPED")
    selected_ids = nodes_for_event(dict(registry), gate=str(event.get("gate", "")), scenario=scenario)
    results = _execute_selected(event=event, registry=registry, selected_ids=selected_ids)
    return {
        "status": "SHADOW_ENVELOPE_REPLAYED",
        "reason_code": "SHADOW_COMPATIBILITY_REPLAY_ONLY",
        "route_pack": route_id,
        "selected_node_count": len(selected_ids),
        "results": results,
        "rejections": [],
        "semantic_execution": False,
        "authoritative_effect": "NONE",
        "authority_granted": False,
        "automatic_gate_advance": False,
        "decision_authority": False,
    }


def run_shadow_event(
    event: dict[str, Any],
    registry: dict[str, Any],
    activation: dict[str, Any],
    *,
    observed_revision: str,
    observed_state: Mapping[str, Any] | None = None,
    profile: Mapping[str, Any] | None = None,
    graph_registry: Mapping[str, Any] | None = None,
    root: Path | str = Path("."),
    route_resolver: RouteResolver = resolve_shadow_route,
    source_resolver=resolve_semantic_source,
    policy_registry: Mapping[str, Any] | None = None,
    compatibility_replay: bool = False,
) -> dict[str, Any]:
    """Resolve and execute one immutable shadow event, fail closed by default."""
    activation_error = _activation_runtime_error(activation)
    if activation_error:
        return _base_terminal(*activation_error)

    if event.get("exact_revision") != observed_revision:
        return _base_terminal("SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_REVISION_DRIFT")

    if compatibility_replay:
        return _run_compatibility_replay(event, registry)

    if observed_state is None or profile is None or graph_registry is None:
        return _base_terminal("SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_RUNTIME_CONTEXT_MISSING")

    decision = route_resolver(
        event=event,
        registry=registry,
        activation=activation,
        observed_state=observed_state,
        profile=profile,
        graph_registry=graph_registry,
        root=Path(root),
        source_resolver=source_resolver,
        policy_registry=policy_registry,
    )
    if not isinstance(decision, Mapping):
        return _base_terminal("SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_ROUTE_RESOLVER_INVALID_RESULT")
    if decision.get("status") != "SHADOW_ROUTE_RESOLVED":
        return _terminal_from_decision(decision)

    selected_ids = [str(item) for item in list(decision.get("selected_node_ids", []) or []) if item]
    if not selected_ids:
        return _terminal_from_decision({
            **dict(decision),
            "status": "SHADOW_NO_APPLICABLE_NODES",
            "reason_code": "SHADOW_NO_APPLICABLE_NODES",
        })

    results = _execute_selected(event=event, registry=registry, selected_ids=selected_ids)
    return {
        "status": "SHADOW_EXECUTED",
        "reason_code": "SHADOW_ROUTE_EXECUTED",
        "route_pack": decision.get("route_pack"),
        "selected_node_count": len(selected_ids),
        "results": results,
        "rejections": list(decision.get("rejections", []) or []),
        "profile_revision": decision.get("profile_revision"),
        "graph_revision": decision.get("graph_revision"),
        "node_registry_revision": decision.get("node_registry_revision"),
        "policy_revision": decision.get("policy_revision"),
        "gate_applicability": decision.get("gate_applicability"),
        "semantic_execution": False,
        "authoritative_effect": "NONE",
        "authority_granted": False,
        "automatic_gate_advance": False,
        "decision_authority": False,
    }
