#!/usr/bin/env python3
"""Validate a compiled GWC node registry using stdlib-only checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REQUIRED_NODE_FIELDS = {"node_id", "node_type", "title", "canonical", "authority_boundary", "gates"}
VALID_GATES = {"G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"}
AUTHORITY_TO_GATE = {
    "g2_required": "G2_EXECUTION",
    "g3_required": "G3_PR",
    "g4_required": "G4_MERGE",
    "g5_required": "G5_DEPLOY",
    "g6_required": "G6_PRODUCTION_DATA",
}


def _finding(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _load_registry(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("registry must be a JSON object")
    return data


def validate_registry(registry: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    if registry.get("schema_version") != "0.1":
        findings.append(_finding("BLOCKER", "SCHEMA_VERSION_INVALID", "schema_version must be 0.1"))

    nodes = registry.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        findings.append(_finding("BLOCKER", "NODES_MISSING", "registry must contain at least one node"))
        return findings

    seen: set[str] = set()
    node_ids: set[str] = set()

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            findings.append(_finding("BLOCKER", "NODE_INVALID", f"node[{index}] must be an object"))
            continue

        missing = sorted(REQUIRED_NODE_FIELDS.difference(node))
        if missing:
            findings.append(_finding("BLOCKER", "NODE_REQUIRED_FIELD_MISSING", f"{node.get('node_id', index)} missing {missing}"))
            continue

        node_id = node["node_id"]
        if node_id in seen:
            findings.append(_finding("BLOCKER", "NODE_ID_DUPLICATE", f"duplicate node_id {node_id}"))
        seen.add(node_id)
        node_ids.add(node_id)

        gates = node.get("gates")
        if not isinstance(gates, list):
            findings.append(_finding("BLOCKER", "NODE_GATES_INVALID", f"{node_id} gates must be a list"))
            continue

        invalid_gates = sorted(set(gates).difference(VALID_GATES))
        if invalid_gates:
            findings.append(_finding("BLOCKER", "NODE_GATE_UNKNOWN", f"{node_id} has unknown gates {invalid_gates}"))

        authority = node.get("authority_boundary")
        required_gate = AUTHORITY_TO_GATE.get(authority)
        if required_gate and required_gate not in gates:
            findings.append(_finding("BLOCKER", "AUTHORITY_GATE_MISMATCH", f"{node_id} requires {required_gate} in gates"))

        if node.get("canonical") == "audit_projection" and authority not in {"read_only", "none"}:
            findings.append(_finding("BLOCKER", "AUDIT_PROJECTION_HAS_AUTHORITY", f"{node_id} audit projection must not grant authority"))

    edges = registry.get("edges", [])
    if not isinstance(edges, list):
        findings.append(_finding("BLOCKER", "EDGES_INVALID", "edges must be a list"))
    else:
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                findings.append(_finding("BLOCKER", "EDGE_INVALID", f"edge[{index}] must be an object"))
                continue
            source = edge.get("source")
            target = edge.get("target")
            if source not in node_ids or target not in node_ids:
                findings.append(_finding("BLOCKER", "EDGE_TARGET_MISSING", f"edge[{index}] references unknown node"))

    return findings


def validation_result(registry_path: Path, registry: dict[str, Any], findings: list[dict[str, str]]) -> dict[str, Any]:
    outcome = "FAIL" if any(item["severity"] == "BLOCKER" for item in findings) else "PASS"
    return {"schema_version": "0.1", "registry_id": registry.get("registry_id", str(registry_path)), "outcome": outcome, "findings": findings}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        registry = _load_registry(args.registry)
    except ValueError as exc:
        result = {"schema_version": "0.1", "registry_id": str(args.registry), "outcome": "FAIL", "findings": [_finding("BLOCKER", "REGISTRY_LOAD_FAILED", str(exc))]}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    result = validation_result(args.registry, registry, validate_registry(registry))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
