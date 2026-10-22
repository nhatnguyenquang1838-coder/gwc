#!/usr/bin/env python3
"""Production Agent Host entrypoint into the Node Architect semantic runtime.

This is the missing top-level wiring between repository Agent instructions and
skills, canonical route selection, one exact semantic node binding, an LLM/Agent
reasoning provider, the W12 authority/capability boundary, canonical readback,
evidence ledger, and typed NEXT.

The provider is a reasoner, not an authority or tool executor. It may return a
typed outcome, tool requests, and a key selecting one predeclared NEXT contract.
It may not supply route/gate/authority objects or executed effects. Repository
instructions/skills are host-selected and materialized before provider invocation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .agent_instruction_bundle import InstructionBundleError, resolve_agent_instruction_bundle
from .build_node_instruction_pack import build_node_instruction_pack
from .canonical_readback import verify_canonical_readback
from .live_runtime_bridge import LiveRuntimeState, build_live_runtime_event, dispatch_live_runtime_event
from .ai_agent_adapter import DeterministicFakeProvider, Provider, SUCCESS, execute
from .resolve_gate_node_route import resolve_gate_node_route
from .semantic_implementation_registry import compile_semantic_implementation_registry
from .agent_provider_bridge import ProviderRegistry, build_agent_provider_binding

RouteResolver = Callable[..., Mapping[str, Any]]


def _resolve_provider_gate(provider: Any, provider_registry: Any) -> tuple[str, bool, Any]:
    """Classify a provider and compute live-closure eligibility.

    Mirrors ``agent_provider_bridge._provider_class`` so the Agent Host enforces
    the same gate the W11 bridge applies: an authoritative provider must resolve
    from a configured ``provider_registry`` to be live-closure eligible. Synthetic
    and direct-injection providers are never live-eligible (reasoner/test only).
    Returns ``(evidence_class, live_closure_eligible, resolved_provider)``.
    """
    if provider is None:
        return "UNAVAILABLE", False, provider
    if isinstance(provider, DeterministicFakeProvider) or getattr(provider, "name", "") == "deterministic-fake":
        return "SYNTHETIC_TEST_ONLY", False, provider
    if provider_registry is not None:
        resolved = provider_registry.resolve(getattr(provider, "name", ""))
        if resolved is not None:
            return "CONFIGURED_PROVIDER", True, resolved
        return "DIRECT_INJECTION", False, provider
    return "DIRECT_INJECTION", False, provider

_FORBIDDEN_PROVIDER_FIELDS = {
    "authority",
    "authority_granted",
    "write_authority_granted",
    "pr_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
    "executed_effects",
    "next_contract",
    "next_node",
    "next_action",
    "next_gate",
    "route_decision",
    "route_id",
}
_ALLOWED_OUTCOMES = {"PASS", "PENDING", "WAIT", "RETRY", "NOT_APPLICABLE", "BLOCKED", "FAIL"}


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _blocked(reason_code: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "AGENT_RUNTIME_BLOCKED",
        "reason_code": reason_code,
        "agent_runtime_wired": False,
        "authority_granted": False,
        "executed_effects": [],
        "automatic_gate_advance": False,
        **extra,
    }


def _binding_for(registry: Mapping[str, Any], node_id: str) -> Mapping[str, Any] | None:
    matches = [
        item for item in registry.get("bindings", [])
        if isinstance(item, Mapping) and item.get("node_id") == node_id
    ]
    return matches[0] if len(matches) == 1 else None


def _route_context(
    *,
    canonical_state: Mapping[str, Any],
    run_id: str,
    gate: str,
    requested_action: str,
    workflow_mode: str,
    input_payload: Mapping[str, Any],
    supplied: Mapping[str, Any] | None,
) -> dict[str, Any]:
    context = dict(supplied or {})
    context.update({
        "task_id": str(canonical_state.get("task_id") or context.get("task_id") or ""),
        "run_id": run_id,
        "gate": gate,
        "requested_action": requested_action,
        "workflow_mode": workflow_mode,
        "repository": str(canonical_state.get("repository") or ""),
        "base_sha": str(canonical_state.get("base_sha") or ""),
        "working_branch": str(canonical_state.get("branch") or ""),
        "scope_hash": str(canonical_state.get("scope_hash") or ""),
        "expected_profile_revision": str(canonical_state.get("profile_revision") or ""),
        "expected_graph_revision": str(canonical_state.get("graph_revision") or ""),
    })
    # Canonical route resolution owns required-context validation. The Agent Host
    # supplies the immutable task/gate context; provider/model output never does.
    context.setdefault("context", dict(input_payload))
    return context


def _provider_request(
    *,
    canonical_state: Mapping[str, Any],
    run_id: str,
    event_id: str,
    route: Mapping[str, Any],
    binding: Mapping[str, Any],
    capability_handlers: Mapping[str, Any],
    authority: Mapping[str, Any] | None = None,
    validation_commands: Sequence[str] = (),
) -> dict[str, Any]:
    # File/path scope is an authority concern. It is carried from the resolved
    # authority when present; absent authority means a reasoner-only envelope
    # (any write is out-of-scope downstream). The model never populates this.
    if isinstance(authority, Mapping):
        allowed_paths = list(authority.get("allowed_paths", []) or [])
        prohibited_paths = list(authority.get("prohibited_paths", []) or [])
    else:
        allowed_paths = []
        prohibited_paths = []
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "task_id": str(canonical_state.get("task_id") or ""),
        "repository": str(canonical_state.get("repository") or ""),
        "preprod_base_sha": str(canonical_state.get("base_sha") or ""),
        "working_branch": str(canonical_state.get("branch") or ""),
        "scope_hash": str(canonical_state.get("scope_hash") or ""),
        "graph_revision": str(canonical_state.get("graph_revision") or ""),
        "policy_revision": str(canonical_state.get("policy_revision") or ""),
        # The LLM can request only capabilities exposed by the host. File/path
        # scope is derived from authority above; model output never sets it.
        "allowed_paths": allowed_paths,
        "prohibited_paths": prohibited_paths,
        "authorized_actions": sorted(map(str, capability_handlers.keys())),
        "validation_commands": list(map(str, validation_commands)),
        "idempotency_key": f"agent-runtime:{event_id}:{binding.get('node_id', '')}",
        "route_id": str(route.get("route_id") or ""),
    }


def _prepare_m1_m7_checkpoint(
    *, root: Path, selection: Mapping[str, Any], operation: Mapping[str, Any]
) -> tuple[Path, int, dict[str, Any], dict[str, Any] | None]:
    """Read/reconcile the same-run checkpoint before replaying graph work."""
    from .checkpoint_store import CheckpointInput, load_store, reconcile_unknown_outcome, replay_checkpoint, validate_readback
    run_id = operation.get("run_id")
    if not isinstance(run_id, str) or not run_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for ch in run_id):
        raise ValueError("CHECKPOINT_RUN_ID_INVALID")
    expected_ref = f".gwc/tasks/SCRUM-841/g2/checkpoints/{run_id}.json"
    checkpoint_ref = selection.get("checkpoint_store_ref", expected_ref)
    if checkpoint_ref != expected_ref:
        raise ValueError("CHECKPOINT_STORE_PATH_NOT_RUN_BOUND")
    path = (root / checkpoint_ref).resolve()
    allowed_root = (root / ".gwc/tasks/SCRUM-841/g2/checkpoints").resolve()
    if not path.is_relative_to(allowed_root):
        raise ValueError("CHECKPOINT_STORE_PATH_OUTSIDE_SCOPE")
    exists = path.exists()
    store = load_store(path)
    expected_revision = selection.get("checkpoint_expected_revision")
    actual_revision = int(store.get("revision", 0))
    if expected_revision is None and not exists:
        expected_revision = 0
    if not isinstance(expected_revision, int) or expected_revision < 0 or expected_revision != actual_revision:
        raise ValueError("CHECKPOINT_CAS_REVISION_MISMATCH")
    if not exists:
        return path, expected_revision, store, None
    node_id = "scrum841-m1-m7-workflow"
    record = replay_checkpoint(store, "SCRUM-841", run_id, node_id)
    if not isinstance(record, Mapping):
        raise ValueError("CHECKPOINT_UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION")
    binding = {
        "task_id": operation.get("task_id"), "repository": operation.get("repository"),
        "branch": operation.get("working_branch"), "base_sha": operation.get("base_sha"),
        "head_sha": operation.get("head_sha"), "scope_hash": operation.get("scope_hash"),
    }
    if any(record.get(key) != value for key, value in binding.items()):
        raise ValueError("CHECKPOINT_BINDING_DRIFT")
    item = CheckpointInput(
        task_id="SCRUM-841", run_id=run_id, node_id=node_id,
        repository=str(operation["repository"]), branch=str(operation["working_branch"]),
        base_sha=str(operation["base_sha"]), head_sha=str(operation["head_sha"]),
        scope_hash=str(operation["scope_hash"]), state=dict(record.get("state") or {}),
        expected_revision=expected_revision, graph_revision="scrum841-m1-m7-agent-workflow-r1",
    )
    if reconcile_unknown_outcome(store, item).get("outcome") != "KNOWN_STATE":
        raise ValueError("CHECKPOINT_UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION")
    validate_readback(store, item)
    return path, expected_revision, store, dict(record.get("state") or {})


def _run_selected_m1_m7_workflow(
    *,
    selection: Mapping[str, Any],
    canonical_state: Mapping[str, Any],
    current_binding: Mapping[str, Any],
    root: Path,
) -> dict[str, Any]:
    """Run the explicit inner graph inside the already-resolved canonical host node."""
    allowed_selection_keys = {
        "workflow_id", "operation_envelope", "inputs", "prior_host_action_requests",
        "prior_controller_exchange_requests", "prior_settlement_requests",
        "checkpoint_store_ref", "checkpoint_expected_revision",
    }
    if set(selection) - allowed_selection_keys or selection.get("workflow_id") != "scrum841-m1-m7-agent-workflow-r1":
        return {"outcome": "BLOCKED", "reason_code": "WORKFLOW_SELECTION_INVALID", "requested_effects": [], "proposed_effects": [], "executed_effects": [], "authority_granted": False}
    operation = selection.get("operation_envelope")
    inputs = selection.get("inputs")
    if not isinstance(operation, Mapping) or not isinstance(inputs, Mapping):
        return {"outcome": "BLOCKED", "reason_code": "WORKFLOW_OPERATION_ENVELOPE_INVALID", "requested_effects": [], "proposed_effects": [], "executed_effects": [], "authority_granted": False}
    try:
        from .m1_m7_agent_workflow import build_m1_m7_graph, load_m1_m7_contracts
        manifest, profile = load_m1_m7_contracts(root)
        exact = {
            "task_id": "task_id", "repository": "repository", "base_sha": "base_sha",
            "head_sha": "head_sha", "working_branch": "branch", "scope_hash": "scope_hash",
        }
        if any(operation.get(op_key) != canonical_state.get(state_key) for op_key, state_key in exact.items()):
            return {"outcome": "BLOCKED", "reason_code": "WORKFLOW_CANONICAL_STATE_MISMATCH", "requested_effects": [], "proposed_effects": [], "executed_effects": [], "authority_granted": False}
        graph = build_m1_m7_graph(workflow_manifest=manifest, runtime_profile=profile, activity_source_sha256=manifest["source_sha256"])
        initial: dict[str, Any] = {
            "operation_envelope": dict(operation), "inputs": dict(inputs),
            "host_action_requests": [], "settlement_requests": [],
            "child_dispatch_requests": [], "controller_exchange_requests": [],
            "activity_results": {}, "authority_granted": False, "executed_effects": [],
        }
        for key in ("prior_host_action_requests", "prior_controller_exchange_requests", "prior_settlement_requests"):
            if key in selection:
                initial[key] = selection[key]
        checkpoint_path, expected_revision, checkpoint_store, prior_projection = _prepare_m1_m7_checkpoint(
            root=root, selection=selection, operation=operation
        )
        if prior_projection is not None:
            initial["checkpoint_projection"] = prior_projection
            initial["activity_results"] = dict(prior_projection.get("activity_results") or {})
            initial["mailbox_classification"] = prior_projection.get("mailbox_classification")
            prior_keys = list(prior_projection.get("idempotency_keys") or [])
            if prior_keys:
                initial["host_action_requests"] = [{"idempotency_key": key} for key in prior_keys]
            controller_keys = list(prior_projection.get("controller_exchange_idempotency_keys") or [])
            if controller_keys:
                initial["controller_exchange_requests"] = [{"idempotency_key": key} for key in controller_keys]
            settlement_keys = list(prior_projection.get("settlement_idempotency_keys") or [])
            if settlement_keys:
                initial["settlement_requests"] = [{"idempotency_key": key} for key in settlement_keys]
            resumed_inputs = dict(initial["inputs"])
            for input_key, persisted in (
                ("prior_host_action_requests", initial["host_action_requests"]),
                ("prior_controller_exchange_requests", initial["controller_exchange_requests"]),
                ("prior_settlement_requests", initial["settlement_requests"]),
            ):
                existing = resumed_inputs.get(input_key, [])
                existing = existing if isinstance(existing, list) else []
                seen = {item.get("idempotency_key") for item in existing if isinstance(item, Mapping)}
                resumed_inputs[input_key] = existing + [item for item in persisted if isinstance(item, Mapping) and item.get("idempotency_key") not in seen]
            initial["inputs"] = resumed_inputs
        raw = graph.invoke(initial)
        prior_checkpoint = initial.get("checkpoint_projection")
        prior_checkpoint = prior_checkpoint if isinstance(prior_checkpoint, Mapping) else {}
        activity_results = raw.get("activity_results")
        activity_results = activity_results if isinstance(activity_results, Mapping) else dict(prior_checkpoint.get("activity_results") or {})
        def _idempotency_values(state_key: str, projection_key: str) -> list[str]:
            values: list[str] = list(prior_checkpoint.get(projection_key) or [])
            for source in (initial.get(state_key, []), raw.get(state_key, [])):
                if isinstance(source, list):
                    for item in source:
                        key = item.get("idempotency_key") if isinstance(item, Mapping) else None
                        if isinstance(key, str) and key:
                            values.append(key)
            return list(dict.fromkeys(values))
        projection = {
            key: operation[key] for key in (
                "task_id", "repository", "run_id", "operation_id", "activity_id",
                "base_sha", "head_sha", "working_branch", "scope_hash",
                "runtime_plan_digest", "protocol_version", "continuation_ref", "cursor",
            ) if key in operation
        }
        projection.update({
            "current_activity": raw.get("current_activity") or prior_checkpoint.get("current_activity") or "M1",
            "mailbox_classification": raw.get("mailbox_classification") or prior_checkpoint.get("mailbox_classification"),
            "activity_results": dict(activity_results),
            "receipt_refs": list(dict.fromkeys(
                value.get("readback_digest") for value in activity_results.values()
                if isinstance(value, Mapping) and value.get("readback_digest")
            )),
            "idempotency_keys": _idempotency_values("host_action_requests", "idempotency_keys"),
            "controller_exchange_idempotency_keys": _idempotency_values("controller_exchange_requests", "controller_exchange_idempotency_keys"),
            "settlement_idempotency_keys": _idempotency_values("settlement_requests", "settlement_idempotency_keys"),
        })
        if isinstance(prior_checkpoint.get("gate_readout"), Mapping):
            projection["gate_readout"] = dict(prior_checkpoint["gate_readout"])
        from .checkpoint_store import CheckpointInput, digest_payload, load_store, persist_to_file, replay_checkpoint, validate_readback
        exists = checkpoint_path.exists()
        item = CheckpointInput(
            task_id=str(operation["task_id"]), run_id=str(operation["run_id"]),
            node_id="scrum841-m1-m7-workflow", repository=str(operation["repository"]),
            branch=str(operation["working_branch"]), base_sha=str(operation["base_sha"]),
            head_sha=str(operation["head_sha"]), scope_hash=str(operation["scope_hash"]),
            state=dict(projection), expected_revision=expected_revision,
            graph_revision=str(manifest["workflow_id"]),
        )
        prior_record = replay_checkpoint(checkpoint_store, item.task_id, item.run_id, item.node_id)
        if prior_record is not None and prior_record.get("state_digest") == digest_payload(item.state):
            checkpoint_result = {"outcome": "IDEMPOTENT_REPLAY", "revision": prior_record.get("revision"), "state_digest": prior_record.get("state_digest"), "store_path": str(checkpoint_path)}
        else:
            persist_to_file(checkpoint_path, item)
            checkpoint_result = {**validate_readback(load_store(checkpoint_path), item), "store_path": str(checkpoint_path)}
    except (ImportError, ModuleNotFoundError) as exc:
        return {"outcome": "BLOCKED", "reason_code": "LANGGRAPH_BACKEND_UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}", "requested_effects": [], "proposed_effects": [], "executed_effects": [], "authority_granted": False}
    except Exception as exc:
        return {"outcome": "BLOCKED", "reason_code": "M1_M7_GRAPH_OR_CHECKPOINT_ERROR", "error": f"{type(exc).__name__}: {exc}", "requested_effects": [], "proposed_effects": [], "executed_effects": [], "authority_granted": False}

    graph_status = str(raw.get("status") or "BLOCKED")
    outcome = "WAIT" if graph_status in {"HOLD", "WAIT"} else "BLOCKED" if graph_status in {"BLOCKED", "FAIL"} else "PASS" if graph_status == "CONTINUE" else "BLOCKED"
    next_table = current_binding.get("next_route_contract")
    if not isinstance(next_table, Mapping):
        return {"outcome": "BLOCKED", "reason_code": "M1_M7_NEXT_CONTRACT_MISSING", "requested_effects": [], "proposed_effects": [], "executed_effects": [], "authority_granted": False}
    next_key = "pending" if outcome == "WAIT" else "pass" if outcome == "PASS" else "blocked"
    next_contract = next_table.get(next_key)
    if not isinstance(next_contract, Mapping):
        next_contract = next_table.get("blocked")
    if not isinstance(next_contract, Mapping):
        return {"outcome": "BLOCKED", "reason_code": "M1_M7_NEXT_CONTRACT_INVALID", "requested_effects": [], "proposed_effects": [], "executed_effects": [], "authority_granted": False}
    public = {
        key: raw[key] for key in (
            "status", "reason_code", "current_activity", "mailbox_classification",
            "activity_results", "host_action_requests", "controller_exchange_requests",
            "settlement_requests", "checkpoint_projection", "child_dispatch_requests",
        ) if key in raw
    }
    return {
        "outcome": outcome,
        "reason_code": str(raw.get("reason_code") or "M1_M7_RESULT_UNTYPED"),
        "provider": "langgraph:scrum841-m1-m7-agent-workflow-r1",
        "requested_effects": [],
        "proposed_effects": [],
        "executed_effects": [],
        "authority_granted": False,
        "implementation_invoked": True,
        "semantic_execution": True,
        "next_contract": dict(next_contract),
        "workflow_result": public,
        "checkpoint_persistence": checkpoint_result,
        "invocation_digest": _digest({"selection": selection, "result": public, "checkpoint": checkpoint_result}),
    }


def _provider_semantic_handler(
    *,
    provider: Any,
    provider_request: Mapping[str, Any],
    bundle: Mapping[str, Any],
    canonical_state: Mapping[str, Any],
    gate: str,
    requested_action: str,
    route: Mapping[str, Any],
    binding: Mapping[str, Any],
    input_payload: Mapping[str, Any],
    capability_handlers: Mapping[str, Any],
    provider_binding: Any | None = None,
    workflow_root: Path | None = None,
) -> Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]:
    def handler(current_binding: Mapping[str, Any], event: Mapping[str, Any]) -> Mapping[str, Any]:
        selection = input_payload.get("_scrum841_workflow_selection")
        if selection is not None:
            return _run_selected_m1_m7_workflow(
                selection=selection,
                canonical_state=canonical_state,
                current_binding=current_binding,
                root=workflow_root or Path("."),
            )
        if provider_binding is not None:
            bridge_input = {
                "head_sha": str(canonical_state.get("head_sha") or ""),
                "gate": gate,
                "requested_action": requested_action,
                "g0_g1_decision_ref": str(input_payload.get("g0_g1_decision_ref") or ""),
                "task_summary": str(input_payload.get("task_summary") or ""),
                "objective": str(input_payload.get("objective") or requested_action),
                "node_id": str(current_binding.get("node_id") or ""),
                "node_version": str(current_binding.get("node_version") or ""),
                "implementation_ref": str(current_binding.get("implementation_ref") or ""),
                "profile_revision": str(canonical_state.get("profile_revision") or ""),
                "node_registry_revision": str(canonical_state.get("node_registry_revision") or ""),
                "provider_contract_revision": str(getattr(provider, "contract_revision", "agent-reasoning-v1")),
                "agent_boot_ref": str(bundle.get("instruction_refs", [""])[0] if bundle.get("instruction_refs") else ""),
                "agent_instruction_digest": str(bundle.get("bundle_digest") or ""),
                "acceptance_criteria": tuple(map(str, input_payload.get("acceptance_criteria", ()) or ())),
                "gate_node_route": (f"{gate}:{current_binding.get('node_id', '')}",),
                "plan_refs": tuple(map(str, input_payload.get("plan_refs", ()) or ())),
            }
            try:
                bridged = provider_binding.handler(bridge_input)
            except Exception as exc:
                return {
                    "outcome": "BLOCKED",
                    "reason_code": "LLM_PROVIDER_BRIDGE_ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                    "requested_effects": [],
                    "proposed_effects": [],
                    "executed_effects": [],
                    "next_contract": current_binding.get("next_route_contract", {}).get("blocked"),
                    "authority_granted": False,
                    "implementation_invoked": False,
                    "semantic_execution": False,
                }
            if not isinstance(bridged, Mapping):
                return {
                    "outcome": "BLOCKED",
                    "reason_code": "LLM_PROVIDER_BRIDGE_INVALID_RESULT",
                    "requested_effects": [],
                    "proposed_effects": [],
                    "executed_effects": [],
                    "next_contract": current_binding.get("next_route_contract", {}).get("blocked"),
                    "authority_granted": False,
                    "implementation_invoked": False,
                    "semantic_execution": False,
                }
            if bridged.get("runtime_disposition") != "CONTINUE":
                return {
                    "outcome": "BLOCKED",
                    "reason_code": str(bridged.get("reason_code") or "LLM_PROVIDER_BRIDGE_BLOCKED"),
                    "provider_result": dict(bridged.get("provider_result") or {}),
                    "requested_effects": [],
                    "proposed_effects": [],
                    "executed_effects": [],
                    "next_contract": current_binding.get("next_route_contract", {}).get("blocked"),
                    "authority_granted": False,
                    "implementation_invoked": True,
                    "semantic_execution": True,
                }
            provider_result = dict(bridged.get("provider_result") or {})
            requested_effects = [
                {"action": str(action), "side_effect_class": current_binding.get("side_effect_class") or "read_only"}
                for action in provider_result.get("recorded_actions", []) or []
                if str(action)
            ]
            return {
                "outcome": "PASS",
                "reason_code": "LLM_PROVIDER_SUCCESS",
                "provider_result": provider_result,
                "requested_effects": requested_effects,
                "proposed_effects": [],
                "executed_effects": [],
                "next_contract": current_binding.get("next_route_contract", {}).get("pass"),
                "authority_granted": False,
                "implementation_invoked": True,
                "semantic_execution": True,
                "invocation_digest": _digest({"bridge": provider_result, "node": current_binding.get("node_id")}),
            }

        # Bind the actual host-resolved instruction/skill bytes into the exact
        # provider replay identity. Model-supplied skill/instruction fields are
        # intentionally ignored.
        pack = build_node_instruction_pack(
            provider_request,
            head_sha=str(canonical_state.get("head_sha") or ""),
            gate=gate,
            requested_action=requested_action,
            task_summary=str(input_payload.get("task_summary") or ""),
            objective=str(input_payload.get("objective") or requested_action),
            acceptance_criteria=tuple(map(str, input_payload.get("acceptance_criteria", ()) or ())),
            gate_node_route=(f"{gate}:{binding.get('node_id', '')}",),
            plan_refs=tuple(map(str, input_payload.get("plan_refs", ()) or ())),
            node_id=str(binding.get("node_id") or ""),
            node_version=str(binding.get("node_version") or ""),
            implementation_ref=str(binding.get("implementation_ref") or ""),
            profile_revision=str(canonical_state.get("profile_revision") or ""),
            node_registry_revision=str(canonical_state.get("node_registry_revision") or ""),
            provider_contract_revision=str(getattr(provider, "contract_revision", "agent-reasoning-v1")),
            semantic_input_digest=_digest(dict(input_payload)),
            instruction_bundle=bundle,
        )
        try:
            raw = provider.run(pack)
        except Exception as exc:
            return {
                "outcome": "BLOCKED",
                "reason_code": "LLM_PROVIDER_ERROR",
                "provider_error": f"{type(exc).__name__}: {exc}",
                "requested_effects": [],
                "proposed_effects": [],
                "executed_effects": [],
                "next_contract": current_binding.get("next_route_contract", {}).get("blocked"),
                "authority_granted": False,
            }
        if not isinstance(raw, Mapping):
            return {
                "outcome": "BLOCKED",
                "reason_code": "LLM_PROVIDER_INVALID_RESULT",
                "requested_effects": [],
                "proposed_effects": [],
                "executed_effects": [],
                "next_contract": current_binding.get("next_route_contract", {}).get("blocked"),
                "authority_granted": False,
            }
        if any(field in raw for field in _FORBIDDEN_PROVIDER_FIELDS):
            return {
                "outcome": "BLOCKED",
                "reason_code": "LLM_PROVIDER_ROUTE_OR_AUTHORITY_INJECTION",
                "requested_effects": [],
                "proposed_effects": [],
                "executed_effects": [],
                "next_contract": current_binding.get("next_route_contract", {}).get("blocked"),
                "authority_granted": False,
            }

        outcome = str(raw.get("outcome") or "BLOCKED").upper()
        if outcome not in _ALLOWED_OUTCOMES:
            outcome = "BLOCKED"
            reason_code = "LLM_PROVIDER_OUTCOME_INVALID"
        else:
            reason_code = str(raw.get("reason_code") or f"LLM_PROVIDER_{outcome}")

        tool_requests = raw.get("tool_requests", [])
        if not isinstance(tool_requests, list):
            outcome = "BLOCKED"
            reason_code = "LLM_PROVIDER_TOOL_REQUESTS_INVALID"
            tool_requests = []

        requested_effects: list[dict[str, Any]] = []
        if outcome not in {"BLOCKED", "FAIL", "NOT_APPLICABLE"}:
            for item in tool_requests:
                if not isinstance(item, Mapping):
                    outcome = "BLOCKED"
                    reason_code = "LLM_PROVIDER_TOOL_REQUEST_INVALID"
                    requested_effects = []
                    break
                action = item.get("action")
                if not isinstance(action, str) or not action or action not in capability_handlers:
                    outcome = "BLOCKED"
                    reason_code = "LLM_PROVIDER_TOOL_NOT_AUTHORIZED"
                    requested_effects = []
                    break
                effect = dict(item)
                effect.setdefault("side_effect_class", current_binding.get("side_effect_class") or "read_only")
                requested_effects.append(effect)

        next_table = current_binding.get("next_route_contract")
        if not isinstance(next_table, Mapping):
            outcome = "BLOCKED"
            reason_code = "LLM_PROVIDER_NEXT_CONTRACT_UNAVAILABLE"
            next_contract = None
        else:
            key = str(raw.get("next_contract_key") or ("blocked" if outcome in {"BLOCKED", "FAIL"} else "pass"))
            next_contract = next_table.get(key)
            if not isinstance(next_contract, Mapping):
                outcome = "BLOCKED"
                reason_code = "LLM_PROVIDER_NEXT_CONTRACT_KEY_INVALID"
                next_contract = next_table.get("blocked")

        return {
            "outcome": outcome,
            "reason_code": reason_code,
            "provider": str(getattr(provider, "name", type(provider).__name__)),
            "provider_instruction_digest": pack.content_digest,
            "instruction_bundle_digest": pack.instruction_bundle_digest,
            "requested_effects": requested_effects,
            "proposed_effects": [],
            "executed_effects": [],
            "next_contract": dict(next_contract) if isinstance(next_contract, Mapping) else None,
            "authority_granted": False,
        }

    return handler


def run_agent_runtime_event(
    *,
    canonical_state: Mapping[str, Any],
    run_id: str,
    event_id: str,
    gate: str,
    requested_action: str,
    scenario: str,
    workflow_mode: str,
    input_payload: Mapping[str, Any],
    instruction_refs: tuple[str, ...] | list[str],
    role_overlay_refs: tuple[str, ...] | list[str],
    required_skill_names: tuple[str, ...] | list[str],
    provider: Any,
    provider_registry: Any | None = None,
    mode: str,
    authority: Mapping[str, Any] | None,
    capability_handlers: Mapping[str, Any],
    readback_handler: Any,
    evidence_root: Path | str,
    state: LiveRuntimeState | None,
    root: Path | str,
    route_profile: Mapping[str, Any],
    node_registry: Mapping[str, Any],
    graph_registry: Mapping[str, Any],
    implementation_registry: Mapping[str, Any] | None = None,
    route_context: Mapping[str, Any] | None = None,
    route_resolver: RouteResolver = resolve_gate_node_route,
    applicability_decision: Mapping[str, Any] | None = None,
    validation_runner: Any | None = None,
    validation_root: Path | str | None = None,
    internal_receipt_store: Mapping[str, Any] | None = None,
    receipts_persisted: bool = False,
    m1_m7_workflow_selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one canonical Agent task event end-to-end through Node Architect."""
    repo_root = Path(root).resolve()
    if m1_m7_workflow_selection is not None:
        if not isinstance(m1_m7_workflow_selection, Mapping) or m1_m7_workflow_selection.get("workflow_id") != "scrum841-m1-m7-agent-workflow-r1":
            return _blocked("WORKFLOW_SELECTION_INVALID")
        if "_scrum841_workflow_selection" in input_payload:
            return _blocked("WORKFLOW_SELECTION_INPUT_INJECTION")
        input_payload = {**dict(input_payload), "_scrum841_workflow_selection": dict(m1_m7_workflow_selection)}
    context = _route_context(
        canonical_state=canonical_state,
        run_id=run_id,
        gate=gate,
        requested_action=requested_action,
        workflow_mode=workflow_mode,
        input_payload=input_payload,
        supplied=route_context,
    )
    try:
        route = route_resolver(
            profile=route_profile,
            node_registry=node_registry,
            graph_registry=graph_registry,
            context=context,
            root=repo_root,
        )
    except Exception as exc:
        return _blocked("AGENT_ROUTE_RESOLUTION_ERROR", error=f"{type(exc).__name__}: {exc}")
    if not isinstance(route, Mapping) or route.get("outcome") != "ROUTE_SELECTED":
        reason = route.get("reason_code") if isinstance(route, Mapping) else None
        if not reason and isinstance(route, Mapping):
            codes = route.get("reason_codes")
            if isinstance(codes, list) and codes:
                reason = codes[0]
        return _blocked(str(reason or "CANONICAL_ROUTE_NOT_SELECTED"), route_decision=dict(route) if isinstance(route, Mapping) else {})

    node_id = str(route.get("current_node") or "")
    if not node_id:
        return _blocked("AGENT_ROUTE_NODE_MISSING")

    registry = implementation_registry
    if registry is None:
        registry = compile_semantic_implementation_registry(node_registry, root=repo_root)
    if not isinstance(registry, Mapping) or registry.get("status") != "PASS":
        return _blocked("AGENT_SEMANTIC_IMPLEMENTATION_REGISTRY_INVALID")
    binding = _binding_for(registry, node_id)
    if binding is None and node_id == "universal_run.gate-adapter":
        # Compile only the independently admitted slot-83 sidecar binding. The
        # canonical compiler remains exactly the immutable 81-node baseline.
        node = route.get("node") if isinstance(route.get("node"), Mapping) else None
        implementation = route.get("implementation") if isinstance(route.get("implementation"), Mapping) else {}
        implementation_ref = str(implementation.get("ref") or "")
        try:
            from . import semantic_implementation_registry as semantic_registry
            if node is not None:
                binding = semantic_registry.compile_extension_semantic_binding(
                    node=node,
                    implementation_ref=implementation_ref,
                    descriptor_ref=str(route.get("node_descriptor_ref") or ""),
                    instruction_ref=str(route.get("node_instruction_ref") or ""),
                    root=repo_root,
                )
        except Exception:
            binding = None
        if binding is None:
            return _blocked("AGENT_EXTENSION_BINDING_NOT_ADMITTED", node_id=node_id)
        registry = {**dict(registry), "bindings": [*registry.get("bindings", []), binding]}
    if binding is None:
        return _blocked("AGENT_SEMANTIC_BINDING_MISSING_OR_AMBIGUOUS", node_id=node_id)

    extension_binding = node_id == "universal_run.gate-adapter"
    if extension_binding:
        binding = dict(binding)
        binding["node_registry_revision"] = str(canonical_state.get("node_registry_revision") or "")
        binding["next_route_contract"] = {key: dict(value) for key, value in binding["next_route_contract"].items()}
        binding["next_route_contract"]["pass"]["next_gate"] = gate
        binding["next_route_contract"]["blocked"]["next_gate"] = gate
        from .semantic_implementation_registry import _digest as _semantic_digest
        registry = {**dict(registry), "bindings": [
            binding if item.get("node_id") == node_id else item
            for item in registry.get("bindings", []) if isinstance(item, Mapping)
        ]}
        binding["binding_digest"] = _semantic_digest({key: value for key, value in binding.items() if key != "binding_digest"})
        route_payload = context.get("context") if isinstance(context.get("context"), Mapping) else {}
        manifest = route_payload.get("universal_run_manifest")
        target_contract = route_payload.get("target_contract")
        input_payload = {
            **dict(input_payload), "run_id": run_id,
            "run_kind": manifest.get("run_kind") if isinstance(manifest, Mapping) else None,
            "parent_run_ref": manifest.get("parent_run_ref") if isinstance(manifest, Mapping) else None,
            "gate": gate, "action": requested_action,
            "target_contract": target_contract, "manifest": manifest,
            "evidence": route_payload.get("evidence", {}),
            "readbacks": route_payload.get("readbacks", {}),
        }

    route_instruction_ref = str(route.get("node_instruction_ref") or route.get("instruction_ref") or "")
    binding_instruction_ref = str(binding.get("instruction_ref") or "")
    node_instruction_ref = route_instruction_ref or binding_instruction_ref
    if not node_instruction_ref:
        return _blocked("AGENT_NODE_INSTRUCTION_REF_MISSING", node_id=node_id)
    if route_instruction_ref and binding_instruction_ref and route_instruction_ref != binding_instruction_ref:
        return _blocked("AGENT_NODE_INSTRUCTION_BINDING_MISMATCH", node_id=node_id)

    try:
        bundle = resolve_agent_instruction_bundle(
            root=repo_root,
            instruction_refs=tuple(map(str, instruction_refs)),
            role_overlay_refs=tuple(map(str, role_overlay_refs)),
            required_skill_names=tuple(map(str, required_skill_names)),
            node_instruction_ref=node_instruction_ref,
        )
    except InstructionBundleError as exc:
        return _blocked(exc.reason_code, detail=exc.detail, node_id=node_id)

    event = build_live_runtime_event(
        canonical_state=canonical_state,
        event_id=event_id,
        run_id=run_id,
        gate=gate,
        requested_action=requested_action,
        scenario=scenario,
        input_payload=input_payload,
    )
    provider_request = _provider_request(
        canonical_state=canonical_state,
        run_id=run_id,
        event_id=event_id,
        route=route,
        binding=binding,
        capability_handlers=capability_handlers,
        authority=authority,
        validation_commands=tuple(map(str, input_payload.get("validation_commands", ()) or ())),
    )
    implementation_ref = str(binding.get("implementation_ref") or "")
    if not implementation_ref:
        return _blocked("AGENT_SEMANTIC_IMPLEMENTATION_REF_MISSING", node_id=node_id)

    extension_pack = None
    if extension_binding:
        try:
            extension_pack = build_node_instruction_pack(
                provider_request, head_sha=str(canonical_state.get("head_sha") or ""),
                gate=gate, requested_action=requested_action,
                node_id=str(binding.get("node_id") or ""), node_version=str(binding.get("node_version") or ""),
                implementation_ref=implementation_ref,
                profile_revision=str(canonical_state.get("profile_revision") or ""),
                node_registry_revision=str(canonical_state.get("node_registry_revision") or ""),
                provider_contract_revision=str(getattr(provider, "contract_revision", "agent-reasoning-v1")),
                instruction_bundle=bundle,
            )
        except Exception as exc:
            return _blocked("AGENT_NODE_INSTRUCTION_PACK_INVALID", node_id=node_id,
                            error=f"{type(exc).__name__}: {exc}")

    # Apply the provider live-closure gate (review finding #2): the Agent Host
    # must not silently run a provider that is not live-closure eligible. When a
    # configured provider_registry is supplied, an authoritative provider must
    # resolve from it; synthetic/direct-injection providers are rejected. When
    # no registry is configured (test/reasoner-only path), the gate is recorded
    # but not enforced, preserving the existing test-only provider path.
    provider_evidence_class, live_closure_eligible, _resolved = _resolve_provider_gate(
        provider, provider_registry
    )
    if mode == "authoritative" and provider_registry is None:
        return _blocked(
            "AGENT_PROVIDER_REGISTRY_REQUIRED",
            node_id=node_id,
            provider_evidence_class=provider_evidence_class,
            live_closure_eligible=False,
        )
    if provider_registry is not None and not live_closure_eligible:
        return _blocked(
            "AGENT_LIVE_CLOSURE_INELIGIBLE",
            node_id=node_id,
            provider_evidence_class=provider_evidence_class,
            live_closure_eligible=False,
        )

    provider_binding = None
    if provider_registry is not None:
        try:
            provider_binding = build_agent_provider_binding(
                node_id=node_id,
                evaluator_path=implementation_ref,
                request=provider_request,
                provider_name=str(getattr(provider, "name", "")),
                provider_registry=provider_registry,
                validation_runner=validation_runner,
                validation_root=validation_root,
                instruction_bundle=bundle,
            )
        except Exception as exc:
            return _blocked(
                "AGENT_PROVIDER_BRIDGE_BUILD_ERROR",
                node_id=node_id,
                error=f"{type(exc).__name__}: {exc}",
                provider_evidence_class=provider_evidence_class,
                live_closure_eligible=live_closure_eligible,
            )

    llm_handler = _provider_semantic_handler(
        provider=provider,
        provider_request=provider_request,
        bundle=bundle,
        canonical_state=canonical_state,
        gate=gate,
        requested_action=requested_action,
        route=route,
        binding=binding,
        input_payload=input_payload,
        capability_handlers=capability_handlers,
        provider_binding=provider_binding,
        workflow_root=repo_root,
    )
    semantic_handlers = {implementation_ref: llm_handler}
    extension_decision: dict[str, Any] = {}
    if extension_binding:
        from .universal_run_gate_adapter import handle_gate

        def extension_handler(current_binding: Mapping[str, Any], event_payload: Mapping[str, Any]) -> Mapping[str, Any]:
            payload = event_payload.get("input_payload") if isinstance(event_payload.get("input_payload"), Mapping) else {}
            decision = handle_gate(
                gate=str(payload.get("gate") or gate), action=str(payload.get("action") or requested_action),
                run_id=str(payload.get("run_id") or run_id),
                manifest=payload.get("manifest") if isinstance(payload.get("manifest"), Mapping) else {},
                target_contract=payload.get("target_contract") if isinstance(payload.get("target_contract"), Mapping) else {},
                authority=authority, internal_store=internal_receipt_store,
                receipts_persisted=receipts_persisted,
            )
            extension_decision.clear()
            extension_decision.update(decision)
            accepted = decision.get("status") in {"ROUTE_SELECTED", "ACCEPTED"}
            return {
                "outcome": "PASS" if accepted else "BLOCKED",
                "reason_code": str(decision.get("reason_code") or "UNIVERSAL_RUN_ROUTE_SELECTED"),
                "provider_result": dict(decision), "requested_effects": [], "proposed_effects": [],
                "executed_effects": [],
                "next_contract": current_binding["next_route_contract"]["pass" if accepted else "blocked"],
                "authority_granted": False, "implementation_invoked": True, "semantic_execution": True,
                "invocation_digest": _digest({"decision": decision, "binding": current_binding.get("binding_digest"),
                                              "instruction_pack": extension_pack.content_digest if extension_pack else None}),
            }

        semantic_handlers = {implementation_ref: extension_handler}

    runtime_state = state if isinstance(state, LiveRuntimeState) else LiveRuntimeState()
    effective_readback_handler = readback_handler if readback_handler is not None else verify_canonical_readback
    if extension_binding and readback_handler is None:
        def effective_readback_handler(current_binding: Mapping[str, Any], semantic: Mapping[str, Any],
                                       executed_effects: list[Mapping[str, Any]], event_payload: Mapping[str, Any]) -> Mapping[str, Any]:
            decision = semantic.get("provider_result") if isinstance(semantic.get("provider_result"), Mapping) else {}
            event_input = event_payload.get("input_payload") if isinstance(event_payload.get("input_payload"), Mapping) else {}
            contract = event_input.get("target_contract") if isinstance(event_input.get("target_contract"), Mapping) else {}
            if (decision.get("status") in {"ROUTE_SELECTED", "ACCEPTED"}
                    and contract.get("run_id") == event_payload.get("run_id")
                    and not executed_effects):
                return {"status": "VERIFIED", "digest": _digest({
                    "binding_digest": current_binding.get("binding_digest"), "run_id": event_payload.get("run_id"),
                    "gate": event_payload.get("gate"), "target_contract": contract,
                })}
            return {"status": "BLOCKED", "reason_code": str(decision.get("reason_code") or "UNIVERSAL_RUN_READBACK_INVALID")}
    result = dispatch_live_runtime_event(
        event=event,
        route_decision=route,
        implementation_registry=registry,
        mode=mode,
        semantic_handlers=semantic_handlers,
        capability_handlers=capability_handlers,
        readback_handler=effective_readback_handler,
        evidence_root=evidence_root,
        state=runtime_state,
        applicability_decision=applicability_decision,
        authority=authority,
        root=repo_root,
    )
    return {
        **dict(result),
        "agent_runtime_wired": True,
        "instruction_bundle_digest": bundle["bundle_digest"],
        "instruction_refs": list(bundle["instruction_refs"]),
        "role_overlay_refs": list(bundle["role_overlay_refs"]),
        "skill_refs": list(bundle["skill_refs"]),
        "node_instruction_ref": bundle["node_instruction_ref"],
        "provider": str(getattr(provider, "name", type(provider).__name__)),
        "provider_evidence_class": provider_evidence_class,
        "live_closure_eligible": live_closure_eligible,
        **({"g6_receipt": extension_decision.get("g6_receipt")} if extension_binding and gate == "UR.G6" else {}),
    }


