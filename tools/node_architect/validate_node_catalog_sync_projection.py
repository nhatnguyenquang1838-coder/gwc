#!/usr/bin/env python3
"""Validate the sync_projection controlled node catalog family and M4 runtime bindings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_COUNT = 9
FAMILY_PREFIX = "sync-projection-"
ALLOWED_FIELDS = {"node_id", "node_type", "title", "canonical", "authority_boundary", "gates", "description"}
REQUIRED_FIELDS = {"node_id", "node_type", "title", "canonical", "authority_boundary", "gates"}
ALLOWED_GATES = {"G2_EXECUTION", "G3_PR"}
REQUIRED_SEMANTICS = {
    "projection-source-authority-check",
    "projection-drift-detection",
    "projection-reconcile-readback",
    "projection-failure-routing",
    "projection-evidence-linking",
    "projection-privacy-boundary-check",
}
RUNTIME_BINDINGS = {
    "projection-source-authority-check": {
        "schema": "schemas/projection-source-authority-decision.schema.json",
        "evaluator": "tools/node_architect/projection_source_authority_check.py",
        "function": "decide_projection_source_authority",
        "artifact_type": "projection-source-authority-decision",
        "gates": ["G2_EXECUTION"],
    },
    "projection-evidence-linking": {
        "schema": "schemas/projection-evidence-linkset.schema.json",
        "evaluator": "tools/node_architect/projection_evidence_linking.py",
        "function": "build_projection_evidence_linkset",
        "artifact_type": "projection-evidence-linkset",
        "gates": ["G2_EXECUTION", "G3_PR"],
    },
    "projection-privacy-boundary-check": {
        "schema": "schemas/projection-privacy-decision.schema.json",
        "evaluator": "tools/node_architect/projection_privacy_boundary_check.py",
        "function": "decide_projection_privacy",
        "artifact_type": "projection-privacy-decision",
        "gates": ["G2_EXECUTION", "G3_PR"],
    },
    "external-audit-event-projection": {
        "schema": "schemas/external-audit-event-projection.schema.json",
        "evaluator": "tools/node_architect/external_audit_event_projection.py",
        "function": "project_external_audit_event",
        "artifact_type": "external-audit-event-projection",
        "gates": ["G2_EXECUTION", "G3_PR"],
    },
    "projection-drift-detection": {
        "schema": "schemas/projection-drift-decision.schema.json",
        "evaluator": "tools/node_architect/projection_drift_detection.py",
        "function": "detect_projection_drift",
        "artifact_type": "projection-drift-decision",
        "gates": ["G2_EXECUTION", "G3_PR"],
    },
}


def _repository_root(family_dir: Path) -> Path:
    resolved = family_dir.resolve()
    if len(resolved.parents) < 4:
        raise AssertionError(f"cannot resolve repository root from {family_dir}")
    return resolved.parents[3]


def _validate_runtime_binding(root: Path, family_dir: Path, stem: str, binding: dict[str, object]) -> None:
    descriptor_path = family_dir / f"{stem}.node.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    if descriptor["gates"] != binding["gates"]:
        raise AssertionError(f"{descriptor_path}: runtime-bound gates must be exactly {binding['gates']}")
    if descriptor["authority_boundary"] != "read_only":
        raise AssertionError(f"{descriptor_path}: runtime binding must remain read_only")

    schema_path = root / str(binding["schema"])
    evaluator_path = root / str(binding["evaluator"])
    if not schema_path.is_file():
        raise AssertionError(f"missing runtime schema: {schema_path}")
    if not evaluator_path.is_file():
        raise AssertionError(f"missing runtime evaluator: {evaluator_path}")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise AssertionError(f"{schema_path}: runtime schema must be a closed object")
    properties = schema.get("properties", {})
    if properties.get("schema_version", {}).get("const") != "1.0":
        raise AssertionError(f"{schema_path}: schema_version must be fixed to 1.0")
    if properties.get("artifact_type", {}).get("const") != binding["artifact_type"]:
        raise AssertionError(f"{schema_path}: artifact_type mismatch")
    for authority_field, expected in {
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }.items():
        if properties.get(authority_field, {}).get("const") is not expected:
            raise AssertionError(f"{schema_path}: {authority_field} must be const {expected}")

    evaluator_source = evaluator_path.read_text(encoding="utf-8")
    function_marker = f"def {binding['function']}("
    if function_marker not in evaluator_source:
        raise AssertionError(f"{evaluator_path}: missing {binding['function']}")


def validate_family(family_dir: Path, root: Path | None = None) -> None:
    if not family_dir.exists():
        raise AssertionError(f"missing family dir: {family_dir}")
    root = root or _repository_root(family_dir)

    node_files = sorted(family_dir.glob("*.node.json"))
    if len(node_files) != REQUIRED_COUNT:
        raise AssertionError(f"expected {REQUIRED_COUNT} nodes, found {len(node_files)}")

    seen: set[str] = set()
    covered_gates: set[str] = set()
    stems: set[str] = set()
    for path in node_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        extra = set(payload) - ALLOWED_FIELDS
        if extra:
            raise AssertionError(f"{path}: unexpected fields {sorted(extra)}")
        missing = REQUIRED_FIELDS - set(payload)
        if missing:
            raise AssertionError(f"{path}: missing fields {sorted(missing)}")

        stem = path.name.removesuffix(".node.json")
        stems.add(stem)
        expected_id = FAMILY_PREFIX + stem
        if payload["node_id"] != expected_id:
            raise AssertionError(f"{path}: node_id mismatch")
        if payload["node_id"] in seen:
            raise AssertionError(f"{path}: duplicate node_id")
        seen.add(payload["node_id"])

        if payload["canonical"] != "audit_projection":
            raise AssertionError(f"{path}: canonical must be audit_projection")
        if payload["authority_boundary"] != "read_only":
            raise AssertionError(f"{path}: audit projection authority must be read_only")
        gates = set(payload["gates"])
        if not gates or not gates.issubset(ALLOWED_GATES):
            raise AssertionError(f"{path}: gates must be a non-empty subset of {sorted(ALLOWED_GATES)}")
        covered_gates.update(gates)

    if covered_gates != ALLOWED_GATES:
        raise AssertionError(f"family must cover both applicability gates, got {sorted(covered_gates)}")
    missing_semantics = REQUIRED_SEMANTICS - stems
    if missing_semantics:
        raise AssertionError(f"missing required projection semantics: {sorted(missing_semantics)}")

    for stem, binding in RUNTIME_BINDINGS.items():
        if stem not in stems:
            raise AssertionError(f"runtime binding descriptor missing: {stem}")
        _validate_runtime_binding(root, family_dir, stem, binding)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-dir", type=Path, default=Path("core/node-architect/node-catalog/sync_projection"))
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        validate_family(args.family_dir, root=args.root)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: sync_projection node catalog family and runtime bindings are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
