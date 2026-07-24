#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

MANAGED_MARKER = ".dw-managed.json"


class RuntimeError_(RuntimeError):
    pass


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError_(f"required file missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError_(f"expected object in {path}")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def metadata(root: Path) -> dict[str, Any]:
    manifest = load_json(root / "MANIFEST.json")
    return {
        "power_id": manifest["metadata"]["powerId"],
        "version": manifest["metadata"]["version"],
        "runtime_root": manifest["spec"]["runtimeDataRoot"],
        "manifest": manifest,
    }


def target_paths(target: Path, power_id: str) -> dict[str, Path]:
    dw_root = target / ".dw"
    return {
        "target": target,
        "dw": dw_root,
        "install": dw_root / "powers" / power_id,
        "config": dw_root / "config" / power_id,
        "history": dw_root / "history" / power_id,
    }


def marker(path: Path) -> dict[str, Any]:
    return load_json(path / MANAGED_MARKER)


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, encoding="utf-8", newline="\n"
        ) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle_path = handle.name
        os.replace(handle_path, path)
        handle_path = None
    finally:
        if handle_path:
            Path(handle_path).unlink(missing_ok=True)


def assert_safe_target(package: Path, target: Path) -> None:
    package = package.resolve()
    target = target.resolve()
    if package == target or is_within(target, package) or is_within(package, target):
        raise RuntimeError_("package root and consumer target must not contain each other")


