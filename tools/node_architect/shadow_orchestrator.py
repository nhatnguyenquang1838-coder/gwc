#!/usr/bin/env python3
"""Node Architect shadow orchestrator.

Consumes an activation contract plus an immutable gate event, selects a
scenario route, invokes only shadow adapters, and returns advisory evidence.
"""
from __future__ import annotations

from typing import Any

from tools.node_architect.gate_node_routes import nodes_for_event, select_route_pack
from tools.node_architect.shadow_adapters import build_adapter_registry, execute_shadow_node


def _activation_error(activation: dict[str, Any], event: dict[str, Any], observed_revision: str) -> tuple[str, str] | None:
    if activation.get("mode") != "shadow_readonly" or activation.get("authority") != "none":
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_ACTIVATION_INVALID"
    if activation.get("enabled") is not True:
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_NOT_ENABLED"
    if activation.get("kill_switch_engaged") is True:
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_KILL_SWITCH_ENGAGED"
    if activation.get("exact_revision_binding") is not True:
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_REVISION_BINDING_REQUIRED"
    if event.get("exact_revision") != observed_revision:
        return "SHADOW_DISABLED_FAIL_CLOSED", "SHADOW_REVISION_DRIFT"
    return None


def run_shadow_event(event: dict[str, Any], registry: dict[str, Any], activation: dict[str, Any], *, observed_revision: str) -> dict[str, Any]:
    blocked = _activation_error(activation, event, observed_revision)
    if blocked:
        status, reason = blocked
        return {"status": status, "reason_code": reason, "results": [], "authoritative_effect": "NONE", "decision_authority": False}

    scenario = str(event.get("scenario", ""))
    route_id = select_route_pack(scenario)
    if route_id is None:
        return {"status": "SHADOW_NO_APPLICABLE_ROUTE", "reason_code": "SHADOW_SCENARIO_UNMAPPED", "route_pack": None, "results": [], "authoritative_effect": "NONE", "decision_authority": False}

    selected_ids = nodes_for_event(registry, gate=str(event.get("gate", "")), scenario=scenario)
    adapter_registry = build_adapter_registry(registry)
    by_id = {node.get("id"): node for node in registry.get("nodes", []) if isinstance(node, dict)}
    results: list[dict[str, Any]] = []
    for node_id in selected_ids:
        if node_id not in adapter_registry:
            results.append({"node_id": node_id, "applicability": "BLOCKED", "outcome": "ADAPTER_UNAVAILABLE", "reason_code": "SHADOW_ADAPTER_UNAVAILABLE", "executed_effects": [], "proposed_effects": [], "authority_granted": False})
            continue
        results.append(execute_shadow_node(by_id[node_id], event, dict(event.get("input_payload") or {})))

    return {
        "status": "SHADOW_EXECUTED",
        "reason_code": "SHADOW_ROUTE_EXECUTED",
        "route_pack": route_id,
        "selected_node_count": len(selected_ids),
        "results": results,
        "authoritative_effect": "NONE",
        "automatic_gate_advance": False,
        "decision_authority": False,
    }
