#!/usr/bin/env python3
"""Validate catalog, project packages, schemas, references, and canonical hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


CANONICAL_SHA = "04cd33bbaff66f44917199e6bbb8355a1e956edb9c474e6c8e664ed8d0ed41c1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_json_schema(instance: Any, schema_path: Path, label: str) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        location = ".".join(str(item) for item in error.path) or "<root>"
        errors.append(f"{label}:{location}: {error.message}")
    return errors


def ensure_relative_safe(path_value: str, label: str) -> list[str]:
    candidate = Path(path_value)
    errors = []
    if candidate.is_absolute():
        errors.append(f"{label}: absolute path is forbidden: {path_value}")
    if ".." in candidate.parts:
        errors.append(f"{label}: parent traversal is forbidden: {path_value}")
    if "\\" in path_value:
        errors.append(f"{label}: Windows backslash is forbidden: {path_value}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None,
                        help="Repository root; defaults to the parent of tools/")
    parser.add_argument("--project", default=None,
                        help="Validate only one catalog project")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    errors: list[str] = []
    warnings: list[str] = []

    required = [
        "README.md", "AGENTS.md", "catalog.yaml",
        "core/Coding_Project_Governance_v1.0.md",
        "core/E2E_DRAFT_PR_DELIVERY_RULE.md",
        "schemas/instruction.schema.json",
        "schemas/project-package.schema.json",
        "schemas/rollout.schema.json",
        "schemas/approval-envelope.schema.json",
        "schemas/g0-context-snapshot.schema.json",
        "schemas/g01-runtime-input.schema.json",
        "schemas/g01-decision-input.schema.json",
        "schemas/g1-intake-brief.schema.json",
        "schemas/g1-preflight-report.schema.json",
        "schemas/g1-options.schema.json",
        "schemas/g1-decision-record.schema.json",
        "tools/validate_g01.py",
        "tools/generate_g01_runtime.py",
        "tools/capture_g01_decision.py",
        "docs/g01-lifecycle.md",
        "templates/g01/g0-context-snapshot.template.yaml",
        "templates/g01/g01-runtime-input.template.yaml",
        "templates/g01/g01-decision-input.template.yaml",
        "templates/g01/g1-intake-brief.template.yaml",
        "templates/g01/g1-preflight-report.template.yaml",
        "templates/g01/g1-options.template.yaml",
        "templates/g01/g1-decision-record.template.yaml",
        "tests/test_g01_lifecycle.py",
        "tests/test_g01_runtime.py",
        "tests/test_g01_decision_capture.py",
    ]
    for rel in required:
        if not (root / rel).is_file():
            errors.append(f"missing required file: {rel}")

    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors))
        return 1

    core = root / "core/Coding_Project_Governance_v1.0.md"
    actual_core_sha = sha256(core)
    if actual_core_sha != CANONICAL_SHA:
        errors.append(
            f"canonical policy hash mismatch: expected {CANONICAL_SHA}, "
            f"got {actual_core_sha}"
        )

    # Ensure every schema is valid JSON and itself recognized as a JSON Schema.
    for schema_path in sorted((root / "schemas").glob("*.json")):
        try:
            schema = load_json(schema_path)
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            errors.append(f"invalid schema {schema_path.relative_to(root)}: {exc}")

    try:
        catalog = load_yaml(root / "catalog.yaml")
    except Exception as exc:
        errors.append(f"catalog.yaml cannot be parsed: {exc}")
        catalog = {}

    if not isinstance(catalog, dict):
        errors.append("catalog.yaml must contain an object")
        catalog = {}

    declared_sha = (
        catalog.get("canonical_policy", {}).get("sha256")
        if isinstance(catalog.get("canonical_policy"), dict)
        else None
    )
    if declared_sha != CANONICAL_SHA:
        errors.append("catalog canonical policy SHA does not match the required SHA")

    projects = catalog.get("projects", {})
    if not isinstance(projects, dict) or not projects:
        errors.append("catalog must declare at least one project")
        projects = {}

    if args.project:
        if args.project not in projects:
            errors.append(f"project not found in catalog: {args.project}")
            projects = {}
        else:
            projects = {args.project: projects[args.project]}

    package_schema = root / "schemas/project-package.schema.json"
    referenced_targets: dict[tuple[str, str], str] = {}

    for project_id, entry in projects.items():
        if not isinstance(entry, dict):
            errors.append(f"catalog project {project_id} must be an object")
            continue
        package_rel = entry.get("package")
        if not isinstance(package_rel, str):
            errors.append(f"catalog project {project_id} has no package path")
            continue
        errors.extend(ensure_relative_safe(package_rel, f"{project_id}.package"))
        package_path = root / package_rel
        if not package_path.is_file():
            errors.append(f"missing package for {project_id}: {package_rel}")
            continue
        try:
            package = load_yaml(package_path)
        except Exception as exc:
            errors.append(f"cannot parse {package_rel}: {exc}")
            continue

        errors.extend(validate_json_schema(
            package, package_schema, f"package:{project_id}"
        ))

        if package.get("project_id") != project_id:
            errors.append(
                f"package project_id mismatch: catalog={project_id}, "
                f"package={package.get('project_id')}"
            )

        profile_rel = package.get("profile")
        if isinstance(profile_rel, str):
            errors.extend(ensure_relative_safe(profile_rel, f"{project_id}.profile"))
            if not (root / profile_rel).is_file():
                errors.append(f"missing profile for {project_id}: {profile_rel}")
        else:
            errors.append(f"package {project_id} has no profile")

        delivery = package.get("delivery", {})
        if isinstance(delivery, dict):
            write_enabled = delivery.get("write_enabled")
            identity = delivery.get("identity_status")
            target_repo = delivery.get("target_repository")
            mode = delivery.get("mode")
            if write_enabled and identity != "verified":
                errors.append(
                    f"{project_id}: write_enabled requires identity_status=verified"
                )
            if write_enabled and not target_repo:
                errors.append(
                    f"{project_id}: write_enabled requires target_repository"
                )
            if mode == "disabled" and write_enabled:
                errors.append(
                    f"{project_id}: disabled delivery cannot enable writes"
                )

        instructions = package.get("instructions", [])
        seen_ids: set[str] = set()
        for item in instructions if isinstance(instructions, list) else []:
            if not isinstance(item, dict):
                errors.append(f"{project_id}: instruction entry must be an object")
                continue
            instruction_id = item.get("id")
            source_rel = item.get("path")
            target_rel = item.get("target")
            if instruction_id in seen_ids:
                errors.append(f"{project_id}: duplicate instruction id {instruction_id}")
            seen_ids.add(instruction_id)
            if not isinstance(source_rel, str) or not isinstance(target_rel, str):
                errors.append(
                    f"{project_id}:{instruction_id}: path and target are required"
                )
                continue
            errors.extend(ensure_relative_safe(
                source_rel, f"{project_id}:{instruction_id}:source"
            ))
            errors.extend(ensure_relative_safe(
                target_rel, f"{project_id}:{instruction_id}:target"
            ))
            source_path = root / source_rel
            if not source_path.is_file():
                errors.append(
                    f"{project_id}:{instruction_id}: missing source {source_rel}"
                )
            key = (project_id, target_rel)
            if key in referenced_targets:
                errors.append(
                    f"{project_id}: duplicate target {target_rel} used by "
                    f"{referenced_targets[key]} and {instruction_id}"
                )
            referenced_targets[key] = str(instruction_id)

    # Parse every YAML and JSON file.
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        try:
            if path.suffix in {".yaml", ".yml"}:
                load_yaml(path)
            elif path.suffix == ".json":
                load_json(path)
        except Exception as exc:
            errors.append(f"cannot parse {rel}: {exc}")

    if warnings:
        print("\n".join(f"WARNING: {item}" for item in warnings))

    if errors:
        print("\n".join(f"ERROR: {item}" for item in errors))
        print(f"\nVALIDATION FAILED: {len(errors)} error(s)")
        return 1

    print("VALIDATION PASSED")
    print(f"Root: {root}")
    print(f"Canonical policy SHA-256: {actual_core_sha}")
    print(f"Projects validated: {', '.join(projects.keys())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
