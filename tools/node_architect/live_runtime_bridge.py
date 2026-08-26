#!/usr/bin/env python3
"""Live authoritative Agent/gate event bridge into Node Architect semantic runtime."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .semantic_agent_runtime import RuntimeExecutionState, execute_semantic_node_lifecycle, resume_checkpoint

GATES = (
    "G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR",
    "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA",
)
CANONICAL_SOURCE_KIND = "canonical_agent_gate_state"


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class LiveRuntimeState:
    execution: RuntimeExecutionState = field(default_factory=RuntimeExecutionState)
    event_digests: dict[str, str] = field(default_factory=dict)
    event_results: dict[str, dict[str, Any]] = field(default_factory=dict)


def build_live_runtime_event(
    *,
    canonical_state: Mapping[str, Any],
    event_id: str,
    run_id: str,
    gate: str,
    requested_action: str,
    scenario: str,
    input_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if gate not in GATES:
        raise ValueError("unsupported gate")
    head = str(canonical_state.get("head_sha") or "")
    event = {
        "schema_version": "1.0",
        "artifact_type": "live-agent-runtime-event",
        "event_id": event_id,
        "task_id": str(canonical_state.get("task_id") or ""),
        "run_id": run_id,
        "repository": str(canonical_state.get("repository") or ""),
        "branch": str(canonical_state.get("branch") or ""),
        "base_sha": str(canonical_state.get("base_sha") or ""),
        "head_sha": head,
        "exact_revision": head,
        "scope_hash": str(canonical_state.get("scope_hash") or ""),
        "gate": gate,
        "requested_action": requested_action,
        "scenario": scenario,
        "profile_revision": str(canonical_state.get("profile_revision") or ""),
        "graph_revision": str(canonical_state.get("graph_revision") or ""),
        "node_registry_revision": str(canonical_state.get("node_registry_revision") or ""),
        "policy_revision": str(canonical_state.get("policy_revision") or ""),
        "source_kind": str(canonical_state.get("source_kind") or ""),
        "input_payload": dict(input_payload),
        "idempotency_key": f"live-runtime:{event_id}",
        "occurred_at": str(canonical_state.get("occurred_at") or _now()),
        "live_agent_event": True,
        "synthetic": False,
    }
    event["event_digest"] = _digest({k: v for k, v in event.items() if k != "event_digest"})
    return event


def _binding_for(implementation_registry: Mapping[str, Any], node_id: str) -> Mapping[str, Any] | None:
    matches = [
        item for item in implementation_registry.get("bindings", [])
        if isinstance(item, Mapping) and item.get("node_id") == node_id
    ]
    return matches[0] if len(matches) == 1 else None


def _event_replay(state: LiveRuntimeState, event: Mapping[str, Any]) -> dict[str, Any] | None:
    event_id = str(event.get("event_id") or "")
    digest = _digest({k: v for k, v in event.items() if k != "event_digest"})
    prior = state.event_digests.get(event_id)
    if prior is None:
        state.event_digests[event_id] = digest
        return None
    if prior != digest:
        return {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "LIVE_RUNTIME_REPLAY_CONFLICT", "authority_granted": False, "executed_effects": []}
    return state.event_results.get(event_id)


def dispatch_live_runtime_event(
    *,
    event: Mapping[str, Any],
    route_decision: Mapping[str, Any],
    implementation_registry: Mapping[str, Any],
    mode: str,
    semantic_handlers: Mapping[str, Any],
    capability_handlers: Mapping[str, Any],
    readback_handler: Any,
    evidence_root: Path | str,
    state: LiveRuntimeState,
    applicability_decision: Mapping[str, Any] | None = None,
    authority: Mapping[str, Any] | None = None,
    root: Path | str = Path("."),
) -> dict[str, Any]:
    if event.get("live_agent_event") is not True or event.get("synthetic") is True:
        return {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "SYNTHETIC_EVENT_NOT_LIVE_RUNTIME", "authority_granted": False, "executed_effects": []}
    if event.get("source_kind") != CANONICAL_SOURCE_KIND:
        return {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "PROJECTION_EVENT_NOT_CANONICAL_RUNTIME", "authority_granted": False, "executed_effects": []}
    if event.get("gate") not in GATES:
        return {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "LIVE_GATE_INVALID", "authority_granted": False, "executed_effects": []}

    replay = _event_replay(state, event)
    if replay is not None:
        return dict(replay)

    applicability = applicability_decision or {
        "decision": "REQUIRED",
        "policy_ref": event.get("policy_revision"),
        "decision_digest": _digest({"gate": event.get("gate"), "decision": "REQUIRED", "policy": event.get("policy_revision")}),
    }
    decision = applicability.get("decision")
    if decision == "NOT_APPLICABLE":
        result = {
            "status": "LIVE_GATE_NOT_APPLICABLE", "reason_code": "LIVE_GATE_NOT_APPLICABLE",
            "gate": event.get("gate"), "applicability": dict(applicability),
            "authority_granted": False, "executed_effects": [], "automatic_gate_advance": False,
        }
        state.event_results[str(event["event_id"])] = result
        return dict(result)
    if decision == "BLOCKED":
        result = {
            "status": "LIVE_GATE_BLOCKED", "reason_code": "LIVE_GATE_BLOCKED",
            "gate": event.get("gate"), "applicability": dict(applicability),
            "authority_granted": False, "executed_effects": [], "automatic_gate_advance": False,
        }
        state.event_results[str(event["event_id"])] = result
        return dict(result)
    if decision != "REQUIRED" or not applicability.get("decision_digest"):
        result = {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "GATE_APPLICABILITY_EVIDENCE_INVALID", "authority_granted": False, "executed_effects": []}
        state.event_results[str(event["event_id"])] = result
        return dict(result)

    if route_decision.get("outcome") != "ROUTE_SELECTED":
        result = {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "CANONICAL_ROUTE_NOT_SELECTED", "authority_granted": False, "executed_effects": []}
        state.event_results[str(event["event_id"])] = result
        return dict(result)
    if any(route_decision.get(field) is True for field in (
        "authority_granted", "write_authority_granted", "pr_authority_granted",
        "merge_authority_granted", "deployment_authority_granted", "production_authority_granted",
    )):
        result = {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "ROUTE_AUTHORITY_ESCALATION_REJECTED", "authority_granted": False, "executed_effects": []}
        state.event_results[str(event["event_id"])] = result
        return dict(result)
    if route_decision.get("profile_revision") not in (None, "", event.get("profile_revision")):
        result = {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "LIVE_ROUTE_PROFILE_DRIFT", "authority_granted": False, "executed_effects": []}
        state.event_results[str(event["event_id"])] = result
        return dict(result)
    if route_decision.get("graph_revision") not in (None, "", event.get("graph_revision")):
        result = {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "LIVE_ROUTE_GRAPH_DRIFT", "authority_granted": False, "executed_effects": []}
        state.event_results[str(event["event_id"])] = result
        return dict(result)

    node_id = str(route_decision.get("current_node") or "")
    binding = _binding_for(implementation_registry, node_id)
    if binding is None:
        result = {"status": "LIVE_RUNTIME_EVENT_REJECTED", "reason_code": "LIVE_SEMANTIC_BINDING_MISSING_OR_AMBIGUOUS", "authority_granted": False, "executed_effects": []}
        state.event_results[str(event["event_id"])] = result
        return dict(result)

    result = execute_semantic_node_lifecycle(
        event=event, binding=binding, mode=mode, authority=authority,
        semantic_handlers=semantic_handlers, capability_handlers=capability_handlers,
        readback_handler=readback_handler, evidence_root=evidence_root, state=state.execution, root=root,
    )
    result = {
        **result,
        "live_agent_event": True,
        "synthetic": False,
        "source_kind": CANONICAL_SOURCE_KIND,
        "applicability": dict(applicability),
        "route_decision_digest": route_decision.get("decision_digest"),
    }
    state.event_results[str(event["event_id"])] = dict(result)
    return result


def resume_live_runtime_event(
    *,
    checkpoint: Mapping[str, Any],
    event: Mapping[str, Any],
    route_decision: Mapping[str, Any],
    implementation_registry: Mapping[str, Any],
    mode: str,
    semantic_handlers: Mapping[str, Any],
    capability_handlers: Mapping[str, Any],
    readback_handler: Any,
    evidence_root: Path | str,
    state: LiveRuntimeState,
    applicability_decision: Mapping[str, Any] | None = None,
    authority: Mapping[str, Any] | None = None,
    root: Path | str = Path("."),
) -> dict[str, Any]:
    node_id = str(checkpoint.get("node_id") or route_decision.get("current_node") or "")
    binding = _binding_for(implementation_registry, node_id)
    if binding is None:
        return {"status": "RESUME_BLOCKED", "reason_code": "CHECKPOINT_BINDING_MISSING"}
    resume = resume_checkpoint(checkpoint, event=event, binding=binding)
    if resume.get("status") != "RESUME_ALLOWED":
        return resume
    return dispatch_live_runtime_event(
        event=event, route_decision=route_decision, implementation_registry=implementation_registry,
        mode=mode, semantic_handlers=semantic_handlers, capability_handlers=capability_handlers,
        readback_handler=readback_handler, evidence_root=evidence_root, state=state,
        applicability_decision=applicability_decision, authority=authority, root=root,
    )


__all__ = ["GATES", "LiveRuntimeState", "build_live_runtime_event", "dispatch_live_runtime_event", "resume_live_runtime_event"]
