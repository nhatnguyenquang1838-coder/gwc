#!/usr/bin/env python3
"""Fail-closed semantic dispatcher for Node Architect runtime nodes.

The source resolver proves which repository file semantically backs a node. This
module deliberately does *not* import that file. An Agent Host must provide an
explicit binding whose node id and evaluator path exactly match the resolved
source. The binding adapts the evaluator's native call signature to one bounded
``handler(payload) -> mapping`` interface.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

SemanticHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class SemanticEvaluatorBinding:
    node_id: str
    evaluator_path: str
    handler: SemanticHandler


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finish(payload: dict[str, Any]) -> dict[str, Any]:
    stable = dict(payload)
    stable["result_digest"] = _digest(stable)
    return stable


def _blocked(
    *,
    node_id: str,
    semantic_source: Mapping[str, Any],
    reason_code: str,
    input_payload: Mapping[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "node_id": node_id,
        "status": "BLOCKED",
        "reason_code": reason_code,
        "semantic_execution": False,
        "semantic_source_status": semantic_source.get("status"),
        "evaluator_path": semantic_source.get("evaluator_path"),
        "input_digest": _digest(dict(input_payload)),
        "result": {},
        "authority_granted": False,
        "executed_effects": [],
    }
    if error is not None:
        result["error"] = error
    return _finish(result)


def dispatch_semantic_node(
    node: Mapping[str, Any],
    semantic_source: Mapping[str, Any],
    input_payload: Mapping[str, Any],
    *,
    bindings: Mapping[str, SemanticEvaluatorBinding],
) -> dict[str, Any]:
    """Execute one already-resolved node through an explicit semantic binding."""
    node_id = node.get("id")
    if not isinstance(node_id, str) or not node_id:
        return _blocked(
            node_id="",
            semantic_source=semantic_source,
            reason_code="SEMANTIC_NODE_ID_MISSING",
            input_payload=input_payload,
        )

    if semantic_source.get("runtime_eligible") is not True:
        return _blocked(
            node_id=node_id,
            semantic_source=semantic_source,
            reason_code=str(semantic_source.get("reason_code") or "SEMANTIC_SOURCE_NOT_ELIGIBLE"),
            input_payload=input_payload,
        )

    evaluator_path = semantic_source.get("evaluator_path")
    if not isinstance(evaluator_path, str) or not evaluator_path:
        return _blocked(
            node_id=node_id,
            semantic_source=semantic_source,
            reason_code="SEMANTIC_EVALUATOR_MISSING",
            input_payload=input_payload,
        )

    binding = bindings.get(node_id)
    if binding is None:
        return _blocked(
            node_id=node_id,
            semantic_source=semantic_source,
            reason_code="SEMANTIC_HANDLER_UNAVAILABLE",
            input_payload=input_payload,
        )
    if binding.node_id != node_id or binding.evaluator_path != evaluator_path:
        return _blocked(
            node_id=node_id,
            semantic_source=semantic_source,
            reason_code="SEMANTIC_BINDING_MISMATCH",
            input_payload=input_payload,
        )

    try:
        raw = binding.handler(dict(input_payload))
    except Exception as exc:  # host/evaluator failure must become typed evidence
        return _blocked(
            node_id=node_id,
            semantic_source=semantic_source,
            reason_code="SEMANTIC_EVALUATOR_ERROR",
            input_payload=input_payload,
            error=f"{type(exc).__name__}: {exc}",
        )

    if not isinstance(raw, Mapping):
        return _blocked(
            node_id=node_id,
            semantic_source=semantic_source,
            reason_code="SEMANTIC_EVALUATOR_INVALID_RESULT",
            input_payload=input_payload,
        )

    result = {
        "node_id": node_id,
        "status": "SEMANTIC_EXECUTED",
        "reason_code": "SEMANTIC_EVALUATOR_EXECUTED",
        "semantic_execution": True,
        "semantic_source_status": semantic_source.get("status"),
        "evaluator_path": evaluator_path,
        "input_digest": _digest(dict(input_payload)),
        "result": dict(raw),
        "authority_granted": False,
        "executed_effects": [],
    }
    return _finish(result)


__all__ = [
    "SemanticEvaluatorBinding",
    "SemanticHandler",
    "dispatch_semantic_node",
]
