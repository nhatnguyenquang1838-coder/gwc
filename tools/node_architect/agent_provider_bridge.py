#!/usr/bin/env python3
"""Explicit semantic binding for an LLM/Agent provider-backed node.

The provider is deliberately a *node implementation*, never the route engine.
Node input is digested into the bounded InstructionPack; the existing
``ai_agent_adapter`` enforces file/action scope, validation evidence, replay and
later-gate non-authority. Provider output is projected through a strict result
allowlist so it cannot inject route/NEXT or authority fields into Node Architect.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, MutableMapping

from .ai_agent_adapter import Provider, SUCCESS, execute
from .semantic_dispatcher import SemanticEvaluatorBinding

_PROVIDER_RESULT_FIELDS = (
    "schema_version",
    "run_id",
    "task_id",
    "repository",
    "scope_hash",
    "idempotency_key",
    "final_head_sha",
    "changed_paths",
    "changed_path_digest",
    "validation_digest",
    "terminal_outcome",
    "provider",
    "findings",
    "checkpoints",
    "next_action",
    "recorded_actions",
    "g3_g4_g5_authority_granted",
)


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sanitize_provider_result(raw: Mapping[str, Any]) -> dict[str, Any]:
    result = {field: raw.get(field) for field in _PROVIDER_RESULT_FIELDS if field in raw}
    # Never allow a provider result to represent later-gate authority, even if a
    # future adapter accidentally returns a truthy value.
    result["g3_g4_g5_authority_granted"] = False
    return result


def build_agent_provider_binding(
    *,
    node_id: str,
    evaluator_path: str,
    request: Mapping[str, Any],
    provider: Provider,
    idempotency_store: MutableMapping[str, Mapping[str, Any]] | None = None,
    max_repair_rounds: int = 2,
) -> SemanticEvaluatorBinding:
    """Build one explicit semantic binding for a bounded Agent provider node."""
    store = idempotency_store if idempotency_store is not None else {}

    def handler(node_input: Mapping[str, Any]) -> Mapping[str, Any]:
        semantic_input_digest = _digest(node_input)
        context = {
            "g0_g1_decision_ref": str(node_input.get("g0_g1_decision_ref", "")),
            "task_summary": str(node_input.get("task_summary", "")),
            "objective": str(node_input.get("objective", "")),
            "acceptance_criteria": tuple(map(str, node_input.get("acceptance_criteria", ()) or ())),
            "gate_node_route": tuple(map(str, node_input.get("gate_node_route", ()) or ())),
            "plan_refs": tuple(map(str, node_input.get("plan_refs", ()) or ())),
            "semantic_input_digest": semantic_input_digest,
        }
        raw_result = execute(
            request,
            provider=provider,
            idempotency_store=store,
            max_repair_rounds=max_repair_rounds,
            request_context=context,
        )
        provider_result = _sanitize_provider_result(raw_result)
        terminal = str(provider_result.get("terminal_outcome") or "FAIL_CLOSED")
        disposition = "CONTINUE" if terminal == SUCCESS else "BLOCK"
        return {
            "runtime_disposition": disposition,
            "reason_code": "AGENT_PROVIDER_SUCCESS" if disposition == "CONTINUE" else f"AGENT_PROVIDER_{terminal}",
            "semantic_input_digest": semantic_input_digest,
            "provider_result": provider_result,
            "authority_granted": False,
            "executed_effects": [],
        }

    return SemanticEvaluatorBinding(
        node_id=node_id,
        evaluator_path=evaluator_path,
        handler=handler,
    )


__all__ = ["build_agent_provider_binding"]
