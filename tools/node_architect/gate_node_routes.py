#!/usr/bin/env python3
"""Source-backed gate/family route packs for Node Architect shadow execution."""
from __future__ import annotations

from typing import Any

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
