#!/usr/bin/env python3
"""Production Agent Host caller for the bounded semantic runtime.

The manifest supplies host-owned runtime context and an explicit provider
factory supplies the configured provider. The provider is registered before the
canonical loop is called; it cannot replace route, authority, skills,
capabilities, readback, or NEXT semantics.
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

from .agent_provider_bridge import ProviderRegistry
from .agent_runtime_entrypoint import run_agent_runtime_loop


class AgentRuntimeCliError(ValueError):
    """A malformed host manifest or provider factory specification."""


def _blocked(reason_code: str, message: str) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "reason_code": reason_code,
        "message": message,
        "authority_granted": False,
        "executed_effects": [],
    }


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentRuntimeCliError(f"manifest could not be loaded: {exc}") from exc


def _load_factory(specification: str) -> Callable[[], Any]:
    module_name, separator, attribute = specification.rpartition(":")
    if not separator or not module_name or not attribute:
        raise AgentRuntimeCliError(
            "provider factory must use module:callable or /path/module.py:callable"
        )

    module: ModuleType
    if module_name.endswith(".py") or "/" in module_name:
        module_path = Path(module_name).expanduser().resolve()
        if not module_path.is_file():
            raise AgentRuntimeCliError(f"provider factory module missing: {module_path}")
        module_spec = importlib.util.spec_from_file_location(
            f"gwc_agent_runtime_provider_{module_path.stem}", module_path
        )
        if module_spec is None or module_spec.loader is None:
            raise AgentRuntimeCliError(f"provider factory module cannot be loaded: {module_path}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise AgentRuntimeCliError(f"provider factory import failed: {exc}") from exc

    factory = getattr(module, attribute, None)
    if not callable(factory):
        raise AgentRuntimeCliError(f"provider factory is not callable: {specification}")
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
    return {"provider_name": provider_name, "event": dict(event)}


def _prepare_event(manifest: Mapping[str, Any], provider: Any) -> dict[str, Any]:
    event = dict(manifest["event"])
    event["provider"] = provider
    event["provider_registry"] = ProviderRegistry({str(provider.name): provider})
    event.setdefault("readback_handler", None)
    event.setdefault("state", None)
    return event


def _write_result(path: Path | None, result: Mapping[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--provider-factory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-iterations", type=int, default=32)
    args = parser.parse_args(argv)

    if args.max_iterations < 1:
        result = _blocked("AGENT_RUNTIME_ITERATION_LIMIT_INVALID", "max_iterations must be positive")
        _write_result(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 1

    try:
        manifest = _load_manifest(args.manifest)
    except AgentRuntimeCliError as exc:
        result = _blocked("AGENT_RUNTIME_MANIFEST_INVALID", str(exc))
        _write_result(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 1

    if not args.provider_factory:
        result = _blocked(
            "AGENT_PROVIDER_FACTORY_REQUIRED",
            "production Agent Host requires an explicit configured provider factory",
        )
        _write_result(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 1

    try:
        provider = _load_factory(args.provider_factory)()
    except (AgentRuntimeCliError, Exception) as exc:  # noqa: BLE001
        result = _blocked("AGENT_PROVIDER_FACTORY_INVALID", str(exc))
        _write_result(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 1

    if not isinstance(getattr(provider, "name", None), str) or not provider.name:
        result = _blocked("AGENT_PROVIDER_NAME_MISSING", "configured provider must expose a non-empty name")
        _write_result(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 1
    if provider.name != manifest["provider_name"]:
        result = _blocked(
            "AGENT_PROVIDER_NAME_MISMATCH",
            f"manifest provider_name {manifest['provider_name']!r} does not match factory provider {provider.name!r}",
        )
        _write_result(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 1

    try:
        result = run_agent_runtime_loop(
            _prepare_event(manifest, provider),
            max_iterations=args.max_iterations,
        )
    except Exception as exc:  # noqa: BLE001
        result = _blocked("AGENT_RUNTIME_CALLER_ERROR", f"{type(exc).__name__}: {exc}")

    _write_result(args.output, result)
    print(json.dumps(dict(result), sort_keys=True))
    return 0 if str(result.get("status", "")).startswith("SEMANTIC_NODE_") and result.get("status") != "SEMANTIC_NODE_BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
