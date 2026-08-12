#!/usr/bin/env python3
"""Validate the package_export controlled node catalog family."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

REQUIRED_COUNT = 9
FAMILY_PREFIX = "package_export."
ALLOWED_FIELDS = {
    "node_id", "node_type", "title", "canonical", "authority_boundary", "gates",
    "description", "intent", "outcome", "constraints", "exclusions",
    "entry_guards", "source_resolution", "reason_codes", "provenance",
}
REQUIRED_FIELDS = {"node_id", "node_type", "title", "canonical", "authority_boundary", "gates"}
ALLOWED_GATES = {"G2_EXECUTION", "G3_PR"}
REQUIRED_SEMANTICS = {
    "package-manifest-load", "entry-schema-validation", "source-path-safety-check",
    "target-path-safety-check", "governance-tree-build", "export-manifest-generation",
    "deterministic-hash-verification", "smoke-verification", "export-failure-routing",
}
ENFORCE_ENRICHED = {"entry-schema-validation", "package-manifest-load"}
REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Runtime contracts for package_export nodes that carry evaluator + schema bindings.
RUNTIME_CONTRACTS: dict[str, dict[str, str]] = {
    "package_export.entry-schema-validation": {
        "artifact_type": "entry-schema-validation",
        "schema": "schemas/node-architect/package-export/entry-schema-validation.schema.json",
        "evaluator": "tools/node_architect/package_export/entry_schema_validation.py",
        "test": "tests/test_package_export_entry_schema_validation.py",
    },
    "package_export.package-manifest-load": {
        "artifact_type": "package-manifest-load",
        "schema": "schemas/node-architect/package-export/package-manifest-load.schema.json",
        "evaluator": "tools/node_architect/package_export/package_manifest_load.py",
        "test": "tests/package_export/test_package_manifest_load.py",
    },
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_family(family_dir: Path, *, root: Path | None = None) -> list[str]:
    """Validate the package_export node catalog family.

    Returns a list of error strings (empty list means PASS), mirroring the
    intake_context validator's fail-closed contract.
    """
    if root is None:
        root = family_dir.parent.parent.parent
    errors: list[str] = []

    if not family_dir.exists():
        return ["missing family dir: " + str(family_dir)]

    node_files = sorted(family_dir.glob("*.node.json"))
    if len(node_files) != REQUIRED_COUNT:
        errors.append(f"expected {REQUIRED_COUNT} nodes, found {len(node_files)}")

    seen: set[str] = set()
    covered_gates: set[str] = set()
    stems: set[str] = set()

    for path in node_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue

        extra = set(payload) - ALLOWED_FIELDS
        if extra:
            errors.append(f"{path}: unexpected fields {sorted(extra)}")

        missing = REQUIRED_FIELDS - set(payload)
        if missing:
            errors.append(f"{path}: missing fields {sorted(missing)}")

        stem = path.name.removesuffix(".node.json")
        expected_id = FAMILY_PREFIX + stem
        if payload.get("node_id") != expected_id:
            errors.append(f"{path}: node_id mismatch — expected {expected_id!r}, got {payload.get('node_id')!r}")

        node_id = payload.get("node_id", "")
        if node_id in seen:
            errors.append(f"{path}: duplicate node_id {node_id!r}")
        seen.add(node_id)

        stems.add(stem)

        if payload.get("canonical") != "delivery_evidence":
            errors.append(f"{path}: canonical must be delivery_evidence")
        if payload.get("authority_boundary") != "g2_required":
            errors.append(f"{path}: authority_boundary must be g2_required")

        gates = set(payload.get("gates", []))
        if not gates or not gates.issubset(ALLOWED_GATES):
            errors.append(f"{path}: gates must be a non-empty subset of {sorted(ALLOWED_GATES)}")
        covered_gates.update(gates)

        # Enriched nodes must carry maturity fields.
        if stem in ENFORCE_ENRICHED:
            for field in ("intent", "outcome", "constraints", "exclusions", "entry_guards", "reason_codes"):
                if not payload.get(field):
                    errors.append(f"{path}: enriched node missing required field {field!r}")
            source_res = payload.get("source_resolution", {})
            if not isinstance(source_res, Mapping) or not source_res.get("evaluator") or not source_res.get("schema"):
                errors.append(f"{path}: enriched node missing source_resolution.evaluator and source_resolution.schema")
            reason_codes = payload.get("reason_codes", {})
            if isinstance(reason_codes, Mapping) and reason_codes:
                for code in reason_codes:
                    if not REASON_CODE_PATTERN.match(str(code)):
                        errors.append(f"{path}: reason code {code!r} does not match closed taxonomy pattern")

    if covered_gates != ALLOWED_GATES:
        errors.append(f"family must cover both gates, got {sorted(covered_gates)}")

    missing_semantics = REQUIRED_SEMANTICS - stems
    if missing_semantics:
        errors.append(f"missing required package export semantics: {sorted(missing_semantics)}")

    return errors


def validate_runtime_contracts(root: Path) -> list[str]:
    """Validate that every RUNTIME_CONTRACTS entry has a reachable schema and evaluator."""
    errors: list[str] = []
    for node_id, contract in RUNTIME_CONTRACTS.items():
        schema_path = root / contract["schema"]
        evaluator_path = root / contract["evaluator"]
        test_path = root / contract["test"]

        if not schema_path.is_file():
            errors.append(f"runtime contract {node_id}: schema missing at {contract['schema']}")
        if not evaluator_path.is_file():
            errors.append(f"runtime contract {node_id}: evaluator missing at {contract['evaluator']}")
        else:
            text = evaluator_path.read_text(encoding="utf-8")
            callable_match = re.search(r"^def (\w+)\(", text, re.MULTILINE)
            if not callable_match:
                errors.append(f"runtime contract {node_id}: evaluator has no top-level callable")
        if not test_path.is_file():
            errors.append(f"runtime contract {node_id}: test missing at {contract['test']}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-dir", type=Path,
                        default=Path("core/node-architect/node-catalog/package_export"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--runtime-contracts", action="store_true",
                        help="Also validate RUNTIME_CONTRACTS schema/evaluator bindings")
    args = parser.parse_args(argv)

    errors = validate_family(args.family_dir, root=args.root)
    if args.runtime_contracts:
        errors.extend(validate_runtime_contracts(args.root))

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    print("PASS: package_export node catalog family is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
