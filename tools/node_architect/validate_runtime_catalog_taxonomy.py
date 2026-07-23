#!/usr/bin/env python3
"""Validate the canonical GWC runtime catalog taxonomy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "schemas" / "node-architect" / "runtime-catalog-taxonomy.schema.json"
EXPECTED_FAMILIES = {
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


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("taxonomy", type=Path)
    args = parser.parse_args(argv)

    taxonomy = load_json(args.taxonomy)
    schema = load_json(SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = [error.message for error in Draft202012Validator(schema).iter_errors(taxonomy)]

    families = {item["id"] for item in taxonomy.get("families", [])}
    if families != EXPECTED_FAMILIES:
        errors.append("family set must remain exactly the canonical nine families")
    if sum(item.get("node_count", 0) for item in taxonomy.get("families", [])) != 81:
        errors.append("family node counts must sum to exactly 81")
    terms = set(taxonomy.get("canonical_terms", []))
    required_terms = {"Gate", "Capability Family", "Runtime Node", "Edge Scenario", "Artifact"}
    if not required_terms.issubset(terms):
        errors.append("canonical terms are incomplete")

    if errors:
        print("RUNTIME CATALOG TAXONOMY VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("RUNTIME CATALOG TAXONOMY VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
