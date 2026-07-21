#!/usr/bin/env python3
"""Simulate whether a requested action has a required GWC gate node."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ACTION_TO_GATE = {
    "repository_write": "G2_EXECUTION",
    "draft_pr": "G3_PR",
    "merge": "G4_MERGE",
    "auto_merge": "G4_MERGE",
    "deploy": "G5_DEPLOY",
    "release": "G5_DEPLOY",
    "production_config": "G6_PRODUCTION_DATA",
    "production_data": "G6_PRODUCTION_DATA",
    "credentials": "G6_PRODUCTION_DATA",
    "secrets": "G6_PRODUCTION_DATA",
    "migration": "G6_PRODUCTION_DATA",
}


def _finding(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _load_registry(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def simulate(registry: dict[str, Any], requested_action: str) -> dict[str, Any]:
    required_gate = ACTION_TO_GATE.get(requested_action)
    findings: list[dict[str, str]] = []

    nodes = registry.get("nodes", [])
    gate_nodes = [node for node in nodes if isinstance(node, dict) and node.get("node_type") == "gate"]
    gate_names = {gate for node in gate_nodes for gate in node.get("gates", [])}

    if required_gate is None:
        findings.append(_finding("MAJOR", "ACTION_UNKNOWN", f"unknown requested action {requested_action}"))
    elif required_gate not in gate_names:
        findings.append(_finding("BLOCKER", "REQUIRED_GATE_MISSING", f"{requested_action} requires {required_gate}"))

    for node in nodes:
        if not isinstance(node, dict):
            findings.append(_finding("BLOCKER", "NODE_INVALID", "registry contains non-object node"))
            continue

        if node.get("canonical") == "audit_projection" and node.get("authority_boundary") not in {"read_only", "none"}:
            findings.append(_finding("BLOCKER", "AUDIT_PROJECTION_AUTHORITY", f"{node.get('node_id')} is audit projection but grants authority"))

        if node.get("node_type") == "projection" and node.get("canonical") == "canonical":
            findings.append(_finding("BLOCKER", "PROJECTION_MARKED_CANONICAL", f"{node.get('node_id')} projection cannot be canonical coding authority"))

    if not findings:
        findings.append(_finding("INFO", "SIMULATION_OK", f"{requested_action} is covered by {required_gate}"))

    outcome = "FAIL" if any(item["severity"] == "BLOCKER" for item in findings) else "PASS"
    return {"schema_version": "0.1", "registry_id": registry.get("registry_id", "unknown"), "requested_action": requested_action, "outcome": outcome, "required_gate": required_gate, "findings": findings}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--requested-action", required=True, choices=sorted(ACTION_TO_GATE))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        registry = _load_registry(args.registry)
        result = simulate(registry, args.requested_action)
    except (OSError, json.JSONDecodeError) as exc:
        result = {"schema_version": "0.1", "registry_id": str(args.registry), "requested_action": args.requested_action, "outcome": "FAIL", "required_gate": ACTION_TO_GATE.get(args.requested_action), "findings": [_finding("BLOCKER", "SIMULATION_LOAD_FAILED", str(exc))]}

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
