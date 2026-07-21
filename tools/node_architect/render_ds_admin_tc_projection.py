#!/usr/bin/env python3
"""Render a deterministic DS Admin / TC projection packet from a checkpoint."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_TARGETS = ("ds_admin", "tc")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("checkpoint must be a JSON object")
    return data


def pick(container: dict[str, Any], *names: str, default: Any = None) -> Any:
    cursor: Any = container
    for name in names:
        if not isinstance(cursor, dict):
            return default
        cursor = cursor.get(name)
    return cursor if cursor is not None else default


def render_packet(checkpoint: dict[str, Any], targets: list[str]) -> dict[str, Any]:
    checkpoint_id = checkpoint.get("checkpoint_id") or checkpoint.get("id")
    if not checkpoint_id:
        raise ValueError("checkpoint_id is required")

    task_id = pick(checkpoint, "task", "id") or checkpoint.get("task_id")
    if not task_id:
        raise ValueError("task.id or task_id is required")

    repository = checkpoint.get("repository")
    if not isinstance(repository, dict):
        raise ValueError("checkpoint.repository is required")

    gate = checkpoint.get("gate")
    if not isinstance(gate, dict):
        raise ValueError("checkpoint.gate is required")

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    target_entries = [
        {
            "blocking": False,
            "enabled": True,
            "metadata": {"rendered_from_checkpoint": str(checkpoint_id)},
            "status": "SYNC_PENDING",
            "target_type": target,
        }
        for target in targets
    ]
    outcome = "SYNC_PENDING" if target_entries else "SYNC_NOT_REQUIRED"

    return {
        "authority": {
            "external_system_authority": False,
            "requires_g4_for_merge": True,
        },
        "checkpoint_id": str(checkpoint_id),
        "gate": {
            "blocking_sync_declared": bool(gate.get("blocking_sync_declared", False)),
            "current": gate.get("current"),
            "status": gate.get("status"),
        },
        "generated_at_utc": now,
        "git_delivery": checkpoint.get("git_delivery", {}),
        "projection_result": {
            "canonical_checkpoint_id": str(checkpoint_id),
            "errors": [],
            "generated_at_utc": now,
            "ok": True,
            "outcome": outcome,
            "source_of_truth": "canonical_checkpoint",
            "targets": target_entries,
            "warnings": [],
        },
        "protocol_id": "DS_ADMIN_TC_SYNC_PROTOCOL",
        "repository": {
            "base_branch": repository.get("base_branch"),
            "base_sha": repository.get("base_sha"),
            "full_name": repository.get("full_name"),
        },
        "schema_version": "0.1",
        "source_of_truth": "canonical_checkpoint",
        "targets": target_entries,
        "task_id": str(task_id),
    }


def emit(packet: dict[str, Any]) -> str:
    return json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path, help="Path to canonical checkpoint JSON")
    parser.add_argument("--target", action="append", choices=DEFAULT_TARGETS, dest="targets")
    parser.add_argument("--output", type=Path, help="Optional output path")
    args = parser.parse_args(argv)

    try:
        checkpoint = load_json(args.checkpoint)
        packet = render_packet(checkpoint, args.targets or list(DEFAULT_TARGETS))
        rendered = emit(packet)
    except ValueError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 1

    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