def install(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.package_root).resolve()
    target = Path(args.target).resolve()
    assert_safe_target(source, target)
    info = metadata(source)
    paths = target_paths(target, info["power_id"])
    destination = paths["install"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    paths["history"].mkdir(parents=True, exist_ok=True)

    old_marker: dict[str, Any] | None = None
    if destination.exists():
        marker_path = destination / MANAGED_MARKER
        if not marker_path.is_file():
            raise RuntimeError_(f"refusing to overwrite unmanaged installation: {destination}")
        old_marker = marker(destination)

    temporary = destination.parent / f".{info['power_id']}.tmp-{uuid.uuid4().hex}"
    backup: Path | None = None
    try:
        shutil.copytree(source, temporary, symlinks=False)
        atomic_json(
            temporary / MANAGED_MARKER,
            {
                "managedBy": "dw-power-runtime",
                "powerId": info["power_id"],
                "version": info["version"],
                "sourceManifestSha256": sha256_file(source / "MANIFEST.json"),
                "installedAtEpoch": int(time.time()),
            },
        )
        if destination.exists():
            old_version = str(old_marker.get("version", "unknown")) if old_marker else "unknown"
            backup = paths["history"] / f"{old_version}-{int(time.time())}"
            suffix = 0
            while backup.exists():
                suffix += 1
                backup = paths["history"] / f"{old_version}-{int(time.time())}-{suffix}"
            os.replace(destination, backup)
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if backup and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise

    runtime_root = (target / info["runtime_root"]).resolve()
    if not is_within(runtime_root, target):
        raise RuntimeError_("runtime data root escapes consumer target")
    runtime_root.mkdir(parents=True, exist_ok=True)
    return {
        "status": "INSTALLED",
        "power_id": info["power_id"],
        "version": info["version"],
        "install_root": str(destination),
        "runtime_root": str(runtime_root),
        "backup": str(backup) if backup else None,
    }


def configure(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.package_root).resolve()
    target = Path(args.target).resolve()
    info = metadata(source)
    paths = target_paths(target, info["power_id"])
    destination = paths["config"]
    if not args.config and not args.contract:
        raise RuntimeError_("configure requires --config and/or --contract")
    if destination.exists() and not (destination / MANAGED_MARKER).is_file():
        raise RuntimeError_(f"refusing to overwrite unmanaged configuration: {destination}")

    temporary = destination.parent / f".{info['power_id']}.config-{uuid.uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        if args.config:
            config = Path(args.config).resolve()
            if not config.is_file():
                raise RuntimeError_(f"config file not found: {config}")
            shutil.copyfile(config, temporary / "config.yaml")
        elif destination.is_dir() and (destination / "config.yaml").is_file():
            shutil.copyfile(destination / "config.yaml", temporary / "config.yaml")

        if args.contract:
            contract = Path(args.contract).resolve()
            if not contract.is_file():
                raise RuntimeError_(f"contract file not found: {contract}")
            shutil.copyfile(contract, temporary / "consumer-contract.yaml")
        elif destination.is_dir() and (destination / "consumer-contract.yaml").is_file():
            shutil.copyfile(destination / "consumer-contract.yaml", temporary / "consumer-contract.yaml")

        atomic_json(
            temporary / MANAGED_MARKER,
            {
                "managedBy": "dw-power-runtime",
                "powerId": info["power_id"],
                "version": info["version"],
                "configuredAtEpoch": int(time.time()),
            },
        )
        old = destination.parent / f".{info['power_id']}.config-old-{uuid.uuid4().hex}"
        if destination.exists():
            os.replace(destination, old)
        else:
            old = None
        os.replace(temporary, destination)
        if old:
            shutil.rmtree(old)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {"status": "CONFIGURED", "config_root": str(destination)}


def verify_manifest(install_root: Path, manifest: dict[str, Any]) -> None:
    for entry in manifest["files"]:
        path = install_root / entry["path"]
        if not path.is_file():
            raise RuntimeError_(f"installed file missing: {entry['path']}")
        if path.stat().st_size != entry["size"]:
            raise RuntimeError_(f"installed size mismatch: {entry['path']}")
        if sha256_file(path) != entry["sha256"]:
            raise RuntimeError_(f"installed hash mismatch: {entry['path']}")
    for entrypoint in manifest["spec"]["entrypoints"]:
        if not (install_root / entrypoint).is_file():
            raise RuntimeError_(f"entrypoint missing: {entrypoint}")


def doctor(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.package_root).resolve()
    target = Path(args.target).resolve()
    info = metadata(source)
    paths = target_paths(target, info["power_id"])
    install_root = paths["install"]
    if not install_root.is_dir():
        raise RuntimeError_(f"Power is not installed: {install_root}")
    installed_marker = marker(install_root)
    if installed_marker.get("powerId") != info["power_id"]:
        raise RuntimeError_("managed marker power ID mismatch")
    installed_manifest = load_json(install_root / "MANIFEST.json")
    verify_manifest(install_root, installed_manifest)

    runtime_root = (target / installed_manifest["spec"]["runtimeDataRoot"]).resolve()
    if not is_within(runtime_root, target):
        raise RuntimeError_("runtime root escapes consumer target")
    if not runtime_root.is_dir():
        raise RuntimeError_(f"runtime root missing: {runtime_root}")

    config_root = paths["config"]
    config_status = "missing"
    if config_root.is_dir():
        config_marker = marker(config_root)
        if config_marker.get("powerId") != info["power_id"]:
            raise RuntimeError_("configuration marker power ID mismatch")
        config_status = "managed"
    elif args.require_config:
        raise RuntimeError_("managed configuration is required but missing")

    return {
        "status": "PASS",
        "power_id": info["power_id"],
        "version": installed_marker.get("version"),
        "install_root": str(install_root),
        "runtime_root": str(runtime_root),
        "configuration": config_status,
    }


def uninstall(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.package_root).resolve()
    target = Path(args.target).resolve()
    info = metadata(source)
    paths = target_paths(target, info["power_id"])
    removed: list[str] = []

    for key in ("install", "config"):
        path = paths[key]
        if not path.exists():
            continue
        if not (path / MANAGED_MARKER).is_file():
            raise RuntimeError_(f"refusing to remove unmanaged path: {path}")
        shutil.rmtree(path)
        removed.append(str(path))

    runtime_root = (target / info["runtime_root"]).resolve()
    if args.include_runtime:
        if not args.yes:
            raise RuntimeError_("--include-runtime requires --yes")
        if not is_within(runtime_root, target):
            raise RuntimeError_("runtime root escapes consumer target")
        if runtime_root.exists():
            shutil.rmtree(runtime_root)
            removed.append(str(runtime_root))

    return {
        "status": "UNINSTALLED",
        "power_id": info["power_id"],
        "runtime_preserved": not args.include_runtime,
        "removed": removed,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Portable runtime for a DW Power package.")
    result.add_argument("--package-root", default=str(package_root()))
    subparsers = result.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--target", required=True)
    install_parser.set_defaults(handler=install)

    configure_parser = subparsers.add_parser("configure")
    configure_parser.add_argument("--target", required=True)
    configure_parser.add_argument("--config")
    configure_parser.add_argument("--contract")
    configure_parser.set_defaults(handler=configure)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--target", required=True)
    doctor_parser.add_argument("--require-config", action="store_true")
    doctor_parser.set_defaults(handler=doctor)

    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--target", required=True)
    uninstall_parser.add_argument("--include-runtime", action="store_true")
    uninstall_parser.add_argument("--yes", action="store_true")
    uninstall_parser.set_defaults(handler=uninstall)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        output = args.handler(args)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (RuntimeError_, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"power-runtime: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
