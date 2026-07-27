#!/usr/bin/env python3
"""Deterministic P3 backward graph compiler and scenario routing engine.

The module intentionally uses only the Python standard library so repository and
CI consumers can execute it without adding a runtime dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, MutableSequence, Sequence


class CompileError(ValueError):
    """Raised when a graph cannot produce a governed deterministic plan."""


class RouteClass(str, Enum):
    VALID_AUTO = "VALID_AUTO"
    VALID_HUMAN = "VALID_HUMAN"
    CONDITIONAL = "CONDITIONAL"
    BLOCKED = "BLOCKED"
    UNSAFE = "UNSAFE"


@dataclass(frozen=True)
class GuardResult:
    passed: bool
    conditional: bool = False
    reason: str = ""


def _stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_stable(value).encode("utf-8")).hexdigest()


def _graph_revision(nodes: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {key: node[key] for key in sorted(node)}
        for node in sorted(nodes, key=lambda item: str(item["id"]))
    ]
    return _digest(payload)


def _index(nodes: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("id", ""))
        if not node_id or node_id in indexed:
            raise CompileError("MISSING_DEPENDENCY: node ids must be unique and non-empty")
        indexed[node_id] = node
    return indexed


def _dependencies(node: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(str(item) for item in node.get("dependencies", [])))


def compile_backward_graph(
    nodes: Sequence[Mapping[str, Any]],
    desired_outcome: str,
    safe_failure_outcome: str,
    *,
    profile: str = "standard",
    allowed_authorities: Iterable[str] = (),
) -> dict[str, Any]:
    """Compile the dependency closure for a desired outcome.

    Selection order is deterministic: dependencies are visited lexicographically
    and emitted in topological order. Profile overlays may disable nodes or add a
    required profile. Human/production authorities are never silently promoted.
    """
    indexed = _index(nodes)
    if desired_outcome not in indexed:
        raise CompileError("MISSING_TERMINAL: desired outcome is absent")
    if safe_failure_outcome not in indexed:
        raise CompileError("MISSING_TERMINAL: safe-failure outcome is absent")

    authorities = set(allowed_authorities)
    state: dict[str, int] = {}
    order: list[str] = []
    rejected: list[dict[str, str]] = []

    def visit(node_id: str) -> None:
        if node_id not in indexed:
            raise CompileError(f"MISSING_DEPENDENCY: {node_id}")
        if state.get(node_id) == 1:
            raise CompileError(f"CYCLE_UNSAFE: {node_id}")
        if state.get(node_id) == 2:
            return
        state[node_id] = 1
        node = indexed[node_id]
        overlays = node.get("profiles", {})
        overlay = overlays.get(profile, {}) if isinstance(overlays, Mapping) else {}
        if overlay.get("enabled") is False:
            raise CompileError(f"PROFILE_MISMATCH: {node_id} disabled for {profile}")
        required_profile = node.get("required_profile")
        if required_profile and required_profile != profile:
            raise CompileError(f"PROFILE_MISMATCH: {node_id} requires {required_profile}")
        authority = str(node.get("authority", "AUTO"))
        if authority not in {"AUTO", "READ_ONLY"} and authority not in authorities:
            rejected.append({"id": node_id, "reason": "AUTHORITY_MISMATCH"})
            raise CompileError(f"AUTHORITY_MISMATCH: {node_id} requires {authority}")
        if node.get("unsafe") is True:
            raise CompileError(f"UNSAFE_TERMINAL: {node_id}")
        for dependency in _dependencies(node):
            visit(dependency)
        state[node_id] = 2
        order.append(node_id)

    visit(desired_outcome)
    return {
        "graph_revision": _graph_revision(nodes),
        "profile": profile,
        "desired_outcome": desired_outcome,
        "safe_failure_outcome": safe_failure_outcome,
        "selected_nodes": order,
        "rejected_nodes": rejected,
        "status": "COMPILED",
    }


def evaluate_guard(guard: Mapping[str, Any], context: Mapping[str, Any]) -> GuardResult:
    """Evaluate a typed guard without implicit truthiness coercion.

    ``value_from_field`` is the explicit form for comparing two context fields.
    The legacy form, where ``value`` names another present context field, remains
    supported for the initial SCRUM-115 registry entries.
    """
    kind = guard.get("type")
    field = guard.get("field")
    actual = context.get(field)
    expected = guard.get("value")
    value_from_field = guard.get("value_from_field")
    if value_from_field is not None:
        expected = context.get(value_from_field)
    elif kind == "equals" and isinstance(expected, str) and expected in context and field != expected:
        expected = context[expected]

    if kind == "exists":
        passed = field in context
    elif kind == "equals":
        passed = type(actual) is type(expected) and actual == expected
    elif kind == "in":
        values = guard.get("values", [])
        passed = any(type(actual) is type(item) and actual == item for item in values)
    elif kind == "gte":
        passed = (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and isinstance(expected, (int, float))
            and not isinstance(expected, bool)
            and actual >= expected
        )
    elif kind == "lte":
        passed = (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and isinstance(expected, (int, float))
            and not isinstance(expected, bool)
            and actual <= expected
        )
    else:
        return GuardResult(False, False, f"UNKNOWN_GUARD_TYPE:{kind}")
    if passed:
        return GuardResult(True)
    return GuardResult(False, bool(guard.get("conditional")), str(guard.get("reason", "GUARD_FAILED")))


def enumerate_routes(
    nodes: Sequence[Mapping[str, Any]],
    start: str,
    green: str,
    context: Mapping[str, Any],
    *,
    max_depth: int = 32,
) -> list[dict[str, Any]]:
    """Enumerate and rank all simple routes from start to green."""
    indexed = _index(nodes)
    if start not in indexed or green not in indexed:
        raise CompileError("MISSING_TERMINAL: route endpoint absent")
    routes: list[dict[str, Any]] = []

    def walk(
        node_id: str,
        path: list[str],
        conditional: bool,
        human: bool,
        blocked: bool,
        unsafe: bool,
    ) -> None:
        if len(path) > max_depth:
            return
        node = indexed[node_id]
        guard_results = [evaluate_guard(item, context) for item in node.get("guards", [])]
        node_conditional = conditional or any(
            result.conditional and not result.passed for result in guard_results
        )
        node_blocked = blocked or any(
            not result.passed and not result.conditional for result in guard_results
        )
        node_human = human or str(node.get("authority", "AUTO")) not in {"AUTO", "READ_ONLY"}
        node_unsafe = unsafe or node.get("unsafe") is True
        if node_id == green:
            if node_unsafe:
                route_class = RouteClass.UNSAFE
            elif node_blocked:
                route_class = RouteClass.BLOCKED
            elif node_conditional:
                route_class = RouteClass.CONDITIONAL
            elif node_human:
                route_class = RouteClass.VALID_HUMAN
            else:
                route_class = RouteClass.VALID_AUTO
            routes.append({"path": path, "class": route_class.value, "length": len(path)})
            return
        for successor in sorted(str(item) for item in node.get("successors", [])):
            if successor not in indexed:
                raise CompileError(f"MISSING_DEPENDENCY: {successor}")
            if successor not in path:
                walk(
                    successor,
                    path + [successor],
                    node_conditional,
                    node_human,
                    node_blocked,
                    node_unsafe,
                )

    walk(start, [start], False, False, False, False)
    priority = {
        RouteClass.VALID_AUTO.value: 0,
        RouteClass.VALID_HUMAN.value: 1,
        RouteClass.CONDITIONAL.value: 2,
        RouteClass.BLOCKED.value: 3,
        RouteClass.UNSAFE.value: 4,
    }
    routes.sort(key=lambda route: (priority[route["class"]], route["length"], tuple(route["path"])))
    for position, route in enumerate(routes, start=1):
        route["rank"] = position
    return routes


def route_decision(
    nodes: Sequence[Mapping[str, Any]], start: str, green: str, context: Mapping[str, Any]
) -> dict[str, Any]:
    routes = enumerate_routes(nodes, start, green, context)
    selected = routes[0] if routes else None
    return {
        "graph_revision": _graph_revision(nodes),
        "routes": routes,
        "selected_route": selected,
        "status": "ROUTED" if selected else "NO_ROUTE",
    }


def scenario_nodes(
    scenario: Mapping[str, Any],
    node_metadata: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Build a deterministic route graph from a canonical scenario.

    Canonical node ``authority_class`` values are mapped into the route engine's
    authority/unsafe flags. This is the critical bridge that prevents a scenario
    route through a human or prohibited boundary from becoming ``VALID_AUTO``.
    """
    metadata = {str(node["id"]): dict(node) for node in node_metadata}
    indexed: dict[str, dict[str, Any]] = {
        str(node_id): {"id": str(node_id), "successors": []}
        for node_id in scenario.get("route_nodes", [])
    }
    for node_id, node in metadata.items():
        if node_id not in indexed:
            continue
        indexed[node_id].update(node)
        indexed[node_id].setdefault("successors", [])
        authority_class = str(node.get("authority_class", "automatic"))
        if authority_class in {"delegated", "human_required"}:
            indexed[node_id]["authority"] = authority_class.upper()
        elif authority_class == "prohibited":
            indexed[node_id]["authority"] = "PROHIBITED"
            indexed[node_id]["unsafe"] = True
        else:
            indexed[node_id]["authority"] = "AUTO"

    for edge in scenario.get("edges", []):
        if edge.get("runtime_executable") and edge.get("edge_type") in {"runtime", "dependency"}:
            source = str(edge["source"])
            target = str(edge["target"])
            indexed.setdefault(source, {"id": source, "successors": []})["successors"].append(target)
            indexed.setdefault(target, {"id": target, "successors": []})

    for node in indexed.values():
        node["successors"] = sorted(set(str(item) for item in node.get("successors", [])))
    return [indexed[node_id] for node_id in sorted(indexed)]


