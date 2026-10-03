#!/usr/bin/env python3
"""Production entrypoint for the Universal Runtime v2 controller/executor path.

This module never imports or falls back to the GWC v1 Agent Runtime. Missing or
invalid Universal V2 components are reported as ``GWC_RUNTIME_DEFECT``.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Callable, Mapping

from .universal_runtime_profile import (
    UniversalRuntimeProfileError,
    load_universal_v2_default_profile,
)


class AgentRuntimeCliError(ValueError):
    """A malformed V2 manifest or provider-factory specification."""


def _blocked(reason_code: str, message: str, *, profile: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "BLOCKED",
        "reason_code": reason_code,
        "message": message,
        "runtime_family": "UNIVERSAL_V2",
        "runtime_protocol": "gwc.universal.controller/v2",
        "authority_granted": False,
        "executed_effects": [],
        "legacy_fallback": False,
    }
    if isinstance(profile, Mapping):
        result["runtime_profile_digest"] = str(profile.get("profile_digest", ""))
    return result


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentRuntimeCliError(f"manifest could not be loaded: {type(exc).__name__}") from exc


def _load_factory(specification: str) -> Callable[[], Any]:
    module_name, separator, attribute = specification.rpartition(":")
    if not separator or not module_name or not attribute:
        raise AgentRuntimeCliError("provider factory must use module:callable or /path/module.py:callable")

    module: ModuleType
    if module_name.endswith(".py") or "/" in module_name:
        module_path = Path(module_name).expanduser().resolve()
        if not module_path.is_file():
            raise AgentRuntimeCliError("provider factory module missing")
        module_spec = importlib.util.spec_from_file_location(
            f"gwc_universal_v2_provider_{module_path.stem}", module_path
        )
        if module_spec is None or module_spec.loader is None:
            raise AgentRuntimeCliError("provider factory module cannot be loaded")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise AgentRuntimeCliError("provider factory import failed") from exc

    factory = getattr(module, attribute, None)
    if not callable(factory):
        raise AgentRuntimeCliError("provider factory is not callable")
    return factory


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = _load_json(path)
    if not isinstance(manifest, Mapping):
        raise AgentRuntimeCliError("manifest must be a JSON object")
    event = manifest.get("event")
    provider_name = manifest.get("provider_name")
    if not isinstance(event, Mapping):
        raise AgentRuntimeCliError("manifest.event must be a JSON object")
    if not isinstance(provider_name, str) or not provider_name.strip():
        raise AgentRuntimeCliError("manifest.provider_name must be a non-empty string")
    universal_run = manifest.get("universal_run")
    if universal_run is not None and not isinstance(universal_run, Mapping):
        raise AgentRuntimeCliError("manifest.universal_run must be a JSON object")
    return {
        "provider_name": provider_name,
        "event": dict(event),
        "universal_run": dict(universal_run) if isinstance(universal_run, Mapping) else None,
    }


def _prepare_event(manifest: Mapping[str, Any], _provider: Any) -> dict[str, Any]:
    """Return only caller event data; runtime authority is host/controller-owned."""
    return dict(manifest["event"])


def _write_result(path: Path | None, result: Mapping[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _emit(result: Mapping[str, Any], output: Path | None) -> int:
    _write_result(output, result)
    print(json.dumps(dict(result), sort_keys=True, ensure_ascii=False))
    return 0 if result.get("status") == "UNIVERSAL_RUN_NODE_COMPLETE" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--provider-factory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-iterations", type=int, default=32)
    args = parser.parse_args(argv)

    try:
        profile = load_universal_v2_default_profile()
    except UniversalRuntimeProfileError as exc:
        return _emit(_blocked("GWC_RUNTIME_DEFECT", str(exc)), args.output)

    try:
        manifest = _load_manifest(args.manifest)
    except AgentRuntimeCliError as exc:
        return _emit(_blocked("GWC_RUNTIME_DEFECT", str(exc), profile=profile), args.output)

    universal_run = manifest.get("universal_run")
    if not isinstance(universal_run, Mapping):
        return _emit(
            _blocked(
                "GWC_RUNTIME_DEFECT",
                "Universal V2 is the only default runtime; manifest.universal_run is required.",
                profile=profile,
            ),
            args.output,
        )

    if not args.provider_factory:
        return _emit(
            _blocked("GWC_RUNTIME_DEFECT", "Universal V2 requires a configured provider factory.", profile=profile),
            args.output,
        )
    if args.max_iterations < 1:
        return _emit(
            _blocked("GWC_RUNTIME_DEFECT", "max_iterations must be positive.", profile=profile),
            args.output,
        )

    try:
        provider = _load_factory(args.provider_factory)()
        if not isinstance(getattr(provider, "name", None), str) or not provider.name:
            raise AgentRuntimeCliError("configured provider must expose a non-empty name")
        if provider.name != manifest["provider_name"]:
            raise AgentRuntimeCliError("manifest/provider factory identity mismatch")
        event = _prepare_event(manifest, provider)

        # Imports are deliberately lazy and V2-only. Missing components become a
        # runtime defect; there is no import or execution fallback to GWC v1.
        from .universal_run_controller import UniversalController
        from .universal_run_execution import UniversalExecutor

        controller = UniversalController.from_manifest(profile=profile, manifest=universal_run)
        assignment = controller.assign_current_action()
        executor = UniversalExecutor()
        receipt = executor.execute(
            assignment=assignment,
            provider=provider,
            event=event,
            evidence_root=universal_run.get("evidence_root"),
            max_iterations=args.max_iterations,
        )
        decision = controller.consume_executor_receipt(receipt)
        result = {
            "status": "UNIVERSAL_RUN_NODE_COMPLETE" if receipt.get("host_status") == "ACTION_COMPLETE" else "UNIVERSAL_RUN_NODE_BLOCKED",
            "runtime_family": "UNIVERSAL_V2",
            "runtime_protocol": profile["runtime_protocol"],
            "runtime_profile_digest": profile["profile_digest"],
            "run_id": assignment["run_id"],
            "executor_receipt": receipt,
            "controller_decision": decision,
            "authority_granted": False,
            "executed_effects": [],
        }
        return _emit(result, args.output)
    except Exception as exc:  # noqa: BLE001 - V2 component/contract failures never fall back
        return _emit(
            _blocked("GWC_RUNTIME_DEFECT", f"Universal V2 dispatch failed: {type(exc).__name__}", profile=profile),
            args.output,
        )


if __name__ == "__main__":
    raise SystemExit(main())
