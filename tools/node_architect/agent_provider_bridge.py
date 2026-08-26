#!/usr/bin/env python3
"""Explicit semantic binding for an LLM/Agent provider-backed node.

The provider is deliberately a *node implementation*, never the route engine.
Node input is digested into the bounded InstructionPack; the existing
``ai_agent_adapter`` enforces file/action scope, provider evidence, replay and
later-gate non-authority. The bridge adds configured provider discovery plus a
separate trusted validation runner before returning CONTINUE to the lifecycle.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from .ai_agent_adapter import DeterministicFakeProvider, Provider, SUCCESS, execute
from .semantic_dispatcher import SemanticEvaluatorBinding
from .trusted_validation_runner import TrustedValidationRunner

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


class ProviderRegistry:
    """Small explicit capability registry owned by the Agent Host."""

    def __init__(self, providers: Mapping[str, Provider] | None = None) -> None:
        self._providers: dict[str, Provider] = dict(providers or {})

    def register(self, name: str, provider: Provider) -> None:
        if not name:
            raise ValueError("provider name required")
        self._providers[name] = provider

    def resolve(self, name: str) -> Provider | None:
        return self._providers.get(name)

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sanitize_provider_result(raw: Mapping[str, Any]) -> dict[str, Any]:
    result = {field: raw.get(field) for field in _PROVIDER_RESULT_FIELDS if field in raw}
    result["g3_g4_g5_authority_granted"] = False
    return result


def _provider_class(provider: Provider | None, resolution: str) -> tuple[str, bool]:
    if provider is None:
        return "UNAVAILABLE", False
    if isinstance(provider, DeterministicFakeProvider) or getattr(provider, "name", "") == "deterministic-fake":
        return "SYNTHETIC_TEST_ONLY", False
    if resolution == "CONFIGURED_REGISTRY":
        return "CONFIGURED_PROVIDER", True
    return "DIRECT_INJECTION", False


def _run_trusted_validation(
    commands: tuple[str, ...],
    *,
    runner: TrustedValidationRunner,
    cwd: str | Path | None,
) -> tuple[bool, list[dict[str, Any]], str | None]:
    evidence: list[dict[str, Any]] = []
    for command in commands:
        try:
            raw = runner.run(command, cwd=cwd)
        except Exception as exc:
            return False, evidence, f"AGENT_VALIDATION_RUNNER_ERROR:{type(exc).__name__}:{exc}"
        if not isinstance(raw, Mapping) or not isinstance(raw.get("exit_code"), int):
            return False, evidence, "AGENT_VALIDATION_RUNNER_INVALID_RESULT"
        item = {
            "runner": str(getattr(runner, "name", type(runner).__name__)),
            "command": command,
            "exit_code": int(raw["exit_code"]),
            "stdout_digest": _digest(str(raw.get("stdout", ""))),
            "stderr_digest": _digest(str(raw.get("stderr", ""))),
        }
        if "duration_ms" in raw:
            item["duration_ms"] = raw.get("duration_ms")
        evidence.append(item)
        if item["exit_code"] != 0:
            return False, evidence, "AGENT_VALIDATION_FAILED"
    return True, evidence, None


def build_agent_provider_binding(
    *,
    node_id: str,
    evaluator_path: str,
    request: Mapping[str, Any],
    provider: Provider | None = None,
    provider_name: str | None = None,
    provider_registry: ProviderRegistry | None = None,
    validation_runner: TrustedValidationRunner | None = None,
    validation_root: str | Path | None = None,
    idempotency_store: MutableMapping[str, Mapping[str, Any]] | None = None,
    max_repair_rounds: int = 2,
) -> SemanticEvaluatorBinding:
    """Build one explicit semantic binding for a bounded Agent provider node."""
    store = idempotency_store if idempotency_store is not None else {}

    if provider_name is not None:
        resolved_provider = provider_registry.resolve(provider_name) if provider_registry is not None else None
        provider_resolution = "CONFIGURED_REGISTRY" if resolved_provider is not None else "UNAVAILABLE"
    else:
        resolved_provider = provider
        provider_resolution = "DIRECT_INJECTION" if resolved_provider is not None else "UNAVAILABLE"

    provider_evidence_class, live_closure_eligible = _provider_class(resolved_provider, provider_resolution)
    validation_commands = tuple(map(str, request.get("validation_commands", ()) or ()))

    def handler(node_input: Mapping[str, Any]) -> Mapping[str, Any]:
        semantic_input_digest = _digest(dict(node_input))
        common = {
            "semantic_input_digest": semantic_input_digest,
            "provider_resolution": provider_resolution,
            "provider_evidence_class": provider_evidence_class,
            "live_closure_eligible": live_closure_eligible,
            "authority_granted": False,
            "executed_effects": [],
        }
        if resolved_provider is None:
            return {
                **common,
                "runtime_disposition": "BLOCK",
                "reason_code": "AGENT_PROVIDER_UNAVAILABLE",
                "provider_result": {},
                "trusted_validation_passed": False,
                "validation_evidence": [],
            }
        if validation_commands and validation_runner is None:
            return {
                **common,
                "runtime_disposition": "BLOCK",
                "reason_code": "AGENT_VALIDATION_RUNNER_UNAVAILABLE",
                "provider_result": {},
                "trusted_validation_passed": False,
                "validation_evidence": [],
            }

        scalar_fields = (
            "head_sha",
            "gate",
            "requested_action",
            "g0_g1_decision_ref",
            "task_summary",
            "objective",
            "node_id",
            "node_version",
            "implementation_ref",
            "profile_revision",
            "node_registry_revision",
            "provider_contract_revision",
            "agent_boot_ref",
            "agent_instruction_digest",
        )
        context = {field: str(node_input.get(field, "")) for field in scalar_fields}
        context.update(
            {
                "acceptance_criteria": tuple(map(str, node_input.get("acceptance_criteria", ()) or ())),
                "gate_node_route": tuple(map(str, node_input.get("gate_node_route", ()) or ())),
                "plan_refs": tuple(map(str, node_input.get("plan_refs", ()) or ())),
                "semantic_input_digest": semantic_input_digest,
            }
        )
        raw_result = execute(
            request,
            provider=resolved_provider,
            idempotency_store=store,
            max_repair_rounds=max_repair_rounds,
            request_context=context,
        )
        provider_result = _sanitize_provider_result(raw_result)
        terminal = str(provider_result.get("terminal_outcome") or "FAIL_CLOSED")
        if terminal != SUCCESS:
            return {
                **common,
                "runtime_disposition": "BLOCK",
                "reason_code": f"AGENT_PROVIDER_{terminal}",
                "provider_result": provider_result,
                "trusted_validation_passed": False,
                "validation_evidence": [],
            }

        trusted_passed = True
        evidence: list[dict[str, Any]] = []
        validation_reason: str | None = None
        if validation_commands:
            assert validation_runner is not None
            trusted_passed, evidence, validation_reason = _run_trusted_validation(
                validation_commands,
                runner=validation_runner,
                cwd=validation_root,
            )
        if not trusted_passed:
            return {
                **common,
                "runtime_disposition": "BLOCK",
                "reason_code": validation_reason or "AGENT_VALIDATION_FAILED",
                "provider_result": provider_result,
                "trusted_validation_passed": False,
                "validation_evidence": evidence,
            }

        return {
            **common,
            "runtime_disposition": "CONTINUE",
            "reason_code": "AGENT_PROVIDER_SUCCESS",
            "provider_result": provider_result,
            "trusted_validation_passed": True,
            "validation_evidence": evidence,
        }

    return SemanticEvaluatorBinding(
        node_id=node_id,
        evaluator_path=evaluator_path,
        handler=handler,
    )


__all__ = ["ProviderRegistry", "build_agent_provider_binding"]
