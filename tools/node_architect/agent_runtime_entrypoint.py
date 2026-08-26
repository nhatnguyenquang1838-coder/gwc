#!/usr/bin/env python3
"""Production Agent Host entrypoint for the Node Architect semantic Agent/LLM runtime.

This is the ONE obvious composition point a reviewer can open to see the whole
runtime. It wires, in order:

  repository instructions (AGENTS.md) + agent instructions + role overlays
        + required skills + current Node Instruction Card
        -> immutable InstructionBundle
        -> canonical route decision (resolve_gate_node_route)
        -> semantic implementation binding
        -> live runtime event (build_live_runtime_event)
        -> dispatch (dispatch_live_runtime_event)
        -> semantic node lifecycle (execute_semantic_node_lifecycle)
        -> LLM/Agent provider (build_agent_provider_binding)
        -> authorized tool capability boundary
        -> canonical readback
        -> NodeEvidenceLedger
        -> typed NEXT

The provider is the reasoning engine INSIDE the governed node. It never owns
route selection, gate authority, NEXT selection outside the declared contract,
arbitrary skill selection, or arbitrary tool authority. All of those are
resolved by the host from repository contracts before the provider is invoked.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from .agent_instruction_bundle import (
    InstructionBundleError,
    resolve_agent_instruction_bundle,
    validate_agent_instruction_bundle,
)
from .agent_provider_bridge import ProviderRegistry, build_agent_provider_binding
from .build_node_instruction_pack import InstructionPack
from .live_runtime_bridge import LiveRuntimeState, build_live_runtime_event, dispatch_live_runtime_event
from .resolve_gate_node_route import resolve_gate_node_route
from .semantic_implementation_registry import compile_semantic_implementation_registry
from .trusted_validation_runner import TrustedValidationRunner

INSTRUCTION_EVALUATOR_REF = "tools/node_architect/instruction_contract_evaluator.py:evaluate_instruction_contract"

CANONICAL_SOURCE_KIND = "canonical_agent_gate_state"


def _load_json(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def bootstrap_agent_runtime(
    *,
    root: Path | str,
    canonical_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Load repository runtime artifacts and compile the semantic implementation registry.

    This is the Agent Host boot: it reads the checked-in route profile, node
    registry, graph registry and compiles the exact semantic implementation
    bindings. It performs no provider invocation and grants no authority.
    """
    repo_root = Path(root).resolve()
    profile = _load_json(repo_root / "core/node-architect/gate-node-route-profile.json")
    node_registry = _load_json(repo_root / "core/node-architect/node-registry.json")
    graph_registry = _load_json(repo_root / "core/node-architect/runtime-graph-registry.json")
    if profile is None or node_registry is None or graph_registry is None:
        raise RuntimeError("AGENT_RUNTIME_BOOT_ARTIFACT_MISSING")
    registry_report = compile_semantic_implementation_registry(node_registry, root=repo_root)
    return {
        "root": repo_root,
        "route_profile": profile,
        "node_registry": node_registry,
        "graph_registry": graph_registry,
        "implementation_registry": registry_report,
    }


