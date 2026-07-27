#!/usr/bin/env python3
"""Validate the SCRUM-116 topology, ownership and provenance contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


CONTRACT = Path("core/integration/dw-super-app-integration-contract.json")
SCHEMA = Path("schemas/integration/dw-super-app-integration.schema.json")
REQUIRED_ARTIFACT_CLASSES = {
    "gate-state",
    "product-source",
    "power-package",
    "gwc-runtime-output",
    "ua-output",
    "task-me-output",
    "bmad-output",
    "host-adapter",
    "code-ci-evidence",
    "roadmap-status",
    "human-projection",
    "communication",
}
REQUIRED_INTEGRATIONS = {
    "dw-superapps-control-plane",
    "target-system-runtime",
    "gwc",
    "ua",
    "task-me",
    "bmad",
    "github-ci",
    "jira",
    "notion",
    "slack",
}
REQUIRED_MODES = {"submodule", "power-dist", "immutable-release", "offline-zip"}
REQUIRED_GUARDS = {
    "owner_root",
    "scope_hash",
    "checkpoint_revision",
    "lease_token",
    "fencing_token",
    "idempotency_key",
}
REQUIRED_FAILURES = {
    "OWNER_ROOT_COLLISION",
    "SCOPE_HASH_MISMATCH",
    "CHECKPOINT_REVISION_MISMATCH",
    "STALE_LEASE_OR_FENCING",
    "IDEMPOTENCY_KEY_COLLISION",
}
PROJECTION_IDS = {"notion", "slack"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(root: Path) -> dict[str, Any]:
    contract_path = root / CONTRACT
    schema_path = root / SCHEMA
    issues: list[str] = []
    try:
        contract = load_json(contract_path)
        schema = load_json(schema_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"outcome": "FAIL", "valid": False, "issues": [str(exc)]}

    issues.extend(error.message for error in Draft202012Validator(schema).iter_errors(contract))
    classes = contract.get("artifact_classes", [])
    class_ids = [item.get("id") for item in classes]
    if set(class_ids) != REQUIRED_ARTIFACT_CLASSES:
        issues.append(f"artifact class set mismatch: {sorted(set(class_ids))}")
    if len(class_ids) != len(set(class_ids)):
        issues.append("artifact classes contain duplicate IDs")
    integrations = contract.get("integrations", [])
    integration_ids = [item.get("id") for item in integrations]
    if set(integration_ids) != REQUIRED_INTEGRATIONS:
        issues.append(f"integration set mismatch: {sorted(set(integration_ids))}")
    if len(integration_ids) != len(set(integration_ids)):
        issues.append("integrations contain duplicate IDs")

    for item in classes:
        if not item.get("canonical_owner") or not item.get("storage_root"):
            issues.append(f"{item.get('id')} has no canonical owner/root")
    class_by_id = {item.get("id"): item for item in classes}
    if class_by_id.get("human-projection", {}).get("authority") != "projection":
        issues.append("human-projection must be non-authoritative")
    if class_by_id.get("communication", {}).get("authority") != "projection":
        issues.append("communication must be non-authoritative")
    for item in integrations:
        if item.get("id") in PROJECTION_IDS and item.get("authority") != "projection":
            issues.append(f"{item.get('id')} must be a projection")
        if item.get("id") in PROJECTION_IDS and any("authority" in text.lower() for text in item.get("allowed_writes", [])):
            issues.append(f"{item.get('id')} allowed writes may not grant authority")

    concurrency = contract.get("concurrency", {})
    if set(concurrency.get("required_guards", [])) != REQUIRED_GUARDS:
        issues.append("concurrency guards are incomplete")
    if not REQUIRED_FAILURES <= set(concurrency.get("rejection_outcomes", [])):
        issues.append("concurrency rejection outcomes are incomplete")
    if set(contract.get("compatibility_modes", [])) != REQUIRED_MODES:
        issues.append("compatibility mode set is incomplete")
    if set(contract.get("downstream_tasks", [])) != {"SCRUM-117", "SCRUM-118", "SCRUM-119", "SCRUM-120", "SCRUM-121"}:
        issues.append("downstream task references are incomplete")
    gaps = " ".join(contract.get("explicit_gaps", []))
    if "boilerplate" not in gaps or "ready-unpublished" not in gaps:
        issues.append("explicit gaps must include boilerplate and ready-unpublished")

    examples = contract.get("provenance_examples", [])
    resolved = [item for item in examples if item.get("resolves") is True]
    rejected = [item for item in examples if item.get("resolves") is False]
    if not resolved:
        issues.append("missing positive provenance example")
    if not any(item.get("failure_code") in REQUIRED_FAILURES for item in rejected):
        issues.append("missing rejected collision/fencing provenance example")

    return {
        "outcome": "PASS" if not issues else "FAIL",
        "valid": not issues,
        "issues": issues,
        "counts": {"artifact_classes": len(classes), "integrations": len(integrations), "provenance_examples": len(examples)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = validate_contract(args.root.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
