"""Compile a deterministic runtime decision from Workflow + Policy evidence."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from tools.node_architect.validate_flow_policy_compatibility import (
    CANONICAL_GATES,
    validate_flow_policy_compatibility,
)

APPLICABILITY = {"REQUIRED", "NOT_APPLICABLE", "BLOCKED"}
OUTCOMES = {"CONTINUE", "TERMINAL", "BLOCKED", "HUMAN_REQUIRED"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _workflow_digest(flow_profile: Mapping[str, Any]) -> str:
    return _digest(flow_profile)


def _policy_digest(policy_registry: Mapping[str, Any]) -> str:
    return _digest(policy_registry)


def _gate_policy_ref(flow_profile: Mapping[str, Any], gate: str) -> str | None:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return None
    matches = [
        item for item in workflow.get("gate_bindings", [])
        if isinstance(item, Mapping) and item.get("gate") == gate
    ]
    if len(matches) != 1:
        return None
    value = matches[0].get("policy_ref")
    return str(value) if value else None


def _known_nodes(flow_profile: Mapping[str, Any]) -> set[str]:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return set()
    nodes: set[str] = set(str(item) for item in workflow.get("entry_nodes", []) if item)
    for terminal in workflow.get("terminal_nodes", []):
        if isinstance(terminal, Mapping) and terminal.get("node"):
            nodes.add(str(terminal["node"]))
    for edge in workflow.get("edges", []):
        if isinstance(edge, Mapping):
            if edge.get("source"):
                nodes.add(str(edge["source"]))
            if edge.get("target"):
                nodes.add(str(edge["target"]))
    return nodes


def _terminal_nodes(flow_profile: Mapping[str, Any]) -> set[str]:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return set()
    return {
        str(item.get("node"))
        for item in workflow.get("terminal_nodes", [])
        if isinstance(item, Mapping) and item.get("node")
    }


def compile_flow_policy_decision(
    *,
    flow_profile: Mapping[str, Any],
    policy_registry: Mapping[str, Any],
    current_node: str,
    current_gate: str,
    applicability_decision: Mapping[str, Any],
    context: Mapping[str, Any],
    next_nodes: Sequence[str] | None = None,
    terminal_disposition: str | None = None,
    authority_requirement: Mapping[str, Any] | None = None,
    evidence_requirements: Sequence[str] | None = None,
    evidence_results: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile a pure decision artifact; never execute or mutate runtime state."""
    compatibility = validate_flow_policy_compatibility(
        flow_profile=flow_profile, policy_registry=policy_registry
    )
    reasons: list[str] = []
    applicability = str(applicability_decision.get("decision") or "BLOCKED")

    if not compatibility.get("compatible"):
        applicability = "BLOCKED"
        reasons.extend(str(item) for item in compatibility.get("reason_codes", []))
    if current_gate not in CANONICAL_GATES:
        applicability = "BLOCKED"
        reasons.append("NON_CANONICAL_GATE")
    known_nodes = _known_nodes(flow_profile)
    if current_node not in known_nodes:
        applicability = "BLOCKED"
        reasons.append("CURRENT_NODE_NOT_IN_WORKFLOW")
    if applicability not in APPLICABILITY:
        applicability = "BLOCKED"
        reasons.append("APPLICABILITY_INVALID")

    expected_policy_ref = _gate_policy_ref(flow_profile, current_gate)
    actual_policy_ref = applicability_decision.get("policy_ref")
    if expected_policy_ref != actual_policy_ref:
        applicability = "BLOCKED"
        reasons.append("POLICY_REF_MISMATCH")

    candidate_next = list(dict.fromkeys(str(item) for item in (next_nodes or []) if item))
    invalid_next = sorted(set(candidate_next) - known_nodes)
    if invalid_next:
        applicability = "BLOCKED"
        reasons.append("NEXT_NODE_NOT_IN_WORKFLOW")

    terminal_nodes = _terminal_nodes(flow_profile)
    if terminal_disposition and current_node not in terminal_nodes:
        applicability = "BLOCKED"
        reasons.append("TERMINAL_DISPOSITION_FROM_NON_TERMINAL_NODE")

    if applicability == "BLOCKED":
        outcome = "BLOCKED"
        candidate_next = []
        terminal_disposition = None
    elif terminal_disposition:
        outcome = "TERMINAL"
        candidate_next = []
    elif candidate_next:
        outcome = "CONTINUE"
    elif applicability == "NOT_APPLICABLE":
        outcome = "TERMINAL"
        terminal_disposition = "GATE_NOT_APPLICABLE"
    else:
        outcome = "BLOCKED"
        reasons.append("NEXT_DISPOSITION_MISSING")

    if outcome not in OUTCOMES:
        outcome = "BLOCKED"
        reasons.append("OUTCOME_INVALID")

    if not reasons:
        reason = applicability_decision.get("reason_code")
        reasons.append(str(reason or "FLOW_POLICY_DECISION_COMPILED"))

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_type": "workflow-policy-runtime-decision",
        "workflow": {
            "id": str(flow_profile.get("id") or "unbound"),
            "version": str(flow_profile.get("version") or flow_profile.get("schema_version") or "unbound"),
            "digest": _workflow_digest(flow_profile),
        },
        "policy": {
            "registry_id": str(policy_registry.get("registry_id") or "unbound"),
            "revision": str(policy_registry.get("revision") or "unbound"),
            "digest": _policy_digest(policy_registry),
            "policy_ref": expected_policy_ref,
        },
        "current_node": current_node,
        "current_gate": current_gate,
        "applicability": applicability,
        "outcome": outcome,
        "next_nodes": candidate_next,
        "terminal_disposition": terminal_disposition,
        "authority_requirement": dict(authority_requirement) if authority_requirement else None,
        "evidence_requirements": list(dict.fromkeys(str(item) for item in (evidence_requirements or []) if item)),
        "evidence_results": [dict(item) for item in (evidence_results or [])],
        "reason_codes": list(dict.fromkeys(reasons)),
        "context_digest": _digest(context),
    }
    artifact["decision_digest"] = _digest(artifact)
    return artifact


__all__ = ["compile_flow_policy_decision"]
