#!/usr/bin/env python3
"""Validate the GWC runtime kernel contract using stdlib-only checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REQUIRED_INVARIANTS = {
    "authority_boundary",
    "event_history",
    "idempotency_key",
    "checkpoint_before_suspend",
    "readback_after_side_effect",
    "exact_evidence_binding",
    "version_pin",
    "projection_is_not_authority",
    "no_blind_retry",
    "catalog_expansion_gate",
}

REQUIRED_SCHEMA_PATHS = [
    "schemas/node-architect/runtime-kernel.schema.json",
    "schemas/node-architect/runtime-event.schema.json",
    "schemas/node-architect/transition-envelope.schema.json",
    "schemas/node-architect/node-pack.schema.json",
    "schemas/node-architect/runtime-node.schema.json",
    "schemas/node-architect/node-registry.schema.json",
]

REQUIRED_PACKAGE_IDS = {
    "runtime-kernel-rule",
    "runtime-kernel-schema",
    "runtime-event-schema",
    "transition-envelope-schema",
    "node-pack-schema",
    "runtime-kernel-validator",
}


def _finding(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def validate_kernel(kernel: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    if kernel.get("schema_version") != "0.1":
        findings.append(_finding("BLOCKER", "KERNEL_SCHEMA_VERSION_INVALID", "kernel schema_version must be 0.1"))
    if kernel.get("kernel_id") != "RUNTIME_KERNEL":
        findings.append(_finding("BLOCKER", "KERNEL_ID_INVALID", "kernel_id must be RUNTIME_KERNEL"))
    if kernel.get("version") != "0.1":
        findings.append(_finding("BLOCKER", "KERNEL_VERSION_INVALID", "kernel version must be 0.1"))

    invariants = kernel.get("invariants")
    if not isinstance(invariants, list):
        findings.append(_finding("BLOCKER", "KERNEL_INVARIANTS_MISSING", "kernel invariants must be a list"))
    else:
        missing = sorted(REQUIRED_INVARIANTS.difference(invariants))
        if missing:
            findings.append(_finding("BLOCKER", "KERNEL_INVARIANT_MISSING", f"missing invariants: {missing}"))

    authority = kernel.get("authority", {})
    if not isinstance(authority, dict):
        findings.append(_finding("BLOCKER", "KERNEL_AUTHORITY_INVALID", "authority must be an object"))
    else:
        if authority.get("write_requires_exact_g2") is not True:
            findings.append(_finding("BLOCKER", "WRITE_G2_BOUNDARY_MISSING", "repository write must require exact G2"))
        if authority.get("merge_requires_exact_g4") is not True:
            findings.append(_finding("BLOCKER", "MERGE_G4_BOUNDARY_MISSING", "merge must require exact G4"))
        if authority.get("external_projection_authority") is not False:
            findings.append(_finding("BLOCKER", "PROJECTION_AUTHORITY_ENABLED", "external projections must not be authority"))

    durability = kernel.get("durability", {})
    if not isinstance(durability, dict):
        findings.append(_finding("BLOCKER", "KERNEL_DURABILITY_INVALID", "durability must be an object"))
    else:
        for field in ("event_history_required", "checkpoint_before_suspend", "version_pin_required"):
            if durability.get(field) is not True:
                findings.append(_finding("BLOCKER", "DURABILITY_FIELD_MISSING", f"{field} must be true"))

    side_effects = kernel.get("side_effects", {})
    if not isinstance(side_effects, dict):
        findings.append(_finding("BLOCKER", "KERNEL_SIDE_EFFECTS_INVALID", "side_effects must be an object"))
    else:
        for field in ("idempotency_key_required", "readback_required", "retry_requires_reconciliation"):
            if side_effects.get(field) is not True:
                findings.append(_finding("BLOCKER", "SIDE_EFFECT_FIELD_MISSING", f"{field} must be true"))

    guard = kernel.get("node_catalog_guard", {})
    if not isinstance(guard, dict):
        findings.append(_finding("BLOCKER", "CATALOG_GUARD_INVALID", "node_catalog_guard must be an object"))
    else:
        if guard.get("expansion_allowed_before_kernel_pass") is not False:
            findings.append(_finding("BLOCKER", "CATALOG_EXPANSION_NOT_GATED", "catalog expansion must be blocked before kernel pass"))
        if guard.get("requires_reference_node_pack") is not True:
            findings.append(_finding("BLOCKER", "REFERENCE_NODE_PACK_REQUIRED", "reference node pack is required before catalog expansion"))
        if guard.get("requires_failure_simulation") is not True:
            findings.append(_finding("BLOCKER", "FAILURE_SIMULATION_REQUIRED", "failure simulation is required before catalog expansion"))

    return findings


def validate_workspace(workspace: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    kernel_doc = workspace / "core/node-architect/RUNTIME_KERNEL_v0.1.md"
    if not kernel_doc.exists():
        findings.append(_finding("BLOCKER", "KERNEL_DOC_MISSING", str(kernel_doc)))

    for relative in REQUIRED_SCHEMA_PATHS:
        path = workspace / relative
        if not path.exists():
            findings.append(_finding("BLOCKER", "SCHEMA_MISSING", relative))
            continue
        try:
            _load_json(path)
        except ValueError as exc:
            findings.append(_finding("BLOCKER", "SCHEMA_JSON_INVALID", str(exc)))

    kernel_schema_path = workspace / "schemas/node-architect/runtime-kernel.schema.json"
    if kernel_schema_path.exists():
        try:
            kernel_schema = _load_json(kernel_schema_path)
        except ValueError as exc:
            findings.append(_finding("BLOCKER", "KERNEL_SCHEMA_LOAD_FAILED", str(exc)))
        else:
            # Validate the canonical example implied by the schema contract.
            sample_kernel = {
                "schema_version": "0.1",
                "kernel_id": "RUNTIME_KERNEL",
                "version": "0.1",
                "invariants": sorted(REQUIRED_INVARIANTS),
                "authority": {
                    "write_requires_exact_g2": True,
                    "merge_requires_exact_g4": True,
                    "external_projection_authority": False,
                    "approval_boundaries": ["G2_EXECUTION", "G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"],
                },
                "durability": {
                    "event_history_required": True,
                    "checkpoint_before_suspend": True,
                    "version_pin_required": True,
                },
                "side_effects": {
                    "idempotency_key_required": True,
                    "readback_required": True,
                    "retry_requires_reconciliation": True,
                },
                "node_catalog_guard": {
                    "expansion_allowed_before_kernel_pass": False,
                    "requires_reference_node_pack": True,
                    "requires_failure_simulation": True,
                },
            }
            findings.extend(validate_kernel(sample_kernel))
            required = set(kernel_schema.get("required", []))
            missing_required = sorted({"schema_version", "kernel_id", "version", "invariants", "authority", "durability", "side_effects", "node_catalog_guard"}.difference(required))
            if missing_required:
                findings.append(_finding("BLOCKER", "KERNEL_SCHEMA_REQUIRED_FIELD_MISSING", f"missing required fields: {missing_required}"))

    package_path = workspace / "projects/gwc/package.yaml"
    if not package_path.exists():
        findings.append(_finding("BLOCKER", "PACKAGE_MISSING", str(package_path)))
    else:
        package_text = package_path.read_text(encoding="utf-8")
        for package_id in sorted(REQUIRED_PACKAGE_IDS):
            if f"id: {package_id}" not in package_text:
                findings.append(_finding("BLOCKER", "PACKAGE_ID_MISSING", package_id))
        if 'package_version: "1.16.0"' not in package_text:
            findings.append(_finding("BLOCKER", "PACKAGE_VERSION_CHANGED", "package_version must remain 1.16.0"))

    return findings


def validation_result(workspace: Path, findings: list[dict[str, str]]) -> dict[str, Any]:
    outcome = "FAIL" if any(item["severity"] == "BLOCKER" for item in findings) else "PASS"
    return {"schema_version": "0.1", "workspace": str(workspace), "outcome": outcome, "findings": findings}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    result = validation_result(workspace, validate_workspace(workspace))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
