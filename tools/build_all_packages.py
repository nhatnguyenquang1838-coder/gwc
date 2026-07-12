#!/usr/bin/env python3
"""Build every configured GWC project package into one versioned ZIP bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

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


def build_project(root: Path, project_id: str, output: Path) -> Path:
    command = [
        sys.executable,
        str(root / "tools" / "build_project_package.py"),
        project_id,
        "--root",
        str(root),
        "--output",
        str(output),
        "--clean",
    ]
    subprocess.run(command, check=True, cwd=root)
    package = load_yaml(root / "catalog.yaml")["projects"][project_id]["package"]
    version = str(load_yaml(root / package)["package_version"])
    destination = output / project_id / version
    if not (destination / "package-manifest.yaml").is_file():
        raise RuntimeError(f"PACKAGE_BUILD_MISSING_MANIFEST: {project_id}")
    return destination


def collect_files(root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        files.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    return files


def write_zip(source: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            handle.write(path, path.relative_to(source).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    parser.add_argument("--output", default="dist/bundles")
    parser.add_argument("--timestamp", help="UTC timestamp in YYYYMMDD-HHMMSSZ format")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    config = load_yaml(root / "bundle.yaml")
    generated = datetime.now(timezone.utc).replace(microsecond=0)
    timestamp = args.timestamp or generated.strftime(config["archive"]["timestamp_format"])
    if args.timestamp:
        generated = datetime.strptime(timestamp, config["archive"]["timestamp_format"]).replace(tzinfo=timezone.utc)

    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gwc-bundle-") as temp_dir:
        temp = Path(temp_dir)
        built_root = temp / "projects"
        projects: list[dict[str, Any]] = []
        for project_id in config["projects"]:
            package_dir = build_project(root, project_id, built_root)
            target = temp / "bundle" / "projects" / project_id / package_dir.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(package_dir, target)
            package_manifest = target / "package-manifest.yaml"
            projects.append({
                "project_id": project_id,
                "package_version": package_dir.name,
                "package_manifest": package_manifest.relative_to(temp / "bundle").as_posix(),
                "package_manifest_sha256": sha256(package_manifest),
            })

        bundle_root = temp / "bundle"
        manifest_path = bundle_root / config["archive"]["manifest_name"]
        manifest = {
            "schema_version": config["schema_version"],
            "bundle_id": config["bundle_id"],
            "bundle_version": str(config["bundle_version"]),
            "generated_at": generated.isoformat().replace("+00:00", "Z"),
            "source": {
                "repository": git_value(root, ["config", "--get", "remote.origin.url"]) or "local-uncommitted-source",
                "commit_sha": git_value(root, ["rev-parse", "HEAD"]) or "UNCOMMITTED",
            },
            "projects": projects,
        }
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
        manifest["files"] = collect_files(bundle_root)
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")

        archive_name = f"{config['archive']['prefix']}-v{config['bundle_version']}-{timestamp}.zip"
        archive_path = output / archive_name
        write_zip(bundle_root, archive_path)

    print("AGGREGATE BUNDLE BUILD COMPLETE")
    print(f"Bundle: {config['bundle_id']}")
    print(f"Version: {config['bundle_version']}")
    print(f"Generated at: {generated.isoformat().replace('+00:00', 'Z')}")
    print(f"Projects: {', '.join(config['projects'])}")
    print(f"Archive: {archive_path}")
    print(f"Archive SHA-256: {sha256(archive_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
