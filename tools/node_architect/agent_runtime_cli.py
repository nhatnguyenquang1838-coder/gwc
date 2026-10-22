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
    if "m1_m7_workflow_selection" in event:
        raise AgentRuntimeCliError("AGENT_RUNTIME_WORKFLOW_SELECTION_INJECTION")
    selection = manifest.get("workflow_selection")
    if selection is not None:
        if not isinstance(selection, Mapping) or selection.get("workflow_id") != "scrum841-m1-m7-agent-workflow-r1":
            raise AgentRuntimeCliError("WORKFLOW_SELECTION_INVALID")
        if not isinstance(selection.get("operation_envelope"), Mapping) or not isinstance(selection.get("inputs"), Mapping):
            raise AgentRuntimeCliError("WORKFLOW_SELECTION_INVALID")
    recursive = manifest.get("mode") == "recursive_run"
    if manifest.get("mode") not in (None, "recursive_run"):
        raise AgentRuntimeCliError("AGENT_RUNTIME_MODE_INVALID")
    if recursive:
        recursive_spec = manifest.get("recursive_run")
        if (not isinstance(recursive_spec, Mapping)
                or not isinstance(recursive_spec.get("root_manifest"), Mapping)
                or not isinstance(recursive_spec.get("child_node_allocations"), list)
                or not isinstance(recursive_spec.get("gate_actions"), Mapping)):
            raise AgentRuntimeCliError("RECURSIVE_RUN_MANIFEST_INVALID")
        if recursive_spec["root_manifest"].get("run_id") != event.get("run_id"):
            raise AgentRuntimeCliError("RECURSIVE_ROOT_RUN_ID_MISMATCH")
        if set(recursive_spec["gate_actions"]) != {"G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR", "G4_INTEGRATE", "G5_VALIDATE_TARGET", "G6_ACCEPT_HANDOFF"}:
            raise AgentRuntimeCliError("RECURSIVE_GATE_ACTIONS_INCOMPLETE")
        return {"provider_name": provider_name, "event": dict(event), "mode": "recursive_run", "recursive_run": dict(recursive_spec)}
    if isinstance(selection, Mapping):
        return {"provider_name": provider_name, "event": dict(event), "workflow_selection": dict(selection)}
    return {"provider_name": provider_name, "event": dict(event)}


def _prepare_event(manifest: Mapping[str, Any], provider: Any) -> dict[str, Any]:
    event = dict(manifest["event"])
    event["provider"] = provider
    event["provider_registry"] = ProviderRegistry({str(provider.name): provider})
    event.setdefault("readback_handler", None)
    event.setdefault("state", None)
    selection = manifest.get("workflow_selection")
    if isinstance(selection, Mapping):
        event["m1_m7_workflow_selection"] = dict(selection)
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
        event_kwargs = _prepare_event(manifest, provider)
        if manifest.get("mode") == "recursive_run":
            from .agent_runtime_entrypoint import run_agent_runtime_event
            from .universal_run_node import RecursiveRunDag

            recursive_spec = manifest["recursive_run"]
            actions = dict(recursive_spec["gate_actions"])

            gate_names = {
                "G0": "G0_CONTEXT", "G1": "G1_ALIGNMENT", "G2": "G2_EXECUTION",
                "G3": "G3_PR", "G4": "G4_INTEGRATE", "G5": "G5_VALIDATE_TARGET",
                "G6": "G6_ACCEPT_HANDOFF",
            }
            def canonical_host_event(**kwargs: Any) -> Mapping[str, Any]:
                gate = gate_names.get(str(kwargs.get("gate") or ""), str(kwargs.get("gate") or ""))
                action = actions.get(gate)
                if not isinstance(action, str) or not action.strip():
                    return {"status": "SEMANTIC_NODE_BLOCKED", "reason_code": "RECURSIVE_GATE_ACTION_MISSING"}
                kwargs["gate"] = gate
                kwargs["requested_action"] = action
                return run_agent_runtime_event(**kwargs)

            dag = RecursiveRunDag(runtime_event=canonical_host_event)
            result = dag.execute(
                root_manifest=recursive_spec["root_manifest"],
                child_node_allocations=recursive_spec["child_node_allocations"],
                **event_kwargs,
            )
            result["c1_status"] = "INTEGRATION_PENDING"
        else:
            result = run_agent_runtime_loop(
                event_kwargs,
                max_iterations=args.max_iterations,
            )
    except Exception as exc:  # noqa: BLE001
        result = _blocked("AGENT_RUNTIME_CALLER_ERROR", f"{type(exc).__name__}: {exc}")

    _write_result(args.output, result)
    print(json.dumps(dict(result), sort_keys=True))
    return 0 if str(result.get("status", "")).startswith("SEMANTIC_NODE_") and result.get("status") != "SEMANTIC_NODE_BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
