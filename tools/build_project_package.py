#!/usr/bin/env python3
"""Build a deterministic project instruction package and SHA-256 manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import yaml


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def git_value(root: Path, args: list[str]) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id")
    parser.add_argument("--root", default=None)
    parser.add_argument("--output", default="dist")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    catalog = load_yaml(root / "catalog.yaml")
    project = catalog.get("projects", {}).get(args.project_id)
    if not project:
        print(f"PROJECT_NOT_FOUND: {args.project_id}", file=sys.stderr)
        return 2

    package_path = root / project["package"]
    package = load_yaml(package_path)
    version = package["package_version"]
    output_root = Path(args.output)
    if not output_root.is_absolute():
        output_root = root / output_root
    destination = output_root / args.project_id / version

    if args.clean and destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    manifest_files = []
    for item in package["instructions"]:
        source = root / item["path"]
        target = destination / item["target"]
        if not source.is_file():
            print(f"PACKAGE_BUILD_FAILED: missing source {source}", file=sys.stderr)
            return 3
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest_files.append({
            "instruction_id": item["id"],
            "source_path": item["path"],
            "path": item["target"],
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
        })

    source_repository = git_value(root, ["config", "--get", "remote.origin.url"])
    source_commit = git_value(root, ["rev-parse", "HEAD"])

    manifest = {
        "schema_version": "1.0",
        "project_id": args.project_id,
        "package_version": version,
        "generated_at": datetime.now(timezone.utc).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z"),
        "source": {
            "repository": source_repository or "local-uncommitted-source",
            "commit_sha": source_commit or "UNCOMMITTED",
            "package_definition": str(package_path.relative_to(root)),
        },
        "target": package["delivery"],
        "canonical_policy": catalog["canonical_policy"],
        "files": sorted(manifest_files, key=lambda item: item["path"]),
    }

    manifest_path = destination / "package-manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    print("PACKAGE BUILD COMPLETE")
    print(f"Project: {args.project_id}")
    print(f"Version: {version}")
    print(f"Output: {destination}")
    print(f"Files: {len(manifest_files)}")
    print(f"Manifest SHA-256: {sha256(manifest_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
