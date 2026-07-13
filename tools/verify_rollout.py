#!/usr/bin/env python3
"""Verify a built package against files in a target repository checkout."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from typing import Any

import yaml


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir")
    parser.add_argument("target_root")
    args = parser.parse_args()

    package_dir = Path(args.package_dir).resolve()
    target_root = Path(args.target_root).resolve()
    manifest_path = package_dir / "package-manifest.yaml"

    if not manifest_path.is_file():
        print("PACKAGE_MANIFEST_MISSING", file=sys.stderr)
        return 2
    if not target_root.is_dir():
        print("ROLLOUT_TARGET_INVALID", file=sys.stderr)
        return 2

    manifest = load_yaml(manifest_path)
    errors = []
    warnings = []

    for item in manifest.get("files", []):
        rel = item["path"]
        expected = item["sha256"]
        target = target_root / rel
        if not target.is_file():
            errors.append(f"missing: {rel}")
            continue
        actual = sha256(target)
        if actual != expected:
            warnings.append(
                f"hash mismatch: {rel}: expected {expected}, got {actual}"
            )

    if errors:
        print("INSTRUCTION_DRIFT_DETECTED")
        for error in errors:
            print(f"- {error}")
        return 1

    if warnings:
        print("ROLLOUT VERIFIED WITH WARNINGS")
        for warning in warnings:
            print(f"- {warning}")
        print(f"Project: {manifest.get('project_id')}")
        print(f"Package version: {manifest.get('package_version')}")
        print(f"Target: {target_root}")
        print(f"Files verified: {len(manifest.get('files', []))}")
        return 0

    print("ROLLOUT VERIFIED")
    print(f"Project: {manifest.get('project_id')}")
    print(f"Package version: {manifest.get('package_version')}")
    print(f"Target: {target_root}")
    print(f"Files verified: {len(manifest.get('files', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
