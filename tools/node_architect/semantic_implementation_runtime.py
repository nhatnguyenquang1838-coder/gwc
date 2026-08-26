#!/usr/bin/env python3
"""Invoke one exact semantic implementation binding without reflection fallback."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .instruction_contract_evaluator import evaluate_instruction_contract
from .semantic_implementation_registry import INSTRUCTION_EVALUATOR

Handler = Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _blocked(binding: Mapping[str, Any], event: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = {
        "node_id": binding.get("node_id"),
        "node_version": binding.get("node_version"),
        "implementation_ref": binding.get("implementation_ref"),
        "binding_digest": binding.get("binding_digest"),
        "implementation_invoked": False,
        "semantic_execution": False,
        "outcome": "BLOCKED",
        "reason_code": reason,
        "authority_granted": False,
        "executed_effects": [],
    }
    result["invocation_digest"] = _digest({"binding": binding.get("binding_digest"), "event": event, "result": result})
    return result


def invoke_semantic_implementation(
    binding: Mapping[str, Any],
    runtime_event: Mapping[str, Any],
    *,
    root: Path | str = Path("."),
    handlers: Mapping[str, Handler] | None = None,
) -> dict[str, Any]:
    """Invoke a compiled binding.

    Instruction-contract bindings are implemented by the checked-in interpreter.
    Existing source/route callables must be supplied through an explicit handler
    registry by the Agent Host/lifecycle. Runtime never imports a string selected
    by model output or silently falls back to a generic adapter.
    """
    implementation_ref = binding.get("implementation_ref")
    if not isinstance(implementation_ref, str) or not implementation_ref:
        return _blocked(binding, runtime_event, "SEMANTIC_IMPLEMENTATION_REF_MISSING")

    try:
        if implementation_ref == INSTRUCTION_EVALUATOR:
            raw = evaluate_instruction_contract(binding, runtime_event, root=root)
        else:
            handler = (handlers or {}).get(implementation_ref)
            if handler is None:
                return _blocked(binding, runtime_event, "SEMANTIC_IMPLEMENTATION_HANDLER_UNAVAILABLE")
            raw = handler(binding, runtime_event)
    except Exception as exc:
        result = _blocked(binding, runtime_event, "SEMANTIC_IMPLEMENTATION_EXCEPTION")
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    if not isinstance(raw, Mapping):
        return _blocked(binding, runtime_event, "SEMANTIC_IMPLEMENTATION_INVALID_RESULT")
    result = dict(raw)
    result.update({
        "node_id": binding.get("node_id"),
        "node_version": binding.get("node_version"),
        "implementation_ref": implementation_ref,
        "binding_digest": binding.get("binding_digest"),
        "implementation_invoked": True,
        "semantic_execution": True,
        "authority_granted": False,
    })
    # Semantic implementation output never owns authority. Any proposed effects
    # are consumed later by W12's capability/authority boundary.
    result["executed_effects"] = []
    result["invocation_digest"] = _digest({
        "binding_digest": binding.get("binding_digest"),
        "event": runtime_event,
        "semantic_result": {k: v for k, v in result.items() if k != "invocation_digest"},
    })
    return result


__all__ = ["invoke_semantic_implementation"]
