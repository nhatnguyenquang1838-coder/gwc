#!/usr/bin/env python3
"""Validate DS Admin / TC sync projection packets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ALLOWED_TARGETS = {"ds_admin", "tc", "jira", "github", "dashboard"}
ALLOWED_STATUSES = {
    "SYNC_NOT_REQUIRED",
    "SYNC_PENDING",
    "SYNC_SUBMITTED",
    "SYNC_VERIFIED",
    "SYNC_STALE",
    "SYNC_FAILED",
    "SYNC_SKIPPED",
}
FORBIDDEN_SOURCES = {"external_projection", "ds_admin", "tc", "jira", "dashboard"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("packet must be a JSON object")
    return data


def validate_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    required = [
        "schema_version",
        "protocol_id",
        "task_id",
        "checkpoint_id",
        "source_of_truth",
        "repository",
        "gate",
        "authority",
        "targets",
    ]
    for field in required:
        if field not in packet:
            errors.append(f"missing required field: {field}")

    if packet.get("schema_version") != "0.1":
        errors.append("schema_version must be 0.1")
    if packet.get("protocol_id") != "DS_ADMIN_TC_SYNC_PROTOCOL":
        errors.append("protocol_id must be DS_ADMIN_TC_SYNC_PROTOCOL")

    source = packet.get("source_of_truth")
    if source != "canonical_checkpoint":
        errors.append("source_of_truth must be canonical_checkpoint")
    if source in FORBIDDEN_SOURCES:
        errors.append(f"external projection cannot be source_of_truth: {source}")

    checkpoint_id = packet.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
        errors.append("checkpoint_id is required")

    repository = packet.get("repository")
    if not isinstance(repository, dict):
        errors.append("repository must be an object")
    else:
        for field in ("full_name", "base_branch", "base_sha"):
            if not repository.get(field):
                errors.append(f"repository.{field} is required")

    gate = packet.get("gate")
    blocking_declared = False
    if not isinstance(gate, dict):
        errors.append("gate must be an object")
    else:
        if not gate.get("current"):
            errors.append("gate.current is required")
        if not gate.get("status"):
            errors.append("gate.status is required")
        blocking_declared = bool(gate.get("blocking_sync_declared", False))

    authority = packet.get("authority")
    if not isinstance(authority, dict):
        errors.append("authority must be an object")
    else:
        if authority.get("external_system_authority") is not False:
            errors.append("authority.external_system_authority must be false")
        if authority.get("requires_g4_for_merge") is not True:
            errors.append("authority.requires_g4_for_merge must be true")

    targets = packet.get("targets")
    if not isinstance(targets, list) or not targets:
        errors.append("targets must be a non-empty array")
    else:
        for index, target in enumerate(targets):
            prefix = f"targets[{index}]"
            if not isinstance(target, dict):
                errors.append(f"{prefix} must be an object")
                continue
            target_type = target.get("target_type")
            if target_type not in ALLOWED_TARGETS:
                errors.append(f"{prefix}.target_type is invalid: {target_type}")
            if target.get("status") not in ALLOWED_STATUSES:
                errors.append(f"{prefix}.status is invalid: {target.get('status')}")
            if not isinstance(target.get("enabled"), bool):
                errors.append(f"{prefix}.enabled must be boolean")
            if not isinstance(target.get("blocking"), bool):
                errors.append(f"{prefix}.blocking must be boolean")
            if target.get("blocking") is True and not blocking_declared:
                errors.append(f"{prefix}.blocking requires gate.blocking_sync_declared=true")

    projection_result = packet.get("projection_result")
    if projection_result is not None:
        if not isinstance(projection_result, dict):
            errors.append("projection_result must be an object when present")
        elif projection_result.get("source_of_truth") != "canonical_checkpoint":
            errors.append("projection_result.source_of_truth must be canonical_checkpoint")

    return errors


def emit(result: dict[str, Any]) -> None:
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="Path to DS Admin / TC sync packet JSON")
    args = parser.parse_args(argv)

    try:
        packet = load_json(args.packet)
        errors = validate_packet(packet)
    except ValueError as exc:
        errors = [str(exc)]

    ok = not errors
    emit({"ok": ok, "errors": errors})
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
