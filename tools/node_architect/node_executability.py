#!/usr/bin/env python3
"""Canonical-81 shadow executability qualification helpers.

This module deliberately separates catalogue/maturity state from runtime
executability. A node can be instruction-ready for shadow evaluation without
being adapter-bound, route-bound, or authoritative.
"""
from __future__ import annotations

from typing import Any

CANONICAL_NODE_COUNT = 81
E_LEVELS = (
    "E0_CATALOGUED",
    "E1_INSTRUCTION_READY",
    "E2_ADAPTER_BOUND",
    "E3_ROUTE_BOUND",
    "E4_REPLAY_PROVEN",
    "E5_OBSERVED",
)


def _instruction_contract(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry": {
            "requires": ["task_id", "run_id", "gate", "exact_revision", "input_payload"],
            "node_version": node.get("version", "unknown"),
        },
        "do": {
            "mode": "shadow_readonly",
            "authority": "none",
            "output_effect": "observe_only",
            "operation": "evaluate_declared_node_semantics",
        },
        "branches": {
            "outcomes": ["APPLICABLE", "NOT_APPLICABLE", "BLOCKED"],
            "fail_closed": True,
        },
        "exit": {
            "requires": ["applicability", "outcome", "reason_code", "evidence_refs"],
            "automatic_gate_advance": False,
        },
        "next": {
            "selection": "route_pack",
            "decision_authority": False,
        },
    }


def build_qualification_records(registry: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for node in registry.get("nodes", []):
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            continue
        records.append(
            {
                "node_id": node_id,
                "family": node.get("family"),
                "version": node.get("version"),
                "maturity": node.get("maturity"),
                "source_status": node.get("source_status"),
                "effect_class": node.get("effect_class"),
                "authority_class": node.get("authority_class"),
                "executability_level": "E1_INSTRUCTION_READY",
                "runtime_executable": False,
                "instruction_contract": _instruction_contract(node),
                "qualification": {
                    "catalogued": True,
                    "instruction_ready": True,
                    "adapter_bound": False,
                    "route_bound": False,
                    "replay_proven": False,
                    "observed": False,
                },
            }
        )
    return records


def validate_canonical_coverage(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = registry.get("nodes")
    if not isinstance(nodes, list):
        return ["CANONICAL_NODES_NOT_LIST"]
    ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(nodes) != CANONICAL_NODE_COUNT or registry.get("declared_slot_count") != CANONICAL_NODE_COUNT:
        errors.append("CANONICAL_NODE_COUNT_MISMATCH")
    if len(ids) != len(set(ids)):
        errors.append("CANONICAL_NODE_ID_DUPLICATE")
    if any(not isinstance(node_id, str) or not node_id for node_id in ids):
        errors.append("CANONICAL_NODE_ID_INVALID")
    return errors
