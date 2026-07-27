#!/usr/bin/env python3
"""Validate canonical runtime registries and their cross-references."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, RefResolver

FAMILIES = {
    "intake_context",
    "gate_authority",
    "repo_delivery",
    "runtime_checkpoint",
    "validation_quality",
    "sync_projection",
    "package_export",
    "failure_recovery",
    "scale_control",
}
EXPLICIT_NODES = {
    "repo_delivery.ci-run-capture",
    "runtime_checkpoint.checkpoint-persist",
    "validation_quality.ci-evidence-capture",
    "failure_recovery.timeout-recovery",
}
VISUAL_EDGE_TYPES = {
    "visualization",
    "suggested_sequence",
    "audit",
    "human_authority",
    "blocked",
}
RUNTIME_EDGE_TYPES = {"runtime", "dependency"}
GUARD_TYPES = {"exists", "equals", "in", "gte", "lte"}


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_schema(payload: Any, schema_path: Path, schema_dir: Path) -> list[str]:
    schema = load(schema_path)
    Draft202012Validator.check_schema(schema)
    store = {}
    for candidate in schema_dir.glob("*.schema.json"):
        candidate_schema = load(candidate)
        if candidate_schema.get("$id"):
            store[candidate_schema["$id"]] = candidate_schema
    resolver = RefResolver(schema.get("$id", schema_path.as_uri()), schema, store)
    validator = Draft202012Validator(schema, resolver=resolver)
    return [error.message for error in validator.iter_errors(payload)]


def source_hash(repo_root: Path, relative: str) -> str | None:
    path = repo_root / relative
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_registry(root: Path) -> dict[str, Any]:
    runtime = root / "schemas" / "runtime"
    registry_root = root / "core" / "node-architect"
    paths = {
        "nodes": registry_root / "node-registry.json",
        "scenarios": registry_root / "scenario-registry.json",
        "profiles": registry_root / "profile-registry.json",
        "rules": registry_root / "decision-rule-registry.json",
        "graph": registry_root / "runtime-graph-registry.json",
    }
    payloads = {name: load(path) for name, path in paths.items()}
    issues: list[str] = []

    schema_map = {
        "nodes": "node-registry.schema.json",
        "scenarios": "scenario-registry.schema.json",
        "profiles": "profile-registry.schema.json",
        "rules": "decision-rule-registry.schema.json",
        "graph": "runtime-graph.schema.json",
    }
    for name, schema_name in schema_map.items():
        issues.extend(
            f"{name}: {error}"
            for error in validate_schema(payloads[name], runtime / schema_name, runtime)
        )

    nodes = payloads["nodes"].get("nodes", [])
    node_ids = [node.get("id") for node in nodes]
    node_set = set(node_ids)
    if len(nodes) != 81:
        issues.append(f"node registry must materialize exactly 81 slots, got {len(nodes)}")
    if len(node_set) != len(node_ids):
        issues.append("node registry contains duplicate stable IDs")

    families = {family: 0 for family in FAMILIES}
    for node in nodes:
        family = node.get("family")
        if family not in families:
            issues.append(f"node {node.get('id')} has unknown family {family}")
        else:
            families[family] += 1
        if node.get("source_status") == "proposed_registry_slot" and node.get("maturity") == "stable":
            issues.append(f"proposed node {node.get('id')} cannot be stable")
        provenance = node.get("provenance", {})
        actual = source_hash(root, provenance.get("source_path", ""))
        if actual is None:
            issues.append(f"node {node.get('id')} provenance source is missing")
        elif actual != provenance.get("source_sha"):
            issues.append(f"node {node.get('id')} provenance SHA does not match source")

    if {family for family, count in families.items() if count} != FAMILIES:
        issues.append(f"node registry families are incomplete: {families}")
    explicit_nodes = {
        node.get("id")
        for node in nodes
        if node.get("source_status") == "canonical_explicit"
    }
    if explicit_nodes != EXPLICIT_NODES:
        issues.append("canonical explicit node set does not match the four source-backed KG nodes")
    if sum(node.get("source_status") == "proposed_registry_slot" for node in nodes) != 77:
        issues.append("node registry must classify exactly 77 proposed registry slots")

    rules = payloads["rules"].get("rules", [])
    rule_ids = {rule.get("id") for rule in rules}
    scenarios = payloads["scenarios"].get("scenarios", [])
    scenario_ids = [scenario.get("id") for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        issues.append("scenario registry contains duplicate stable IDs")
    if payloads["scenarios"].get("materialized_scenario_count") != len(scenarios):
        issues.append("materialized scenario count does not match scenario entries")
    if len(scenarios) != 14:
        issues.append(f"scenario registry must materialize exactly 14 scenarios, got {len(scenarios)}")
    if payloads["scenarios"].get("declared_scenario_count") != 116:
        issues.append("declared scenario count must remain 116 and separate from materialized entries")

    for scenario in scenarios:
        scenario_id = scenario.get("id")
        activation_facts = set(scenario.get("activation_facts", []))
        missing_rules = set(scenario.get("rules", [])) - rule_ids
        if missing_rules:
            issues.append(f"scenario {scenario_id} has unresolved rules {sorted(missing_rules)}")
        route_nodes = set(scenario.get("route_nodes", []))
        missing_nodes = route_nodes - node_set
        if missing_nodes:
            issues.append(f"scenario {scenario_id} has unresolved route nodes {sorted(missing_nodes)}")

        guards = scenario.get("guards", [])
        guard_ids = [guard.get("id") for guard in guards]
        if len(guard_ids) != len(set(guard_ids)):
            issues.append(f"scenario {scenario_id} has duplicate guard ids")
        for guard in guards:
            guard_id = guard.get("id")
            guard_type = guard.get("type")
            if guard_type not in GUARD_TYPES:
                issues.append(f"scenario {scenario_id} has unsupported guard type {guard_type}")
            if guard.get("field") not in activation_facts:
                issues.append(
                    f"scenario {scenario_id} guard {guard_id} field is not declared as an activation fact"
                )
            if guard_type == "in" and "values" not in guard:
                issues.append(f"scenario {scenario_id} guard {guard_id} requires values")
            if guard_type in {"equals", "gte", "lte"} and not {
                "value",
                "value_from_field",
            }.intersection(guard):
                issues.append(f"scenario {scenario_id} guard {guard_id} requires a comparison value")
            value_from_field = guard.get("value_from_field")
            if value_from_field is not None and value_from_field not in activation_facts:
                issues.append(
                    f"scenario {scenario_id} guard {guard_id} comparison field is not an activation fact"
                )

        policy = scenario.get("route_policy", {})
        start = policy.get("start_node")
        targets = set(policy.get("green_targets", []))
        if start not in node_set or start not in route_nodes:
            issues.append(f"scenario {scenario_id} has unresolved route-policy start node")
        if not targets or not targets <= node_set or not targets <= route_nodes:
            issues.append(f"scenario {scenario_id} has unresolved route-policy green target")
        if targets != set(scenario.get("green_targets", [])):
            issues.append(f"scenario {scenario_id} route-policy green targets drift from scenario targets")

        provenance = scenario.get("provenance", {})
        actual = source_hash(root, provenance.get("source_path", ""))
        if actual is None:
            issues.append(f"scenario {scenario_id} provenance source is missing")
        elif actual != provenance.get("source_sha"):
            issues.append(f"scenario {scenario_id} provenance SHA does not match source")

        for edge in scenario.get("edges", []):
            if edge.get("source") not in node_set or edge.get("target") not in node_set:
                issues.append(f"scenario {scenario_id} has an unresolved edge endpoint")
            edge_type = edge.get("edge_type")
            executable = edge.get("runtime_executable")
            if edge_type in VISUAL_EDGE_TYPES and executable:
                issues.append(f"scenario {scenario_id} marks a visual edge executable")
            if edge_type in RUNTIME_EDGE_TYPES and not executable:
                issues.append(f"scenario {scenario_id} marks a runtime edge non-executable")

    graph = payloads["graph"]
    graph_nodes = set(graph.get("nodes", []))
    if graph_nodes != node_set:
        issues.append("runtime graph node set must equal the canonical node registry")
    for edge in graph.get("edges", []):
        if edge.get("source") not in graph_nodes or edge.get("target") not in graph_nodes:
            issues.append("runtime graph contains an unresolved edge endpoint")
        edge_type = edge.get("edge_type")
        executable = edge.get("runtime_executable")
        if edge_type in VISUAL_EDGE_TYPES and executable:
            issues.append(f"visual-only edge {edge.get('source')}->{edge.get('target')} is executable")
        if edge_type in RUNTIME_EDGE_TYPES and not executable:
            issues.append(f"runtime edge {edge.get('source')}->{edge.get('target')} is not executable")

    profiles = payloads["profiles"].get("profiles", [])
    registry_ids = {
        payloads["nodes"].get("registry_id"),
        payloads["scenarios"].get("registry_id"),
        payloads["graph"].get("graph_id"),
    }
    for profile in profiles:
        refs = {
            profile.get("node_registry_ref"),
            profile.get("scenario_registry_ref"),
            profile.get("graph_registry_ref"),
        }
        if not refs.issubset(registry_ids):
            issues.append(f"profile {profile.get('id')} has unresolved registry reference")
        if len(profile.get("pilot_nodes", [])) != 3:
            issues.append(f"profile {profile.get('id')} must expose exactly three pilot nodes")
        if not set(profile.get("green_targets", [])) <= node_set:
            issues.append(f"profile {profile.get('id')} has unresolved green target")
        for route in profile.get("routes", []):
            if not set(route.get("nodes", [])) <= node_set:
                issues.append(
                    f"profile {profile.get('id')} route {route.get('route_id')} has unresolved node"
                )

    return {
        "outcome": "PASS" if not issues else "FAIL",
        "valid": not issues,
        "issues": issues,
        "counts": {
            "nodes": len(nodes),
            "proposed_nodes": sum(
                node.get("source_status") == "proposed_registry_slot" for node in nodes
            ),
            "explicit_nodes": sum(
                node.get("source_status") == "canonical_explicit" for node in nodes
            ),
            "materialized_scenarios": len(scenarios),
            "declared_scenarios": payloads["scenarios"].get("declared_scenario_count"),
            "graph_edges": len(graph.get("edges", [])),
            "profiles": len(profiles),
        },
        "registry_ids": sorted(registry_ids),
        "scenario_ids": sorted(scenario_ids),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    try:
        report = validate_registry(args.root.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"outcome": "FAIL", "valid": False, "issues": [str(exc)]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
