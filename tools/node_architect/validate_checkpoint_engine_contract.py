#!/usr/bin/env python3
"""Validate the checkpoint runtime engine contract and schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

DOC_PATH = Path("core/node-architect/CHECKPOINT_RUNTIME_ENGINE_CONTRACT_v0.1.md")
SCHEMA_PATH = Path("schemas/node-architect/checkpoint-engine.schema.json")
REQUIRED_INVARIANTS = (
    "cas_required",
    "lease_required",
    "reconcile_before_retry",
    "checkpoint_before_suspend",
    "no_false_pass",
)
REQUIRED_DOC_PHRASES = (
    "CAS required",
    "Lease required",
    "Reconcile before retry",
    "Checkpoint before suspend",
    "No false pass",
)
REQUIRED_STATE_FIELDS = (
    "run_id",
    "checkpoint_id",
    "checkpoint_revision",
    "lease_owner",
    "lease_expires_at_utc",
    "current_node_id",
    "current_node_version",
    "pending_action",
    "last_reconciled_at_utc",
    "next_node_id",
    "status",
)
REQUIRED_FAILURES = (
    "CAS mismatch",
    "expired lease",
    "unknown write result",
    "node version drift",
    "stale approval",
    "live state mismatch",
)


def load_schema(root: Path) -> dict:
    with (root / SCHEMA_PATH).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_schema(schema: dict) -> list[str]:
    errors: list[str] = []
    required = set(schema.get("required", []))
    for key in ("schema_version", "engine_id", "required_phases", "invariants", "state_fields", "failure_routes", "authority_boundaries"):
        if key not in required:
            errors.append(f"schema missing required field: {key}")

    invariants = schema.get("properties", {}).get("invariants", {})
    invariant_required = set(invariants.get("required", []))
    invariant_properties = invariants.get("properties", {})
    for invariant in REQUIRED_INVARIANTS:
        if invariant not in invariant_required:
            errors.append(f"schema invariants missing required: {invariant}")
        if invariant_properties.get(invariant, {}).get("const") is not True:
            errors.append(f"schema invariant {invariant} must be const true")
    return errors


def validate_doc(text: str) -> list[str]:
    errors: list[str] = []
    for phrase in REQUIRED_DOC_PHRASES:
        if phrase not in text:
            errors.append(f"contract missing phrase: {phrase}")
    for field in REQUIRED_STATE_FIELDS:
        if field not in text:
            errors.append(f"contract missing state field: {field}")
    for failure in REQUIRED_FAILURES:
        if failure not in text:
            errors.append(f"contract missing failure route: {failure}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    errors: list[str] = []
    if not (root / DOC_PATH).exists():
        errors.append(f"missing {DOC_PATH}")
    if not (root / SCHEMA_PATH).exists():
        errors.append(f"missing {SCHEMA_PATH}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    schema = load_schema(root)
    text = (root / DOC_PATH).read_text(encoding="utf-8")
    errors.extend(validate_schema(schema))
    errors.extend(validate_doc(text))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Checkpoint runtime engine contract validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
