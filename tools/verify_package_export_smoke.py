#!/usr/bin/env python3
"""Smoke-check the real GWC package export into a generated .governance tree."""

from __future__ import annotations

import argparse
import importlib.util
import json
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


REQUIRED_GENERATED_TARGETS = {
    ".governance/core/node-architect/CONSUMER_PACKAGE_EXPORT_RULE_v0.1.md",
    ".governance/schemas/package-export-manifest.schema.json",
    ".governance/tools/export_project_package.py",
    ".governance/tools/verify_package_export_smoke.py",
    ".governance/docs/runbooks/PACKAGE_EXPORT_SMOKE_TEST.md",
}


def load_exporter(repo_root: Path) -> Any:
    tool_path = repo_root / "tools" / "export_project_package.py"
    spec = importlib.util.spec_from_file_location("export_project_package", tool_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load exporter from {tool_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_export(
    *,
    repo_root: Path,
    package_path: Path,
    output_root: Path,
    source_ref: str,
    source_base_sha: str,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    exporter = load_exporter(repo_root)
    manifest = exporter.export_package(
        repo_root=repo_root,
        package_path=package_path,
        output_root=output_root,
        source_ref=source_ref,
        source_base_sha=source_base_sha,
        generated_at_utc=generated_at_utc,
        target_root_label=".governance",
    )

    manifest_path = output_root / ".package-export-manifest.json"
    if not manifest_path.is_file():
        raise AssertionError("manifest file was not written")
    manifest_file = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest_file != manifest:
        raise AssertionError("manifest return value differs from manifest file")

    if manifest["project_id"] != "gwc":
        raise AssertionError(f"unexpected project_id: {manifest['project_id']!r}")
    if manifest["package_version"] != "1.16.0":
        raise AssertionError(f"unexpected package_version: {manifest['package_version']!r}")
    if manifest["source_ref"] != source_ref:
        raise AssertionError("source_ref mismatch")
    if manifest["source_base_sha"] != source_base_sha:
        raise AssertionError("source_base_sha mismatch")

    entries = manifest.get("entries", [])
    if not entries:
        raise AssertionError("manifest has no entries")

    copied_targets: set[str] = set()
    required_count = 0
    copied_count = 0
    skipped_optional_count = 0

    for entry in entries:
        entry_id = entry["id"]
        source_rel = entry["source_path"]
        target_rel = entry["target_path"]
        status = entry["status"]
        required = bool(entry["required"])

        if required:
            required_count += 1
            if status != "copied":
                raise AssertionError(f"required entry not copied: {entry_id}")

        if status == "skipped_optional":
            skipped_optional_count += 1
            if required:
                raise AssertionError(f"required entry skipped: {entry_id}")
            continue

        if status != "copied":
            raise AssertionError(f"unknown export status for {entry_id}: {status}")

        copied_count += 1
        source_path = repo_root / source_rel
        target_path = output_root / target_rel
        if not source_path.is_file():
            raise AssertionError(f"source file missing after export: {source_rel}")
        if not target_path.is_file():
            raise AssertionError(f"target file missing after export: {target_rel}")
        if sha256_file(source_path) != entry["sha256"]:
            raise AssertionError(f"source sha256 mismatch: {entry_id}")
        if sha256_file(target_path) != entry["sha256"]:
            raise AssertionError(f"target sha256 mismatch: {entry_id}")
        copied_targets.add(target_rel)

    missing_required_targets = sorted(REQUIRED_GENERATED_TARGETS - copied_targets)
    if missing_required_targets:
        raise AssertionError(f"required generated targets missing: {missing_required_targets}")

    return {
        "ok": True,
        "project_id": manifest["project_id"],
        "package_version": manifest["package_version"],
        "source_ref": manifest["source_ref"],
        "source_base_sha": manifest["source_base_sha"],
        "entries": len(entries),
        "required_entries": required_count,
        "copied_entries": copied_count,
        "skipped_optional_entries": skipped_optional_count,
        "required_generated_targets": sorted(REQUIRED_GENERATED_TARGETS),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--package", default="projects/gwc/package.yaml")
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-base-sha", required=True)
    parser.add_argument("--generated-at-utc", default="2026-07-22T00:00:00Z")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    package_path = (repo_root / args.package).resolve()

    try:
        if args.output:
            output_root = Path(args.output).resolve()
            if output_root.exists():
                shutil.rmtree(output_root)
            output_root.mkdir(parents=True, exist_ok=True)
            result = validate_export(
                repo_root=repo_root,
                package_path=package_path,
                output_root=output_root,
                source_ref=args.source_ref,
                source_base_sha=args.source_base_sha,
                generated_at_utc=args.generated_at_utc,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="gwc-package-export-smoke-") as tmp:
                result = validate_export(
                    repo_root=repo_root,
                    package_path=package_path,
                    output_root=Path(tmp) / "generated",
                    source_ref=args.source_ref,
                    source_base_sha=args.source_base_sha,
                    generated_at_utc=args.generated_at_utc,
                )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
