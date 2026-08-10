"""Validate structural compatibility between a Flow Profile workflow and Policy registry."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

CANONICAL_GATES = (
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION_DATA",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def validate_flow_policy_compatibility(
    *, flow_profile: Mapping[str, Any], policy_registry: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a deterministic compatibility artifact.

    This validator checks the architecture boundary only. It does not execute a
    node, grant authority, or mutate runtime state.
    """
    reasons: list[str] = []
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        reasons.append("WORKFLOW_CONTRACT_MISSING")
        workflow = {}

    expected_registry = str(flow_profile.get("policy_registry_ref") or "")
    actual_registry = str(policy_registry.get("registry_id") or "")
    if not expected_registry or expected_registry != actual_registry:
        reasons.append("POLICY_REGISTRY_BINDING_MISMATCH")

    policies = _list_of_mappings(policy_registry.get("policies"))
    policy_ids = [str(item.get("id") or "") for item in policies]
    if any(not item for item in policy_ids) or len(policy_ids) != len(set(policy_ids)):
        reasons.append("POLICY_IDENTITY_INVALID")
    policy_set = set(policy_ids)

    bindings = _list_of_mappings(workflow.get("gate_bindings"))
    gates = [str(item.get("gate") or "") for item in bindings]
    if len(gates) != len(set(gates)):
        reasons.append("GATE_BINDING_AMBIGUOUS")
    if any(gate not in CANONICAL_GATES for gate in gates):
        reasons.append("NON_CANONICAL_GATE")
    for binding in bindings:
        policy_ref = str(binding.get("policy_ref") or "")
        if not policy_ref or policy_ref not in policy_set:
            reasons.append("GATE_POLICY_MISSING")

    nodes: set[str] = set()
    for key in ("entry_nodes",):
        value = workflow.get(key, [])
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            nodes.update(str(item) for item in value if item)
    for terminal in _list_of_mappings(workflow.get("terminal_nodes")):
        node = str(terminal.get("node") or "")
        if node:
            nodes.add(node)
    edges = _list_of_mappings(workflow.get("edges"))
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target:
            reasons.append("WORKFLOW_EDGE_ENDPOINT_MISSING")
        else:
            nodes.update((source, target))

    entry_nodes = [str(item) for item in workflow.get("entry_nodes", []) if item] if isinstance(workflow.get("entry_nodes"), list) else []
    terminal_nodes = [str(item.get("node")) for item in _list_of_mappings(workflow.get("terminal_nodes")) if item.get("node")]
    if not entry_nodes:
        reasons.append("WORKFLOW_ENTRY_MISSING")
    if not terminal_nodes:
        reasons.append("WORKFLOW_TERMINAL_MISSING")

    if entry_nodes and terminal_nodes and edges:
        adjacency: dict[str, set[str]] = {}
        for edge in edges:
            if edge.get("runtime_executable") is not True:
                continue
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source and target:
                adjacency.setdefault(source, set()).add(target)
        reachable = set(entry_nodes)
        frontier = list(entry_nodes)
        while frontier:
            current = frontier.pop()
            for nxt in adjacency.get(current, set()):
                if nxt not in reachable:
                    reachable.add(nxt)
                    frontier.append(nxt)
        if not any(node in reachable for node in terminal_nodes):
            reasons.append("WORKFLOW_TERMINAL_UNREACHABLE")

    # Policy may tighten but must not advertise an explicit weakening mode.
    for policy in policies:
        if policy.get("tighten_only") is False:
            reasons.append("POLICY_WEAKENING_FORBIDDEN")
        default = policy.get("default")
        if default not in {"REQUIRED", "NOT_APPLICABLE", "BLOCKED"}:
            reasons.append("POLICY_DEFAULT_INVALID")

    unique_reasons = list(dict.fromkeys(reasons))
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_type": "flow-policy-compatibility-decision",
        "flow_profile_id": str(flow_profile.get("id") or "unbound"),
        "flow_profile_version": str(flow_profile.get("version") or flow_profile.get("schema_version") or "unbound"),
        "flow_profile_digest": _digest(flow_profile),
        "policy_registry_id": actual_registry or "unbound",
        "policy_registry_revision": str(policy_registry.get("revision") or "unbound"),
        "policy_registry_digest": _digest(policy_registry),
        "compatible": not unique_reasons,
        "reason_codes": unique_reasons or ["FLOW_POLICY_COMPATIBLE"],
    }
    artifact["decision_digest"] = _digest(artifact)
    return artifact


__all__ = ["CANONICAL_GATES", "validate_flow_policy_compatibility"]
