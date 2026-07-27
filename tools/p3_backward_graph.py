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
from typing import Any, Iterable, Mapping, Sequence


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


def _graph_revision(nodes: Sequence[Mapping[str, Any]]) -> str:
    payload = [{k: node[k] for k in sorted(node)} for node in sorted(nodes, key=lambda n: str(n["id"]))]
    return "sha256:" + sha256(_stable(payload).encode("utf-8")).hexdigest()


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
    """Evaluate a typed guard without implicit truthiness coercion."""
    kind = guard.get("type")
    field = guard.get("field")
    actual = context.get(field)
    expected = guard.get("value")
    if kind == "exists":
        passed = field in context
    elif kind == "equals":
        passed = type(actual) is type(expected) and actual == expected
    elif kind == "in":
        values = guard.get("values", [])
        passed = any(type(actual) is type(item) and actual == item for item in values)
    elif kind == "gte":
        passed = isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual >= expected
    elif kind == "lte":
        passed = isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual <= expected
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

    def walk(node_id: str, path: list[str], conditional: bool, human: bool, blocked: bool, unsafe: bool) -> None:
        if len(path) > max_depth:
            return
        node = indexed[node_id]
        guard_results = [evaluate_guard(item, context) for item in node.get("guards", [])]
        node_conditional = conditional or any(result.conditional and not result.passed for result in guard_results)
        node_blocked = blocked or any(not result.passed and not result.conditional for result in guard_results)
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
                walk(successor, path + [successor], node_conditional, node_human, node_blocked, node_unsafe)

    walk(start, [start], False, False, False, False)
    rank = {
        RouteClass.VALID_AUTO.value: 0,
        RouteClass.VALID_HUMAN.value: 1,
        RouteClass.CONDITIONAL.value: 2,
        RouteClass.BLOCKED.value: 3,
        RouteClass.UNSAFE.value: 4,
    }
    routes.sort(key=lambda route: (rank[route["class"]], route["length"], tuple(route["path"])))
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