def run_agent_runtime_loop(event_kwargs: Mapping[str, Any], *, max_iterations: int = 32) -> dict[str, Any]:
    """Drive a canonical Agent task from one entry node to its gate boundary.

    This is the missing production caller (review finding #1). It runs one
    ``run_agent_runtime_event`` and re-dispatches on the typed ``next_route``
    while the disposition is a real node hop (``continue`` + ``next_node``).
    It stops at a gate boundary (``stop`` + ``next_gate``), a terminal/blocked
    node, or the iteration cap — never silently auto-advancing a gate or
    granting later-gate authority.

    Each hop gets a distinct ``event_id`` (``<event_id>-<i>``) so the
    NodeEvidenceLedger records every runtime hop without replay conflict. The
    shared ``state`` (if any) carries fences/checkpoints across hops.
    """
    last: dict[str, Any] | None = None
    iterations = 0
    terminated = "iteration_limit"
    current_kwargs = dict(event_kwargs)
    if current_kwargs.get("state") is None:
        current_kwargs["state"] = LiveRuntimeState()

    for i in range(1, max(1, int(max_iterations)) + 1):
        run_kwargs = dict(current_kwargs)
        base_event_id = str(event_kwargs.get("event_id") or "agent-runtime-event")
        run_kwargs["event_id"] = f"{base_event_id}-{i}"
        last = run_agent_runtime_event(**run_kwargs)
        iterations = i
        status = str(last.get("status") or "")
        if status == "SEMANTIC_NODE_BLOCKED":
            terminated = "event_blocked"
            break
        if status == "SEMANTIC_NODE_NOT_APPLICABLE":
            terminated = "terminal"
            break
        next_route = last.get("next_route") or {}
        if not isinstance(next_route, Mapping):
            terminated = "terminal"
            break
        disposition = str(next_route.get("disposition") or "")
        if disposition == "stop":
            terminated = "gate_boundary" if next_route.get("next_gate") else "terminal"
            break
        if disposition == "continue" and next_route.get("next_node"):
            next_action = str(next_route.get("next_action") or "")
            if not next_action:
                terminated = "terminal"
                break
            # The canonical route profile is keyed by gate + requested_action.
            # Carry the typed handoff into the next resolution; never let the
            # provider select the next action or node.
            next_context = dict(current_kwargs.get("route_context") or {})
            next_context.update({
                "transition_kind": "continue",
                "previous_node": str(last.get("node_id") or ""),
                "previous_event_id": run_kwargs["event_id"],
                "next_node": str(next_route["next_node"]),
            })
            handoff = {
                "previous_node": str(last.get("node_id") or ""),
                "previous_event_id": run_kwargs["event_id"],
                "status": status,
                "reason_code": str(last.get("reason_code") or ""),
                "executed_effects": list(last.get("executed_effects", []) or []),
                "readback": dict(last.get("readback") or {}),
                "evidence_summary": dict(last.get("evidence_summary") or {}),
            }
            next_payload = dict(current_kwargs.get("input_payload") or {})
            next_payload.setdefault("previous_node_result", handoff)
            next_registry = current_kwargs.get("implementation_registry")
            next_binding = None
            if isinstance(next_registry, Mapping):
                next_binding = _binding_for(next_registry, str(next_route["next_node"]))
            if next_binding is not None:
                for field in next_binding.get("entry_contract", []) or []:
                    next_payload.setdefault(str(field), handoff)
            current_kwargs["requested_action"] = next_action
            current_kwargs["route_context"] = next_context
            current_kwargs["input_payload"] = next_payload
            continue
        terminated = "terminal"
        break
    return {
        **dict(last or {}),
        "iterations": iterations,
        "loop_terminated": terminated,
    }


__all__ = ["run_agent_runtime_event", "run_agent_runtime_loop"]
