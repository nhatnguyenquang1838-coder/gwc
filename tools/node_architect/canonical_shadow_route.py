#!/usr/bin/env python3
"""Canonical fail-closed route decision for Node Architect shadow execution.

The historical route packs remain catalogue/candidate data only. A candidate is
not executable until activation, immutable runtime identity, profile/graph/node
registry bindings, canonical gate applicability, node-specific guards and the
node's semantic implementation binding all pass.

This module deliberately reuses revision helpers from ``resolve_gate_node_route``
so shadow and authoritative paths share the same registry/graph identity
semantics rather than inventing a second revision model.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .gate_node_routes import FAMILY_GATE_BINDINGS, ROUTE_PACKS
from .resolve_gate_node_route import _graph_revision, _node_registry_revision
from .semantic_source_resolver import resolve_semantic_source

SourceResolver = Callable[..., Mapping[str, Any]]


def _blocked(reason: str, *, route_pack: str | None = None, status: str = "SHADOW_DISABLED_FAIL_CLOSED", rejections=None) -> dict[str, Any]:
    return {
        "status": status,
        "reason_code": reason,
        "route_pack": route_pack,
        "selected_node_ids": [],
        "rejections": list(rejections or []),
        "authority_granted": False,
        "decision_authority": False,
        "automatic_gate_advance": False,
    }


def _schema_type_ok(value: Any, expected: str) -> bool:
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "object":
        return isinstance(value, Mapping)
    return True


def _validate_activation(activation: Mapping[str, Any], *, root: Path) -> bool:
    """Enforce the checked-in activation schema without a runtime dependency."""
    try:
        schema = json.loads((root / "schemas/node-architect/shadow-runtime-activation.schema.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(schema, Mapping):
        return False
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    if not isinstance(required, list) or not isinstance(properties, Mapping):
        return False
    if any(key not in activation for key in required):
        return False
    if schema.get("additionalProperties") is False and any(key not in properties for key in activation):
        return False
    for key, rule in properties.items():
        if key not in activation or not isinstance(rule, Mapping):
            continue
        value = activation[key]
        if "const" in rule and value != rule["const"]:
            return False
        expected_type = rule.get("type")
        if isinstance(expected_type, str) and not _schema_type_ok(value, expected_type):
            return False
        if expected_type == "string" and isinstance(rule.get("minLength"), int) and len(value) < rule["minLength"]:
            return False
    return True


def _load_json(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _canonical_gate_applicability(*, gate: str, root: Path, policy_registry: Mapping[str, Any] | None) -> str | None:
    registry = policy_registry or _load_json(root / "core/node-architect/gate-applicability-policy-registry.json")
    if registry is None:
        return None
    minimums = registry.get("canonical_minimums")
    if not isinstance(minimums, Mapping):
        return None
    rule = minimums.get(gate)
    if not isinstance(rule, Mapping):
        return None
    decision = rule.get("min_decision")
    return str(decision) if decision in {"REQUIRED", "NOT_APPLICABLE", "BLOCKED"} else None


def _route_matches(route_packs: Mapping[str, Mapping[str, Any]], scenario: str) -> list[tuple[str, Mapping[str, Any]]]:
    return [
        (route_id, pack)
        for route_id, pack in route_packs.items()
        if isinstance(pack, Mapping) and pack.get("scenario") == scenario and pack.get("runtime_executable") is True
    ]


def _descriptor_for(node: Mapping[str, Any], *, root: Path) -> Mapping[str, Any] | None:
    provenance = node.get("provenance") if isinstance(node.get("provenance"), Mapping) else {}
    path = provenance.get("source_path")
    if not isinstance(path, str) or not path:
        return None
    return _load_json(root / path)


def _guard_rejection(node: Mapping[str, Any], descriptor: Mapping[str, Any] | None, event: Mapping[str, Any]) -> str | None:
    gate = str(event.get("gate", ""))
    action = str(event.get("requested_action", ""))
    scenario = str(event.get("scenario", ""))
    guard = node.get("runtime_guard") if isinstance(node.get("runtime_guard"), Mapping) else {}

    for field, actual in (("gates", gate), ("actions", action), ("scenarios", scenario)):
        allowed = guard.get(field)
        if isinstance(allowed, list) and allowed and actual not in {str(item) for item in allowed}:
            return "SHADOW_NODE_GUARD_REJECTED"

    # Existing descriptors already encode exact gate applicability. Reuse it as
    # the node-specific gate guard when no stronger runtime_guard is declared.
    if descriptor is not None:
        gates = descriptor.get("gates")
        if isinstance(gates, list) and gates and gate not in {str(item) for item in gates}:
            return "SHADOW_NODE_GUARD_REJECTED"
        applicability = descriptor.get("applicability")
        if isinstance(applicability, Mapping):
            actions = applicability.get("actions")
            scenarios = applicability.get("scenarios")
            if isinstance(actions, list) and actions and action not in {str(item) for item in actions}:
                return "SHADOW_NODE_GUARD_REJECTED"
            if isinstance(scenarios, list) and scenarios and scenario not in {str(item) for item in scenarios}:
                return "SHADOW_NODE_GUARD_REJECTED"
    return None


def resolve_shadow_route(
    *,
    event: Mapping[str, Any],
    registry: Mapping[str, Any],
    activation: Mapping[str, Any],
    observed_state: Mapping[str, Any],
    profile: Mapping[str, Any],
    graph_registry: Mapping[str, Any],
    root: Path | str = Path("."),
    source_resolver: SourceResolver = resolve_semantic_source,
    route_packs: Mapping[str, Mapping[str, Any]] = ROUTE_PACKS,
    policy_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    repo_root = Path(root).resolve()

    if not _validate_activation(activation, root=repo_root):
        return _blocked("SHADOW_ACTIVATION_SCHEMA_INVALID")

    # Exact immutable runtime identity is checked before route/node selection.
    identity_pairs = (
        (event.get("repository"), observed_state.get("repository")),
        (event.get("branch"), observed_state.get("branch")),
        (event.get("base_sha"), observed_state.get("base_sha")),
        (event.get("exact_revision"), observed_state.get("head_sha")),
        (event.get("profile_revision"), observed_state.get("profile_revision")),
        (event.get("graph_revision"), observed_state.get("graph_revision")),
        (event.get("node_registry_revision"), observed_state.get("node_registry_revision")),
        (event.get("policy_revision"), observed_state.get("policy_revision")),
    )
    if any(not left or not right or str(left) != str(right) for left, right in identity_pairs):
        return _blocked("SHADOW_RUNTIME_IDENTITY_DRIFT")

    profile_revision = str(profile.get("revision", ""))
    graph_revision = _graph_revision(graph_registry)
    node_registry_revision = _node_registry_revision(registry)
    policy_revision = str(event.get("policy_revision", ""))
    if profile_revision != str(event.get("profile_revision", "")):
        return _blocked("SHADOW_PROFILE_REVISION_DRIFT")
    if graph_revision != str(event.get("graph_revision", "")) or str(profile.get("bound_graph_revision", "")) != graph_revision:
        return _blocked("SHADOW_GRAPH_REVISION_DRIFT")
    if node_registry_revision != str(event.get("node_registry_revision", "")) or str(profile.get("bound_node_registry_revision", "")) != node_registry_revision:
        return _blocked("SHADOW_NODE_REGISTRY_REVISION_DRIFT")
    declared_policy_revision = str(profile.get("policy_revision", ""))
    if declared_policy_revision and declared_policy_revision != policy_revision:
        return _blocked("SHADOW_POLICY_REVISION_DRIFT")

    gate = str(event.get("gate", ""))
    gate_applicability = _canonical_gate_applicability(gate=gate, root=repo_root, policy_registry=policy_registry)
    if gate_applicability == "NOT_APPLICABLE":
        out = _blocked("SHADOW_GATE_NOT_APPLICABLE", status="SHADOW_GATE_NOT_APPLICABLE")
        out.update({
            "profile_revision": profile_revision,
            "graph_revision": graph_revision,
            "node_registry_revision": node_registry_revision,
            "policy_revision": policy_revision,
            "gate_applicability": gate_applicability,
        })
        return out
    if gate_applicability == "BLOCKED":
        return _blocked("SHADOW_GATE_APPLICABILITY_BLOCKED")

    matches = _route_matches(route_packs, str(event.get("scenario", "")))
    if not matches:
        return _blocked("SHADOW_SCENARIO_UNMAPPED", status="SHADOW_NO_APPLICABLE_ROUTE")
    if len(matches) != 1:
        return _blocked("SHADOW_ROUTE_AMBIGUOUS")
    route_id, pack = matches[0]
    families = {str(item) for item in pack.get("families", [])}

    selected: list[str] = []
    rejections: list[dict[str, Any]] = []
    for raw in registry.get("nodes", []):
        if not isinstance(raw, Mapping):
            continue
        node_id = raw.get("id")
        family = raw.get("family")
        if not isinstance(node_id, str) or not isinstance(family, str):
            continue
        if family not in families or gate not in FAMILY_GATE_BINDINGS.get(family, []):
            continue
        if raw.get("runtime_executable") is False:
            rejections.append({"node_id": node_id, "reason_code": "NODE_NOT_RUNTIME_EXECUTABLE"})
            continue
        descriptor = _descriptor_for(raw, root=repo_root)
        guard_reason = _guard_rejection(raw, descriptor, event)
        if guard_reason:
            rejections.append({"node_id": node_id, "reason_code": guard_reason})
            continue
        try:
            source = source_resolver(raw, root=repo_root)
        except Exception as exc:
            rejections.append({"node_id": node_id, "reason_code": "SEMANTIC_SOURCE_RESOLUTION_ERROR", "error": f"{type(exc).__name__}: {exc}"})
            continue
        if not isinstance(source, Mapping) or source.get("runtime_eligible") is not True:
            reason = source.get("reason_code") if isinstance(source, Mapping) else None
            rejections.append({"node_id": node_id, "reason_code": str(reason or "SEMANTIC_IMPLEMENTATION_UNAVAILABLE")})
            continue
        selected.append(node_id)

    if not selected:
        out = _blocked("SHADOW_NO_APPLICABLE_NODES", route_pack=route_id, status="SHADOW_NO_APPLICABLE_NODES", rejections=rejections)
        out.update({
            "profile_revision": profile_revision,
            "graph_revision": graph_revision,
            "node_registry_revision": node_registry_revision,
            "policy_revision": policy_revision,
            "gate_applicability": gate_applicability,
        })
        return out

    return {
        "status": "SHADOW_ROUTE_RESOLVED",
        "reason_code": "SHADOW_ROUTE_RESOLVED",
        "route_pack": route_id,
        "selected_node_ids": selected,
        "rejections": rejections,
        "profile_revision": profile_revision,
        "graph_revision": graph_revision,
        "node_registry_revision": node_registry_revision,
        "policy_revision": policy_revision,
        "gate_applicability": gate_applicability,
        "authority_granted": False,
        "decision_authority": False,
        "automatic_gate_advance": False,
    }


__all__ = ["resolve_shadow_route"]
