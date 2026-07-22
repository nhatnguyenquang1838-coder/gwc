#!/usr/bin/env python3
"""Validate the GWC failure simulation scale-readiness matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

MATRIX_PATH = Path("core/node-architect/failure-simulation-matrix.json")
SCHEMA_PATH = Path("schemas/node-architect/failure-simulation-matrix.schema.json")
REQUIRED_CASE_IDS = {
    "unknown_write_result_reconciles_before_retry",
    "cas_mismatch_reloads_checkpoint",
    "lease_expired_stops_or_reacquires",
    "approval_expired_regenerates_request",
    "duplicate_agent_blocked_by_lease",
    "node_version_drift_pins_or_restarts",
}
FORBIDDEN_BEHAVIOR_MINIMUM = 1
EVIDENCE_MINIMUM = 1


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_schema(schema: dict) -> list[str]:
    errors: list[str] = []
    required = set(schema.get("required", []))
    for key in ("schema_version", "matrix_id", "scale_81_nodes_allowed", "required_cases"):
        if key not in required:
            errors.append(f"schema missing required field: {key}")
    scale_property = schema.get("properties", {}).get("scale_81_nodes_allowed", {})
    if scale_property.get("const") is not False:
        errors.append("schema must keep scale_81_nodes_allowed const false")
    cases = schema.get("properties", {}).get("required_cases", {})
    if cases.get("minItems", 0) < len(REQUIRED_CASE_IDS):
        errors.append("schema required_cases minItems must cover all required cases")
    return errors


def validate_matrix(matrix: dict) -> list[str]:
    errors: list[str] = []
    if matrix.get("scale_81_nodes_allowed") is not False:
        errors.append("scale_81_nodes_allowed must remain false before failure proof")
    cases = matrix.get("required_cases", [])
    case_ids = {case.get("case_id") for case in cases}
    missing = REQUIRED_CASE_IDS - case_ids
    extra = case_ids - REQUIRED_CASE_IDS
    if missing:
        errors.append(f"missing required cases: {sorted(missing)}")
    if extra:
        errors.append(f"unexpected cases: {sorted(extra)}")
    for case in cases:
        case_id = case.get("case_id", "<unknown>")
        if not case.get("trigger"):
            errors.append(f"{case_id}: trigger required")
        if not case.get("expected_response"):
            errors.append(f"{case_id}: expected_response required")
        if len(case.get("forbidden_behaviors", [])) < FORBIDDEN_BEHAVIOR_MINIMUM:
            errors.append(f"{case_id}: forbidden_behaviors required")
        if len(case.get("evidence_required", [])) < EVIDENCE_MINIMUM:
            errors.append(f"{case_id}: evidence_required required")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    errors: list[str] = []
    if not (root / MATRIX_PATH).exists():
        errors.append(f"missing {MATRIX_PATH}")
    if not (root / SCHEMA_PATH).exists():
        errors.append(f"missing {SCHEMA_PATH}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    errors.extend(validate_schema(load_json(root / SCHEMA_PATH)))
    errors.extend(validate_matrix(load_json(root / MATRIX_PATH)))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Failure simulation matrix validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
