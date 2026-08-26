#!/usr/bin/env python3
"""Node Architect shadow orchestrator.

The orchestrator no longer treats scenario/family matching as runtime evidence.
It consumes one fail-closed canonical route decision, then invokes only the
selected nodes through read-only shadow adapters. Route resolution owns all
activation, immutable identity, revision, applicability and semantic binding
checks; this layer owns adapter invocation only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from tools.node_architect.canonical_shadow_route import resolve_shadow_route
from tools.node_architect.semantic_source_resolver import resolve_semantic_source
from tools.node_architect.shadow_adapters import build_adapter_registry, execute_shadow_node

RouteResolver = Callable[..., Mapping[str, Any]]


def _terminal_from_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": str(decision.get("status") or "SHADOW_DISABLED_FAIL_CLOSED"),
        "reason_code": str(decision.get("reason_code") or "SHADOW_ROUTE_RESOLUTION_FAILED"),
        "route_pack": decision.get("route_pack"),
        "selected_node_count": 0,
        "results": [],
        "rejections": list(decision.get("rejections", []) or []),
        "profile_revision": decision.get("profile_revision"),
        "graph_revision": decision.get("graph_revision"),
        "node_registry_revision": decision.get("node_registry_revision"),
        "policy_revision": decision.get("policy_revision"),
        "gate_applicability": decision.get("gate_applicability"),
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
) -> dict[str, Any]:
    """Resolve and execute one immutable shadow event, fail closed by default.

    ``observed_revision`` remains an explicit compatibility/readback argument,
    but it is not sufficient runtime identity. The canonical resolver requires
    repository/branch/base/head plus profile/graph/node-registry/policy binding.
    """
    if event.get("exact_revision") != observed_revision:
        return {
            "status": "SHADOW_DISABLED_FAIL_CLOSED",
            "reason_code": "SHADOW_REVISION_DRIFT",
            "route_pack": None,
            "selected_node_count": 0,
            "results": [],
            "rejections": [],
            "authoritative_effect": "NONE",
            "authority_granted": False,
            "automatic_gate_advance": False,
            "decision_authority": False,
        }

    if observed_state is None or profile is None or graph_registry is None:
        return {
            "status": "SHADOW_DISABLED_FAIL_CLOSED",
            "reason_code": "SHADOW_CANONICAL_CONTEXT_MISSING",
            "route_pack": None,
            "selected_node_count": 0,
            "results": [],
            "rejections": [],
            "authoritative_effect": "NONE",
            "authority_granted": False,
            "automatic_gate_advance": False,
            "decision_authority": False,
        }

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
        return {
            "status": "SHADOW_DISABLED_FAIL_CLOSED",
            "reason_code": "SHADOW_ROUTE_RESOLVER_INVALID_RESULT",
            "route_pack": None,
            "selected_node_count": 0,
            "results": [],
            "rejections": [],
            "authoritative_effect": "NONE",
            "authority_granted": False,
            "automatic_gate_advance": False,
            "decision_authority": False,
        }
    if decision.get("status") != "SHADOW_ROUTE_RESOLVED":
        return _terminal_from_decision(decision)

    selected_ids = list(decision.get("selected_node_ids", []) or [])
    if not selected_ids:
        return _terminal_from_decision({
            **dict(decision),
            "status": "SHADOW_NO_APPLICABLE_NODES",
            "reason_code": "SHADOW_NO_APPLICABLE_NODES",
        })

    adapter_registry = build_adapter_registry(registry)
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
        results.append(
            execute_shadow_node(
                node,
                event,
                dict(event.get("input_payload") or {}),
            )
        )

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
        "authoritative_effect": "NONE",
        "authority_granted": False,
        "automatic_gate_advance": False,
        "decision_authority": False,
    }
