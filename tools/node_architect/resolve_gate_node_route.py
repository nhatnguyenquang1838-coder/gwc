"""Resolve a GWC gate/action pair to one executable Node Architect node."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping

MATURITY = {"experimental": 0, "pilot": 1, "stable": 2}
FAIL_CODES = {
    "NODE_CONTEXT_NOT_LOADED",
    "NODE_ROUTE_MISSING",
    "NODE_ROUTE_AMBIGUOUS",
    "NODE_CONTRACT_MISSING",
    "NODE_CONTRACT_INCOMPLETE",
    "NODE_IMPLEMENTATION_UNAVAILABLE",
    "NODE_NOT_EXECUTABLE_AT_MATURITY",
    "GATE_NODE_BINDING_MISMATCH",
    "GRAPH_REVISION_DRIFT",
    "PROFILE_REVISION_DRIFT",
}


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _graph_revision(graph: Mapping[str, Any]) -> str:
    revision = graph.get("revision")
    if isinstance(revision, Mapping):
        return str(revision.get("revision_id", ""))
    return str(revision or "")


def _node_registry_revision(registry: Mapping[str, Any]) -> str:
    revision = registry.get("revision")
    if isinstance(revision, Mapping):
        return str(revision.get("revision_id", ""))
    return str(revision or "")


def _node_map(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(node.get("id")): node for node in registry.get("nodes", []) if node.get("id")}


def _implementation_available(root: Path, implementation: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    kind = implementation.get("kind")
    ref = str(implementation.get("ref", ""))
    if kind == "connector":
        return ref in set(context.get("available_connectors", []))
    if kind not in {"python", "resolver"} or not ref:
        return False
    path_text, _, callable_name = ref.partition(":")
    path = root / path_text
    if not path.is_file() or not callable_name:
        return False
    module_name = "_gwc_route_impl_check_" + hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
    previous_module = sys.modules.get(module_name)
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return False
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return callable(getattr(module, callable_name, None))
    except Exception:
        return False
    finally:
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module


def _blocked(
    *, task_id: str, gate: str, requested_action: str,
    profile_id: str = "", profile_revision: str = "", graph_revision: str = "",
    route_id: str | None = None, current_node: str | None = None,
    implementation: Mapping[str, Any] | None = None,
    required_context: list[str] | None = None, loaded_context: list[str] | None = None,
    reasons: list[str],
) -> dict[str, Any]:
    codes = []
    for code in reasons:
        if code not in codes:
            codes.append(code)
    payload = {
        "schema_version": "1.0",
        "artifact_type": "gate-node-route-decision",
        "task_id": task_id,
        "gate": gate,
        "requested_action": requested_action,
        "profile_id": profile_id,
        "profile_revision": profile_revision,
        "graph_revision": graph_revision,
        "route_id": route_id,
        "outcome": "BLOCKED",
        "current_node": current_node,
        "implementation": dict(implementation) if implementation else None,
        "required_context": required_context or [],
        "loaded_context": loaded_context or [],
        "next_node": None,
        "next_action": None,
        "next_gate": None,
        "reason_code": codes[0],
        "reason_codes": codes,
        "authority_granted": False,
        "write_authority_granted": False,
        "pr_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    payload["decision_digest"] = _digest(payload)
    return payload


def resolve_gate_node_route(
    *, profile: Mapping[str, Any], node_registry: Mapping[str, Any],
    graph_registry: Mapping[str, Any], context: Mapping[str, Any], root: Path,
) -> dict[str, Any]:
    task_id = str(context.get("task_id", ""))
    gate = str(context.get("gate", ""))
    action = str(context.get("requested_action", ""))
    profile_id = str(profile.get("profile_id", ""))
    profile_revision = str(profile.get("revision", ""))
    graph_revision = _graph_revision(graph_registry)

    expected_profile = str(context.get("expected_profile_revision", profile_revision))
    if expected_profile != profile_revision:
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, reasons=["PROFILE_REVISION_DRIFT"])
    expected_graph = str(context.get("expected_graph_revision", graph_revision))
    if expected_graph != graph_revision or str(profile.get("bound_graph_revision")) != graph_revision:
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, reasons=["GRAPH_REVISION_DRIFT"])
    registry_revision = _node_registry_revision(node_registry)
    if str(profile.get("bound_node_registry_revision")) != registry_revision:
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, reasons=["PROFILE_REVISION_DRIFT"])

    routes = [route for route in profile.get("routes", []) if route.get("gate") == gate and route.get("requested_action") == action]
    if not routes:
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, reasons=["NODE_ROUTE_MISSING"])
    if len(routes) != 1:
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, reasons=["NODE_ROUTE_AMBIGUOUS"])
    route = routes[0]
    route_id = str(route.get("route_id", ""))
    node_id = str(route.get("current_node", ""))
    required_context = list(route.get("required_context", []))
    loaded_context = sorted(key for key in required_context if context.get("context", {}).get(key))
    if len(loaded_context) != len(required_context):
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, route_id=route_id, current_node=node_id, implementation=route.get("implementation"), required_context=required_context, loaded_context=loaded_context, reasons=["NODE_CONTEXT_NOT_LOADED"])

    envelope = context.get("context", {}).get("g2_envelope", {})
    if not isinstance(envelope, Mapping) or any([
        str(envelope.get("task_id", "")) != task_id,
        str(envelope.get("authority_gate", "")) != gate,
        str(envelope.get("repository", "")) != str(context.get("repository", "")),
        str(envelope.get("base_sha", "")) != str(context.get("base_sha", "")),
        str(envelope.get("working_branch", "")) != str(context.get("working_branch", "")),
        str(envelope.get("scope_hash", "")) != str(context.get("scope_hash", "")),
    ]):
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, route_id=route_id, current_node=node_id, implementation=route.get("implementation"), required_context=required_context, loaded_context=loaded_context, reasons=["GATE_NODE_BINDING_MISMATCH"])

    nodes = _node_map(node_registry)
    node = nodes.get(node_id)
    if node is None:
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, route_id=route_id, current_node=node_id, implementation=route.get("implementation"), required_context=required_context, loaded_context=loaded_context, reasons=["NODE_CONTRACT_MISSING"])
    descriptor_ref = str(route.get("node_descriptor_ref", ""))
    descriptor_path = root / descriptor_ref
    if not descriptor_ref or not descriptor_path.is_file():
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, route_id=route_id, current_node=node_id, implementation=route.get("implementation"), required_context=required_context, loaded_context=loaded_context, reasons=["NODE_CONTRACT_MISSING"])
    try:
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except Exception:
        descriptor = {}
    if any(not descriptor.get(key) for key in ("node_id", "node_type", "authority_boundary", "gates")):
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, route_id=route_id, current_node=node_id, implementation=route.get("implementation"), required_context=required_context, loaded_context=loaded_context, reasons=["NODE_CONTRACT_INCOMPLETE"])
    if descriptor.get("node_id") != node_id or gate not in descriptor.get("gates", []):
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, route_id=route_id, current_node=node_id, implementation=route.get("implementation"), required_context=required_context, loaded_context=loaded_context, reasons=["GATE_NODE_BINDING_MISMATCH"])

    current_maturity = str(node.get("maturity", ""))
    minimum_maturity = str(route.get("minimum_maturity", "stable"))
    if MATURITY.get(current_maturity, -1) < MATURITY.get(minimum_maturity, 99):
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, route_id=route_id, current_node=node_id, implementation=route.get("implementation"), required_context=required_context, loaded_context=loaded_context, reasons=["NODE_NOT_EXECUTABLE_AT_MATURITY"])
    if node.get("source_status") == "proposed_registry_slot" and not route.get("allow_proposed_with_implementation", False):
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, route_id=route_id, current_node=node_id, implementation=route.get("implementation"), required_context=required_context, loaded_context=loaded_context, reasons=["NODE_NOT_EXECUTABLE_AT_MATURITY"])
    implementation = route.get("implementation", {})
    if not _implementation_available(root, implementation, context):
        return _blocked(task_id=task_id, gate=gate, requested_action=action, profile_id=profile_id, profile_revision=profile_revision, graph_revision=graph_revision, route_id=route_id, current_node=node_id, implementation=implementation, required_context=required_context, loaded_context=loaded_context, reasons=["NODE_IMPLEMENTATION_UNAVAILABLE"])

    payload = {
        "schema_version": "1.0", "artifact_type": "gate-node-route-decision",
        "task_id": task_id, "gate": gate, "requested_action": action,
        "profile_id": profile_id, "profile_revision": profile_revision,
        "graph_revision": graph_revision, "route_id": route_id,
        "outcome": "ROUTE_SELECTED", "current_node": node_id,
        "implementation": dict(implementation), "required_context": required_context,
        "loaded_context": loaded_context, "next_node": route.get("next_node"),
        "next_action": route.get("next_action"), "next_gate": route.get("next_gate"),
        "reason_code": "ROUTE_SELECTED", "reason_codes": ["ROUTE_SELECTED"],
        "authority_granted": False, "write_authority_granted": False,
        "pr_authority_granted": False, "merge_authority_granted": False,
        "deployment_authority_granted": False, "production_authority_granted": False,
    }
    payload["decision_digest"] = _digest(payload)
    return payload


def _load(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--node-registry", type=Path, required=True)
    parser.add_argument("--graph-registry", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    args = parser.parse_args()
    decision = resolve_gate_node_route(profile=_load(args.profile), node_registry=_load(args.node_registry), graph_registry=_load(args.graph_registry), context=_load(args.context), root=args.root)
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0 if decision["outcome"] == "ROUTE_SELECTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
