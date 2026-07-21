#!/usr/bin/env python3
"""Export a GWC project package into a generated consumer .governance tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import yaml


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def is_safe_relative(path_value: str) -> bool:
    candidate = Path(path_value)
    return bool(path_value) and not candidate.is_absolute() and ".." not in candidate.parts and "\\" not in path_value


def require_safe_relative(path_value: str, label: str) -> Path:
    if not isinstance(path_value, str) or not is_safe_relative(path_value):
        raise ValueError(f"{label}: unsafe relative path: {path_value!r}")
    return Path(path_value)


def utc_now_seconds() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_inside(root: Path, relative_path: Path, label: str) -> Path:
    root_resolved = root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"{label}: path escapes root: {relative_path}") from exc
    return candidate


def export_package(
    *,
    repo_root: Path,
    package_path: Path,
    output_root: Path,
    source_ref: str,
    source_base_sha: str,
    generated_at_utc: str | None = None,
    target_root_label: str = ".",
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    package_path = package_path.resolve()
    output_root = output_root.resolve()
    if not source_ref:
        raise ValueError("source_ref is required")
    if not isinstance(source_base_sha, str) or len(source_base_sha) != 40:
        raise ValueError("source_base_sha must be a 40-character commit SHA")

    package = load_yaml(package_path)
    if not isinstance(package, dict):
        raise ValueError("package must be a YAML object")

    project_id = package.get("project_id")
    package_version = package.get("package_version")
    delivery = package.get("delivery", {})
    source_repository = delivery.get("target_repository") if isinstance(delivery, dict) else None
    instructions = package.get("instructions", [])

    if not isinstance(project_id, str):
        raise ValueError("package.project_id is required")
    if not isinstance(package_version, str):
        raise ValueError("package.package_version is required")
    if not isinstance(source_repository, str):
        raise ValueError("delivery.target_repository is required")
    if not isinstance(instructions, list):
        raise ValueError("package.instructions must be a list")

    seen_ids: set[str] = set()
    seen_targets: set[str] = set()
    entries: list[dict[str, Any]] = []

    for index, item in enumerate(instructions):
        if not isinstance(item, dict):
            raise ValueError(f"instructions[{index}] must be an object")
        entry_id = item.get("id")
        source_value = item.get("path")
        target_value = item.get("target")
        required = bool(item.get("required", True))
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError(f"instructions[{index}].id is required")
        if entry_id in seen_ids:
            raise ValueError(f"duplicate package id: {entry_id}")
        seen_ids.add(entry_id)
        source_rel = require_safe_relative(source_value, f"{entry_id}.path")
        target_rel = require_safe_relative(target_value, f"{entry_id}.target")
        if str(target_rel) in seen_targets:
            raise ValueError(f"duplicate target path: {target_rel}")
        seen_targets.add(str(target_rel))

        source_path = resolve_inside(repo_root, source_rel, f"{entry_id}.path")
        target_path = resolve_inside(output_root, target_rel, f"{entry_id}.target")
        if not source_path.is_file():
            if required:
                raise FileNotFoundError(f"{entry_id}: missing required source {source_rel}")
            entries.append({"id": entry_id, "source_path": str(source_rel), "target_path": str(target_rel), "required": False, "status": "skipped_optional", "sha256": None, "bytes": None})
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        data = source_path.read_bytes()
        target_path.write_bytes(data)
        entries.append({"id": entry_id, "source_path": str(source_rel), "target_path": str(target_rel), "required": required, "status": "copied", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})

    manifest = {
        "schema_version": "1.0",
        "project_id": project_id,
        "package_version": package_version,
        "source_repository": source_repository,
        "source_ref": source_ref,
        "source_base_sha": source_base_sha,
        "target_root": target_root_label,
        "generated_at_utc": generated_at_utc or utc_now_seconds(),
        "entries": entries,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / ".package-export-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--package", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-base-sha", required=True)
    parser.add_argument("--generated-at-utc", default=None)
    parser.add_argument("--target-root-label", default=".")
    args = parser.parse_args()
    try:
        manifest = export_package(
            repo_root=Path(args.root),
            package_path=Path(args.package),
            output_root=Path(args.output),
            source_ref=args.source_ref,
            source_base_sha=args.source_base_sha,
            generated_at_utc=args.generated_at_utc,
            target_root_label=args.target_root_label,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, "entries": len(manifest["entries"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