def append_scenario_decision(
    history: MutableSequence[Mapping[str, Any]],
    decision: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Append a decision without permitting an existing ID to be rebound."""
    for existing in history:
        if existing.get("decision_id") == decision.get("decision_id"):
            if _stable(existing) != _stable(decision):
                raise CompileError("IMMUTABILITY_VIOLATION: decision id rebound")
            return existing
    history.append(dict(decision))
    return decision


def decide_scenario(
    scenario: Mapping[str, Any],
    facts: Mapping[str, Any],
    *,
    node_metadata: Iterable[Mapping[str, Any]] = (),
    history: MutableSequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate one canonical scenario and emit an immutable decision record."""
    missing = [field for field in scenario.get("activation_facts", []) if field not in facts]
    guard_results = []
    for guard in scenario.get("guards", []):
        result = evaluate_guard(guard, facts)
        guard_results.append(
            {
                "id": guard.get("id"),
                "passed": result.passed,
                "conditional": result.conditional,
                "reason": result.reason,
            }
        )

    policy = scenario["route_policy"]
    nodes = scenario_nodes(scenario, node_metadata)
    candidate_routes: list[dict[str, Any]] = []
    for green in sorted(str(item) for item in policy.get("green_targets", [])):
        candidate_routes.extend(
            enumerate_routes(
                nodes,
                str(policy["start_node"]),
                green,
                facts,
                max_depth=int(policy.get("max_depth", 32)),
            )
        )

    priority = {
        RouteClass.VALID_AUTO.value: 0,
        RouteClass.VALID_HUMAN.value: 1,
        RouteClass.CONDITIONAL.value: 2,
        RouteClass.BLOCKED.value: 3,
        RouteClass.UNSAFE.value: 4,
    }
    candidate_routes.sort(
        key=lambda route: (
            priority[route["class"]],
            route["length"],
            tuple(route["path"]),
        )
    )
    for position, route in enumerate(candidate_routes, start=1):
        route["rank"] = position

    blocked = any(not item["passed"] and not item["conditional"] for item in guard_results)
    conditional = bool(missing) or any(
        not item["passed"] and item["conditional"] for item in guard_results
    )
    eligible = [
        route
        for route in candidate_routes
        if route["class"] in {RouteClass.VALID_AUTO.value, RouteClass.VALID_HUMAN.value}
    ]

    selected_route: dict[str, Any] | None = None
    if conditional:
        classification = RouteClass.CONDITIONAL.value
    elif blocked:
        classification = RouteClass.BLOCKED.value
    elif eligible:
        selected_route = eligible[0]
        classification = selected_route["class"]
    elif candidate_routes:
        classification = candidate_routes[0]["class"]
    else:
        classification = RouteClass.BLOCKED.value

    record: dict[str, Any] = {
        "scenario_id": scenario["id"],
        "scenario_version": scenario["version"],
        "graph_revision": _graph_revision(nodes),
        "facts_digest": _digest(facts),
        "missing_activation_facts": missing,
        "guard_results": guard_results,
        "candidate_routes": candidate_routes,
        "selected_route": selected_route,
        "classification": classification,
        "auto_execute": classification == RouteClass.VALID_AUTO.value,
    }
    record["decision_id"] = _digest(record)
    record["decision_digest"] = record["decision_id"]
    if history is not None:
        append_scenario_decision(history, record)
    return record
