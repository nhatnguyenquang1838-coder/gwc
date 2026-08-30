#!/usr/bin/env python3
"""Source-backed gate/family route packs for Node Architect execution."""
from __future__ import annotations

import heapq
from typing import Any, Mapping

FAMILY_GATE_BINDINGS = {
    "intake_context": ["G0_CONTEXT"],
    "gate_authority": ["G1_ALIGNMENT", "G2_EXECUTION"],
    "repo_delivery": ["G2_EXECUTION", "G3_PR"],
    "runtime_checkpoint": ["G2_EXECUTION"],
    "validation_quality": ["G3_PR"],
    "sync_projection": ["READ_ONLY_PROJECTION"],
    "package_export": ["G2_EXECUTION", "G3_PR"],
    "failure_recovery": ["G2_EXECUTION", "G5_DEPLOY"],
    "scale_control": ["G3_PR", "G5_DEPLOY", "READ_ONLY_PROJECTION"],
}

ROUTE_PACKS = {
    "RP-01": {"scenario": "standard_pr_delivery", "families": ["intake_context", "gate_authority", "repo_delivery", "runtime_checkpoint", "validation_quality"], "runtime_executable": True, "provenance": {"source": "SCRUM-588", "kind": "source_backed_design"}},
    "RP-02": {"scenario": "approval_wait_resume", "families": ["gate_authority", "runtime_checkpoint", "failure_recovery"], "runtime_executable": True, "provenance": {"source": "SCRUM-588", "kind": "source_backed_design"}},
    "RP-03": {"scenario": "ci_failure", "families": ["repo_delivery", "runtime_checkpoint", "validation_quality", "failure_recovery"], "runtime_executable": True, "provenance": {"source": "SCRUM-588", "kind": "source_backed_design"}},
    "RP-04": {"scenario": "projection", "families": ["sync_projection", "failure_recovery"], "runtime_executable": True, "provenance": {"source": "SCRUM-588", "kind": "source_backed_design"}},
    "RP-05": {"scenario": "package_export", "families": ["package_export", "failure_recovery"], "runtime_executable": True, "provenance": {"source": "SCRUM-588", "kind": "source_backed_design"}},
    "RP-06": {"scenario": "scale_control", "families": ["scale_control", "runtime_checkpoint", "failure_recovery"], "runtime_executable": True, "provenance": {"source": "SCRUM-588", "kind": "source_backed_design"}},
}

SCENARIO_TO_PACK = {pack["scenario"]: route_id for route_id, pack in ROUTE_PACKS.items()}


def select_route_pack(scenario: str) -> str | None:
    return SCENARIO_TO_PACK.get(scenario)


def route_packs_for_family(family: str) -> list[str]:
    return [route_id for route_id, pack in ROUTE_PACKS.items() if family in pack["families"]]


def build_route_coverage(registry: dict[str, Any]) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    for node in registry.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        family = node.get("family")
        if not isinstance(node_id, str) or not isinstance(family, str):
            continue
        packs = route_packs_for_family(family)
        gates = FAMILY_GATE_BINDINGS.get(family, [])
        coverage.append({
            "node_id": node_id,
            "family": family,
            "gates": list(gates),
            "route_packs": packs,
            "route_bound": bool(packs and gates),
            "reason_code": "ROUTE_BOUND" if packs and gates else "ROUTE_OR_GATE_UNBOUND",
        })
    return coverage


def nodes_for_event(registry: dict[str, Any], *, gate: str, scenario: str) -> list[str]:
    """Legacy selection preserving registry order for shadow compatibility."""
    route_id = select_route_pack(scenario)
    if route_id is None:
        return []
    allowed_families = set(ROUTE_PACKS[route_id]["families"])
    selected: list[str] = []
    for node in registry.get("nodes", []):
        if not isinstance(node, dict):
            continue
        family = node.get("family")
        if family not in allowed_families:
            continue
        if gate not in FAMILY_GATE_BINDINGS.get(str(family), []):
            continue
        node_id = node.get("id")
        if isinstance(node_id, str):
            selected.append(node_id)
    return selected


def ordered_nodes_for_event(
    registry: Mapping[str, Any],
    *,
    gate: str,
    scenario: str,
    graph: Mapping[str, Any],
) -> list[str]:
    """Return a deterministic semantic-runtime order independent of registry order.

    Route-pack family order is the stable baseline. Runtime-executable graph edges
    add real dependency constraints. Lexical node id is only a deterministic tie
    break for nodes with no known dependency edge; it is not treated as semantic
    dependency evidence. Visualization edges are ignored.
    """
    route_id = select_route_pack(scenario)
    if route_id is None:
        return []
    pack_families = list(ROUTE_PACKS[route_id]["families"])
    family_rank = {family: index for index, family in enumerate(pack_families)}

    by_id: dict[str, Mapping[str, Any]] = {}
    for raw in registry.get("nodes", []):
        if not isinstance(raw, Mapping):
            continue
        node_id = raw.get("id")
        family = raw.get("family")
        if not isinstance(node_id, str) or not isinstance(family, str):
            continue
        if family not in family_rank:
            continue
        if gate not in FAMILY_GATE_BINDINGS.get(family, []):
            continue
        by_id[node_id] = raw

    selected = set(by_id)
    indegree = {node_id: 0 for node_id in selected}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in selected}
    for edge in graph.get("edges", []):
        if not isinstance(edge, Mapping):
            continue
        if edge.get("edge_type") != "runtime" or edge.get("runtime_executable") is not True:
            continue
        source = edge.get("source")
        target = edge.get("target")
        if source not in selected or target not in selected or source == target:
            continue
        if target not in outgoing[source]:
            outgoing[source].add(target)
            indegree[target] += 1

    def order_key(node_id: str) -> tuple[int, str]:
        family = str(by_id[node_id].get("family", ""))
        return (family_rank.get(family, len(family_rank)), node_id)

    ready: list[tuple[int, str]] = [order_key(node_id) for node_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    ordered: list[str] = []
    while ready:
        _, node_id = heapq.heappop(ready)
        ordered.append(node_id)
        for target in sorted(outgoing[node_id]):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, order_key(target))

    if len(ordered) != len(selected):
        cyclic = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
        raise ValueError("ROUTE_RUNTIME_GRAPH_CYCLE:" + ",".join(cyclic))
    return ordered