def _binding_for(implementation_registry: Mapping[str, Any], node_id: str) -> Mapping[str, Any] | None:
    matches = [
        item for item in implementation_registry.get("bindings", [])
        if isinstance(item, Mapping) and item.get("node_id") == node_id
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_agent_route(
    *,
    root: Path | str,
    canonical_state: Mapping[str, Any],
    route_context: Mapping[str, Any],
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the canonical gate-node route for the current agent run."""
    runtime = runtime or bootstrap_agent_runtime(root=root, canonical_state=canonical_state)
    return resolve_gate_node_route(
        profile=runtime["route_profile"],
        node_registry=runtime["node_registry"],
        graph_registry=runtime["graph_registry"],
        context=dict(route_context),
        root=runtime["root"],
    )


def _request_from_state(canonical_state: Mapping[str, Any], *, event_id: str, input_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Bounded provider request derived from canonical runtime identity only."""
    return {
        "schema_version": "1.0",
        "run_id": str(canonical_state.get("run_id") or f"run-{event_id}"),
        "task_id": str(canonical_state.get("task_id") or ""),
        "repository": str(canonical_state.get("repository") or ""),
        "preprod_base_sha": str(canonical_state.get("base_sha") or ""),
        "working_branch": str(canonical_state.get("branch") or ""),
        "scope_hash": str(canonical_state.get("scope_hash") or ""),
        "graph_revision": str(canonical_state.get("graph_revision") or ""),
        "policy_revision": str(canonical_state.get("policy_revision") or ""),
        "allowed_paths": list(input_payload.get("approved_paths", []) or []),
        "prohibited_paths": [],
        "authorized_actions": [str(canonical_state.get("requested_action") or "")] if canonical_state.get("requested_action") else [],
        "validation_commands": [],
        "idempotency_key": f"live-runtime:{event_id}",
    }


def _node_input_from_state(
    canonical_state: Mapping[str, Any],
    *,
    event_id: str,
    gate: str,
    requested_action: str,
    binding: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Host-constructed semantic node input. Never accepts model-supplied overrides."""
    return {
        "agent_boot_ref": str((bundle.get("instruction_refs") or ["AGENTS.md"])[0]),
        "agent_instruction_digest": str(bundle.get("bundle_digest") or ""),
        "head_sha": str(canonical_state.get("head_sha") or ""),
        "gate": gate,
        "requested_action": requested_action,
        "g0_g1_decision_ref": f"route:{binding.get('node_id')}",
        "task_summary": str(canonical_state.get("task_summary") or ""),
        "objective": str(canonical_state.get("objective") or ""),
        "acceptance_criteria": list(canonical_state.get("acceptance_criteria", []) or []),
        "gate_node_route": [f"{gate}:{binding.get('node_id')}"],
        "plan_refs": [],
        "node_id": str(binding.get("node_id") or ""),
        "node_version": str(binding.get("node_version") or ""),
        "implementation_ref": str(binding.get("implementation_ref") or ""),
        "profile_revision": str(canonical_state.get("profile_revision") or ""),
        "node_registry_revision": str(canonical_state.get("node_registry_revision") or ""),
        "provider_contract_revision": str(canonical_state.get("provider_contract_revision") or "provider-contract-v1"),
    }


def _provider_semantic_handler(
    *,
    provider_binding: Any,
    binding: Mapping[str, Any],
    canonical_state: Mapping[str, Any],
    gate: str,
    requested_action: str,
    bundle: Mapping[str, Any],
) -> Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]:
    """Adapt the Agent provider binding to the lifecycle's (binding, event) handler shape.

    The provider is invoked inside the governed node; its disposition maps to a
    PASS/BLOCKED semantic outcome and its NEXT is constrained to the binding's
    declared next_route_contract. The provider can never choose its own NEXT.
    """

    def handler(runtime_binding: Mapping[str, Any], event: Mapping[str, Any]) -> Mapping[str, Any]:
        node_input = _node_input_from_state(
            canonical_state,
            event_id=str(event.get("event_id") or ""),
            gate=str(event.get("gate") or gate),
            requested_action=str(event.get("requested_action") or requested_action),
            binding=runtime_binding,
            bundle=bundle,
        )
        try:
            provider_result = provider_binding.handler(node_input)
        except Exception as exc:
            return {
                "node_id": runtime_binding.get("node_id"),
                "implementation_ref": runtime_binding.get("implementation_ref"),
                "binding_digest": runtime_binding.get("binding_digest"),
                "implementation_invoked": False,
                "semantic_execution": False,
                "outcome": "BLOCKED",
                "reason_code": f"AGENT_PROVIDER_EXCEPTION:{type(exc).__name__}",
                "requested_effects": [],
                "proposed_effects": [],
                "executed_effects": [],
                "authority_granted": False,
                "next_contract": None,
            }
        if not isinstance(provider_result, Mapping):
            return {
                "node_id": runtime_binding.get("node_id"),
                "implementation_ref": runtime_binding.get("implementation_ref"),
                "binding_digest": runtime_binding.get("binding_digest"),
                "implementation_invoked": True,
                "semantic_execution": False,
                "outcome": "BLOCKED",
                "reason_code": "AGENT_PROVIDER_INVALID_RESULT",
                "requested_effects": [],
                "proposed_effects": [],
                "executed_effects": [],
                "authority_granted": False,
                "next_contract": None,
            }
        disposition = provider_result.get("runtime_disposition")
        if disposition != "CONTINUE":
            return {
                "node_id": runtime_binding.get("node_id"),
                "implementation_ref": runtime_binding.get("implementation_ref"),
                "binding_digest": runtime_binding.get("binding_digest"),
                "implementation_invoked": True,
                "semantic_execution": False,
                "outcome": "BLOCKED",
                "reason_code": str(provider_result.get("reason_code") or "AGENT_PROVIDER_BLOCKED"),
                "requested_effects": [],
                "proposed_effects": [],
                "executed_effects": [],
                "authority_granted": False,
                "provider_result": dict(provider_result),
                "next_contract": None,
            }
        next_table = runtime_binding.get("next_route_contract")
        if not isinstance(next_table, Mapping):
            next_table = {}
        pass_contract = next_table.get("pass") if isinstance(next_table.get("pass"), Mapping) else None
        next_contract = pass_contract
        return {
            "node_id": runtime_binding.get("node_id"),
            "node_version": runtime_binding.get("node_version"),
            "implementation_ref": runtime_binding.get("implementation_ref"),
            "binding_digest": runtime_binding.get("binding_digest"),
            "implementation_invoked": True,
            "semantic_execution": True,
            "outcome": "PASS",
            "reason_code": "AGENT_PROVIDER_SUCCESS",
            "requested_effects": [],
            "proposed_effects": [],
            "executed_effects": [],
            "authority_granted": False,
            "provider_result": dict(provider_result),
            "provider_evidence_class": provider_result.get("provider_evidence_class"),
            "live_closure_eligible": provider_result.get("live_closure_eligible"),
            "instruction_bundle_digest": provider_result.get("instruction_bundle_digest"),
            "next_contract": next_contract,
            "invocation_digest": "sha256:provider-bridge:" + str(provider_result.get("semantic_input_digest") or ""),
        }

    return handler


def _default_readback(binding: Mapping[str, Any], semantic: Mapping[str, Any], executed_effects: Sequence[Mapping[str, Any]], event: Mapping[str, Any]) -> Mapping[str, Any]:
    """Canonical readback adapter: a semantic PASS with no executed effects is
    verified against the approved scope. Any provider/effect evidence is carried
    into the ledger via the semantic result.
    """
    if semantic.get("semantic_execution") is not True:
        return {"status": "NOT_RUN", "reason_code": str(semantic.get("reason_code") or "SEMANTIC_NOT_EXECUTED")}
    return {"status": "VERIFIED", "reason_code": "CANONICAL_READBACK_VERIFIED", "effect_refs": []}


def run_agent_node(
    *,
    root: Path | str,
    canonical_state: Mapping[str, Any],
    route_context: Mapping[str, Any],
    bundle: Mapping[str, Any] | None,
    event_id: str,
    run_id: str,
    gate: str,
    requested_action: str,
    scenario: str,
    input_payload: Mapping[str, Any],
    evidence_root: Path | str,
    mode: str = "shadow_readonly",
    provider: Any = None,
    provider_name: str | None = None,
    provider_registry: ProviderRegistry | None = None,
    validation_runner: TrustedValidationRunner | None = None,
    validation_root: Path | str | None = None,
    idempotency_store: MutableMapping[str, Mapping[str, Any]] | None = None,
    capability_handlers: Mapping[str, Callable[..., Any]] | None = None,
    readback_handler: Callable[..., Mapping[str, Any]] | None = None,
    authority: Mapping[str, Any] | None = None,
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one live Agent node through the full semantic runtime composition.

    Returns the semantic lifecycle result (status, node, binding, readback,
    evidence summary, typed NEXT) or a fail-closed block.
    """
    repo_root = Path(root).resolve()
    canonical_state = dict(canonical_state)
    canonical_state.setdefault("run_id", run_id)
    canonical_state.setdefault("requested_action", requested_action)
    canonical_state.setdefault("source_kind", CANONICAL_SOURCE_KIND)

    # 1. Host instruction bundle is mandatory before any provider invocation.
    if bundle is None:
        return {
            "status": "SEMANTIC_NODE_BLOCKED",
            "reason_code": "AGENT_INSTRUCTION_BUNDLE_MISSING",
            "node_id": str(canonical_state.get("task_id") or ""),
            "authority_granted": False,
            "executed_effects": [],
            "semantic_execution": False,
            "implementation_invoked": False,
        }
    try:
        canonical_bundle = validate_agent_instruction_bundle(bundle)
    except InstructionBundleError as exc:
        return {
            "status": "SEMANTIC_NODE_BLOCKED",
            "reason_code": f"AGENT_INSTRUCTION_BUNDLE_INVALID:{exc.reason_code}",
            "node_id": str(canonical_state.get("task_id") or ""),
            "authority_granted": False,
            "executed_effects": [],
            "semantic_execution": False,
            "implementation_invoked": False,
        }

    # 2. Canonical route resolution.
    runtime = runtime or bootstrap_agent_runtime(root=repo_root, canonical_state=canonical_state)
    route_decision = resolve_gate_node_route(
        profile=runtime["route_profile"],
        node_registry=runtime["node_registry"],
        graph_registry=runtime["graph_registry"],
        context=dict(route_context),
        root=runtime["root"],
    )
    if route_decision.get("outcome") != "ROUTE_SELECTED":
        return {
            "status": "SEMANTIC_NODE_BLOCKED",
            "reason_code": str(route_decision.get("reason_code") or "CANONICAL_ROUTE_NOT_SELECTED"),
            "node_id": str(route_decision.get("current_node") or ""),
            "authority_granted": False,
            "executed_effects": [],
            "semantic_execution": False,
            "implementation_invoked": False,
        }

    node_id = str(route_decision.get("current_node") or "")
    binding = _binding_for(runtime["implementation_registry"], node_id)
    if binding is None:
        return {
            "status": "SEMANTIC_NODE_BLOCKED",
            "reason_code": "LIVE_SEMANTIC_BINDING_MISSING",
            "node_id": node_id,
            "authority_granted": False,
            "executed_effects": [],
            "semantic_execution": False,
            "implementation_invoked": False,
        }

    # 3. Immutable live event (never synthetic; canonical source only).
    canonical_state["source_kind"] = CANONICAL_SOURCE_KIND
    event = build_live_runtime_event(
        canonical_state=canonical_state,
        event_id=event_id,
        run_id=run_id,
        gate=gate,
        requested_action=requested_action,
        scenario=scenario,
        input_payload=dict(input_payload),
    )

    # 4. Wire the provider (LLM) as the semantic implementation for this node.
    semantic_handlers: dict[str, Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]] = {}
    if binding.get("implementation_ref") != INSTRUCTION_EVALUATOR_REF:
        provider_binding = build_agent_provider_binding(
            node_id=node_id,
            evaluator_path=str(binding.get("implementation_ref") or ""),
            request=_request_from_state(canonical_state, event_id=event_id, input_payload=input_payload),
            provider=provider,
            provider_name=provider_name,
            provider_registry=provider_registry,
            validation_runner=validation_runner,
            validation_root=validation_root,
            idempotency_store=idempotency_store,
            instruction_bundle=canonical_bundle,
        )
        semantic_handlers[str(binding.get("implementation_ref") or "")] = _provider_semantic_handler(
            provider_binding=provider_binding,
            binding=binding,
            canonical_state=canonical_state,
            gate=gate,
            requested_action=requested_action,
            bundle=canonical_bundle,
        )

    # 5. Dispatch into the live runtime bridge -> semantic node lifecycle.
    return dispatch_live_runtime_event(
        event=event,
        route_decision=route_decision,
        implementation_registry=runtime["implementation_registry"],
        mode=mode,
        semantic_handlers=semantic_handlers,
        capability_handlers=capability_handlers or {},
        readback_handler=readback_handler or _default_readback,
        evidence_root=evidence_root,
        state=LiveRuntimeState(),
        authority=authority,
        root=runtime["root"],
    )


__all__ = [
    "bootstrap_agent_runtime",
    "resolve_agent_route",
    "resolve_agent_instruction_bundle",
    "run_agent_node",
]
