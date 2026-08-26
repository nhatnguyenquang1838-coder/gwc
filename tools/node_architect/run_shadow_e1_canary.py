#!/usr/bin/env python3
"""Exercise all route packs and G0-G6 boundaries as an exact-head E1 canary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.node_architect.shadow_orchestrator import run_shadow_event
from tools.node_architect.shadow_telemetry import append_telemetry, build_telemetry_event

CANARY_CASES = (
    ("RP-01", "G3_PR", "standard_pr_delivery"),
    ("RP-02", "G2_EXECUTION", "approval_wait_resume"),
    ("RP-03", "G5_DEPLOY", "ci_failure"),
    ("RP-04", "READ_ONLY_PROJECTION", "projection"),
    ("RP-05", "G2_EXECUTION", "package_export"),
    ("RP-06", "G5_DEPLOY", "scale_control"),
)
BOUNDARIES = (
    ("G0_CONTEXT", "standard_pr_delivery"),
    ("G1_ALIGNMENT", "standard_pr_delivery"),
    ("G4_MERGE", "standard_pr_delivery"),
    ("G6_PRODUCTION_DATA", "standard_pr_delivery"),
)


def load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def run_canary(
    registry: dict,
    activation: dict,
    *,
    revision: str,
    ledger: Path,
) -> dict:
    results: list[dict] = []
    packs: set[str] = set()
    gates: set[str] = set()
    safe = True
    cases = list(CANARY_CASES) + [(None, gate, scenario) for gate, scenario in BOUNDARIES]
    for expected_pack, gate, scenario in cases:
        event = {
            "task_id": "SCRUM-592",
            "run_id": f"e1-canary-{gate}-{scenario}",
            "gate": gate,
            "exact_revision": revision,
            "route_graph_revision": f"repo-bound:{revision}",
            "scenario": scenario,
            "input_payload": {"canary": True},
        }
        output = run_shadow_event(event, registry, activation, observed_revision=revision)
        selected: list[str] = []
        route_pack = output.get("route_pack")
        if isinstance(route_pack, str):
            packs.add(route_pack)
        gates.add(gate)
        if expected_pack and route_pack != expected_pack:
            safe = False
        for item in output.get("results", []):
            if item.get("authority_granted") is not False or item.get("executed_effects") != []:
                safe = False
            selected.append(item.get("node_id"))
            telemetry = build_telemetry_event(
                item,
                route_pack=route_pack,
                graph_revision=f"repo-bound:{revision}",
            )
            append_telemetry(ledger, telemetry)
        results.append(
            {
                "gate": gate,
                "scenario": scenario,
                "route_pack": route_pack,
                "selected_node_count": len(selected),
                "selected_node_ids": selected,
            }
        )
    required_packs = {item[0] for item in CANARY_CASES}
    required_gates = {
        "G0_CONTEXT",
        "G1_ALIGNMENT",
        "G2_EXECUTION",
        "G3_PR",
        "G4_MERGE",
        "G5_DEPLOY",
        "G6_PRODUCTION_DATA",
    }
    status = "PASS" if safe and required_packs <= packs and required_gates <= gates else "FAIL"
    return {
        "artifact_type": "shadow-e1-canary",
        "status": status,
        "exact_revision": revision,
        "route_packs_seen": sorted(packs),
        "gates_seen": sorted(gates),
        "safe": safe,
        "cases": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    report = run_canary(
        load(root / "core/node-architect/node-registry.json"),
        load(root / "core/node-architect/shadow-runtime-activation.json"),
        revision=args.revision,
        ledger=args.ledger,
    )
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "route_packs_seen": report["route_packs_seen"],
                "gates_seen": report["gates_seen"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
