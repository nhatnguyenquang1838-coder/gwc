#!/usr/bin/env python3
"""Final canonical-81 shadow qualification across routes, gates, replay, and safety."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.node_architect.gate_node_routes import build_route_coverage
from tools.node_architect.node_executability import validate_canonical_coverage
from tools.node_architect.shadow_adapters import build_adapter_registry
from tools.node_architect.shadow_orchestrator import run_shadow_event

REPLAY_CASES = (
    ("g0-standard", "G0_CONTEXT", "standard_pr_delivery"),
    ("g1-standard", "G1_ALIGNMENT", "standard_pr_delivery"),
    ("g2-standard", "G2_EXECUTION", "standard_pr_delivery"),
    ("g3-standard", "G3_PR", "standard_pr_delivery"),
    ("g2-approval", "G2_EXECUTION", "approval_wait_resume"),
    ("g5-ci-recovery", "G5_DEPLOY", "ci_failure"),
    ("projection", "READ_ONLY_PROJECTION", "projection"),
    ("g2-package", "G2_EXECUTION", "package_export"),
    ("g3-scale", "G3_PR", "scale_control"),
    ("g5-scale", "G5_DEPLOY", "scale_control"),
)
GATE_BOUNDARIES = (
    ("g4-boundary", "G4_MERGE", "standard_pr_delivery"),
    ("g6-boundary", "G6_PRODUCTION_DATA", "standard_pr_delivery"),
)
GATE_ORDER = (
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION_DATA",
)


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _event(case_id: str, gate: str, scenario: str, revision: str) -> dict[str, Any]:
    return {
        "task_id": "SCRUM-592",
        "run_id": f"e0-{case_id}",
        "gate": gate,
        "exact_revision": revision,
        "scenario": scenario,
        "input_payload": {"qualification_case": case_id},
    }


def _semantic_source(root: Path, node: dict[str, Any]) -> dict[str, Any]:
    provenance = node.get("provenance") if isinstance(node.get("provenance"), dict) else {}
    descriptor_path = provenance.get("source_path")
    descriptor: dict[str, Any] | None = None
    if isinstance(descriptor_path, str) and (root / descriptor_path).is_file():
        try:
            loaded = json.loads((root / descriptor_path).read_text(encoding="utf-8"))
            descriptor = loaded if isinstance(loaded, dict) else None
        except (OSError, json.JSONDecodeError):
            descriptor = None
    if isinstance(descriptor, dict):
        resolution = descriptor.get("source_resolution")
        if isinstance(resolution, dict):
            evaluator = resolution.get("evaluator")
            if isinstance(evaluator, str) and (root / evaluator).is_file():
                return {"status": "SOURCE_RESOLVED_EVALUATOR", "path": evaluator}
    node_id = str(node.get("id", ""))
    slug = node_id.split(".", 1)[-1].replace("-", "_")
    candidate = f"tools/node_architect/{slug}.py"
    if (root / candidate).is_file():
        return {"status": "NAMED_TOOL_PRESENT", "path": candidate}
    return {"status": "DESCRIPTOR_ONLY", "path": descriptor_path}


def build_qualification_report(
    registry: dict[str, Any],
    activation: dict[str, Any],
    *,
    revision: str,
    root: Path | None = None,
    live_observed_node_ids: set[str] | None = None,
) -> dict[str, Any]:
    root = (root or Path(".")).resolve()
    observed = set(live_observed_node_ids or set())
    errors = list(validate_canonical_coverage(registry))
    adapters = build_adapter_registry(registry)
    route_rows = build_route_coverage(registry)
    route_by = {row["node_id"]: row for row in route_rows}
    by_id = {node.get("id"): node for node in registry.get("nodes", []) if isinstance(node, dict)}

    if len(adapters) != 81:
        errors.append("CANONICAL_81_ADAPTER_COVERAGE_MISMATCH")
    if any(not row.get("route_bound") for row in route_rows):
        errors.append("CANONICAL_81_ROUTE_COVERAGE_GAP")

    replayed: set[str] = set()
    replay_runs: list[dict[str, Any]] = []
    safe = True
    deterministic = True
    gate_matrix: dict[str, dict[str, Any]] = {
        gate: {"status": "UNSEEN", "selected_node_count": 0} for gate in GATE_ORDER
    }

    for case_id, gate, scenario in REPLAY_CASES:
        event = _event(case_id, gate, scenario, revision)
        first = run_shadow_event(event, registry, activation, observed_revision=revision)
        second = run_shadow_event(event, registry, activation, observed_revision=revision)
        if first != second:
            deterministic = False
            errors.append(f"REPLAY_NON_DETERMINISTIC:{case_id}")
        if first.get("status") != "SHADOW_EXECUTED":
            errors.append(f"REPLAY_NOT_EXECUTED:{case_id}")
        selected: list[str] = []
        for result in first.get("results", []):
            if not isinstance(result, dict):
                safe = False
                continue
            node_id = result.get("node_id")
            if isinstance(node_id, str):
                replayed.add(node_id)
                selected.append(node_id)
            if result.get("authority_granted") is not False or result.get("executed_effects") != []:
                safe = False
        if gate in gate_matrix and selected:
            gate_matrix[gate] = {
                "status": "SELECTED",
                "selected_node_count": len(selected),
                "case_id": case_id,
            }
        replay_runs.append(
            {
                "case_id": case_id,
                "gate": gate,
                "scenario": scenario,
                "route_pack": first.get("route_pack"),
                "selected_node_ids": selected,
                "output_digest": _digest(first),
            }
        )

    for case_id, gate, scenario in GATE_BOUNDARIES:
        output = run_shadow_event(
            _event(case_id, gate, scenario, revision),
            registry,
            activation,
            observed_revision=revision,
        )
        count = int(output.get("selected_node_count", 0) or 0)
        if count != 0:
            errors.append(f"BOUNDARY_UNEXPECTED_NODE_SELECTION:{gate}")
        gate_matrix[gate] = {
            "status": "TYPED_NON_APPLICABLE",
            "selected_node_count": 0,
            "case_id": case_id,
            "route_pack": output.get("route_pack"),
        }

    if any(gate_matrix[gate]["status"] == "UNSEEN" for gate in GATE_ORDER):
        errors.append("GATE_MATRIX_UNSEEN_GATE")
    if replayed != set(by_id):
        errors.append("CANONICAL_81_REPLAY_COVERAGE_GAP")
    if not safe:
        errors.append("SHADOW_SAFETY_INVARIANT_VIOLATION")

    kill_switch = dict(activation)
    kill_switch["kill_switch_engaged"] = True
    probe = _event("kill-switch", "G3_PR", "standard_pr_delivery", revision)
    kill_output = run_shadow_event(probe, registry, kill_switch, observed_revision=revision)
    drift_output = run_shadow_event(probe, registry, activation, observed_revision="drifted-" + revision)
    unknown_output = run_shadow_event(
        _event("unknown", "G3_PR", "unknown_scenario", revision),
        registry,
        activation,
        observed_revision=revision,
    )
    adversarial_checks = {
        "kill_switch_fail_closed": kill_output.get("reason_code") == "SHADOW_KILL_SWITCH_ENGAGED",
        "revision_drift_fail_closed": drift_output.get("reason_code") == "SHADOW_REVISION_DRIFT",
        "unknown_scenario_typed": unknown_output.get("status") == "SHADOW_NO_APPLICABLE_ROUTE",
        "deterministic_replay": deterministic,
        "zero_authority_or_executed_effects": safe,
        "baseline_exactly_81": not validate_canonical_coverage(registry),
    }
    if not all(adversarial_checks.values()):
        errors.append("ADVERSARIAL_CHECK_FAILED")

    records: list[dict[str, Any]] = []
    for node_id, node in sorted(by_id.items()):
        route = route_by.get(node_id, {})
        semantic = _semantic_source(root, node)
        adapter_bound = node_id in adapters
        route_bound = bool(route.get("route_bound"))
        replay_proven = node_id in replayed
        observed_live = node_id in observed
        if observed_live:
            level = "E5_OBSERVED"
        elif replay_proven:
            level = "E4_REPLAY_PROVEN"
        elif route_bound:
            level = "E3_ROUTE_BOUND"
        elif adapter_bound:
            level = "E2_ADAPTER_BOUND"
        else:
            level = "E1_INSTRUCTION_READY"
        records.append(
            {
                "node_id": node_id,
                "family": node.get("family"),
                "maturity": node.get("maturity"),
                "node_version": node.get("version"),
                "executability_level": level,
                "adapter_bound": adapter_bound,
                "route_bound": route_bound,
                "route_packs": route.get("route_packs", []),
                "gates": route.get("gates", []),
                "replay_proven": replay_proven,
                "observed_live": observed_live,
                "shadow_enabled": adapter_bound and route_bound and replay_proven,
                "semantic_source": semantic,
                "authoritative_candidate": semantic["status"] != "DESCRIPTOR_ONLY",
            }
        )

    summary = {
        "canonical_node_count": len(records),
        "adapter_bound_count": sum(record["adapter_bound"] for record in records),
        "route_bound_count": sum(record["route_bound"] for record in records),
        "replay_proven_count": sum(record["replay_proven"] for record in records),
        "observed_live_count": sum(record["observed_live"] for record in records),
        "shadow_enabled_count": sum(record["shadow_enabled"] for record in records),
        "semantic_source_resolved_count": sum(
            record["semantic_source"]["status"] != "DESCRIPTOR_ONLY" for record in records
        ),
        "descriptor_only_count": sum(
            record["semantic_source"]["status"] == "DESCRIPTOR_ONLY" for record in records
        ),
    }
    report: dict[str, Any] = {
        "artifact_type": "canonical-81-shadow-qualification",
        "schema_version": "1.0",
        "status": "PASS" if not errors else "FAIL",
        "exact_revision": revision,
        "summary": summary,
        "gate_matrix": gate_matrix,
        "adversarial_checks": adversarial_checks,
        "records": records,
        "replay_runs": replay_runs,
        "errors": sorted(set(errors)),
    }
    report["qualification_digest"] = _digest(report)
    return report
