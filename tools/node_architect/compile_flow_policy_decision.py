"""Compile deterministic runtime decisions from Workflow + Policy evidence.

The compiler is pure and side-effect free. It never grants authority and never
stores mutable execution state. Workflow controls composition; Policy controls
applicability/constraints; this module joins their already-declared facts into
one replay-stable machine decision.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from tools.node_architect.validate_flow_policy_compatibility import (
    validate_flow_policy_compatibility,
)
from tools.node_architect.validate_flow_profile_workflow import CANONICAL_GATES

APPLICABILITY = {"REQUIRED", "NOT_APPLICABLE", "BLOCKED"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _workflow_digest(flow_profile: Mapping[str, Any]) -> str:
    compiled = flow_profile.get("compiled")
    if isinstance(compiled, Mapping):
        value = compiled.get("workflow_digest")
        if isinstance(value, str) and value.startswith("sha256:"):
            return value
    return _digest(flow_profile)


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


def _policy(policy_registry: Mapping[str, Any], policy_ref: str | None) -> Mapping[str, Any] | None:
    matches = [
        item for item in policy_registry.get("policies", [])
        if isinstance(item, Mapping) and item.get("id") == policy_ref
    ]
    return matches[0] if len(matches) == 1 else None


def _known_nodes(flow_profile: Mapping[str, Any]) -> set[str]:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return set()
    nodes = {
        str(item.get("participant"))
        for item in workflow.get("participants", [])
        if isinstance(item, Mapping) and item.get("participant_kind") == "node" and item.get("participant")
    }
    for item in workflow.get("entry_nodes", []):
        if item:
            nodes.add(str(item))
    for terminal in workflow.get("terminal_nodes", []):
        if isinstance(terminal, Mapping) and terminal.get("node"):
            nodes.add(str(terminal["node"]))
    return nodes


def _terminal_outcome(flow_profile: Mapping[str, Any], node: str) -> str | None:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return None
    matches = [
        item for item in workflow.get("terminal_nodes", [])
        if isinstance(item, Mapping) and item.get("node") == node
    ]
    if len(matches) != 1:
        return None
    outcome = matches[0].get("outcome")
    return str(outcome) if outcome else None


def _unsatisfied(items: Any) -> list[Mapping[str, Any]]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping) and item.get("satisfied") is False]


def compile_flow_policy_decision(
    *,
    flow_profile: Mapping[str, Any],
    policy_registry: Mapping[str, Any],
    current_node: str,
    current_gate: str,
    applicability_decision: Mapping[str, Any],
    context: Mapping[str, Any],
    next_nodes: Sequence[str] | None = None,
    next_gate: str | None = None,
    terminal_disposition: str | None = None,
) -> dict[str, Any]:
    """Compile one replay-stable runtime decision without executing effects."""
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
    if next_gate is not None and next_gate not in CANONICAL_GATES:
        applicability = "BLOCKED"
        reasons.append("NEXT_GATE_NOT_CANONICAL")
    if applicability not in APPLICABILITY:
        applicability = "BLOCKED"
        reasons.append("APPLICABILITY_INVALID")

    known_nodes = _known_nodes(flow_profile)
    if current_node not in known_nodes:
        applicability = "BLOCKED"
        reasons.append("CURRENT_NODE_NOT_IN_WORKFLOW")
    candidate_next = list(dict.fromkeys(str(item) for item in (next_nodes or []) if item))
    if set(candidate_next) - known_nodes:
        applicability = "BLOCKED"
        reasons.append("NEXT_NODE_NOT_IN_WORKFLOW")

    expected_policy_ref = _gate_policy_ref(flow_profile, current_gate)
    actual_policy_ref = str(applicability_decision.get("policy_ref") or "") or None
    selected_policy = _policy(policy_registry, expected_policy_ref)
    if expected_policy_ref is None or selected_policy is None:
        applicability = "BLOCKED"
        reasons.append("GATE_POLICY_MISSING")
    if expected_policy_ref != actual_policy_ref:
        applicability = "BLOCKED"
        reasons.append("POLICY_REF_MISMATCH")

    policy_registry_digest = _digest(policy_registry)
    decision_registry_digest = applicability_decision.get("policy_registry_digest")
    decision_policy_digest = applicability_decision.get("policy_digest")
    decision_policy_version = applicability_decision.get("policy_version")
    selected_policy_digest = _digest(selected_policy) if selected_policy is not None else None
    if not isinstance(decision_registry_digest, str) or not isinstance(decision_policy_digest, str):
        applicability = "BLOCKED"
        reasons.append("POLICY_DECISION_PROVENANCE_MISSING")
    else:
        if decision_registry_digest != policy_registry_digest:
            applicability = "BLOCKED"
            reasons.append("POLICY_REGISTRY_DIGEST_MISMATCH")
        if selected_policy_digest and decision_policy_digest != selected_policy_digest:
            applicability = "BLOCKED"
            reasons.append("POLICY_DIGEST_MISMATCH")
    if selected_policy is not None and str(selected_policy.get("version") or "") != str(decision_policy_version or ""):
        applicability = "BLOCKED"
        reasons.append("POLICY_VERSION_MISMATCH")

    authority = [dict(item) for item in applicability_decision.get("authority_requirements", []) if isinstance(item, Mapping)]
    evidence = [dict(item) for item in applicability_decision.get("evidence_requirements", []) if isinstance(item, Mapping)]
    prohibited = sorted({str(item) for item in applicability_decision.get("prohibited_actions", []) if item})
    terminal_acceptance = applicability_decision.get("terminal_acceptance")
    terminal_acceptance = dict(terminal_acceptance) if isinstance(terminal_acceptance, Mapping) else None

    requested_action = context.get("requested_action")
    if requested_action is not None and str(requested_action) in prohibited:
        applicability = "BLOCKED"
        reasons.append("POLICY_PROHIBITED_ACTION")
    if applicability == "REQUIRED" and _unsatisfied(authority):
        applicability = "BLOCKED"
        reasons.append("AUTHORITY_REQUIREMENTS_UNSATISFIED")
    if applicability == "REQUIRED" and _unsatisfied(evidence):
        applicability = "BLOCKED"
        reasons.append("EVIDENCE_REQUIREMENTS_UNSATISFIED")

    declared_terminal = _terminal_outcome(flow_profile, current_node)
    effective_terminal = terminal_disposition or declared_terminal
    if effective_terminal and terminal_acceptance is not None and terminal_acceptance.get("accepted") is False:
        applicability = "BLOCKED"
        reasons.append("TERMINAL_ACCEPTANCE_UNMET")

    effective_next_gate = next_gate
    if applicability == "NOT_APPLICABLE":
        # The evaluated gate is skipped explicitly; continue only through an
        # already-declared Workflow edge. Never reinterpret N/A as PASS.
        effective_next_gate = None

    if applicability == "BLOCKED":
        outcome = "BLOCKED"
        candidate_next = []
        effective_next_gate = None
        effective_terminal = None
    elif effective_terminal == "HUMAN_REQUIRED":
        outcome = "HUMAN_REQUIRED"
        candidate_next = []
        effective_next_gate = None
    elif effective_terminal:
        outcome = "TERMINAL"
        candidate_next = []
        effective_next_gate = None
    elif candidate_next or effective_next_gate:
        outcome = "CONTINUE"
    elif applicability == "NOT_APPLICABLE":
        outcome = "TERMINAL"
        effective_terminal = "GATE_NOT_APPLICABLE"
    else:
        outcome = "BLOCKED"
        reasons.append("NEXT_DISPOSITION_MISSING")

    if not reasons:
        reasons.append(str(applicability_decision.get("reason_code") or "FLOW_POLICY_DECISION_COMPILED"))

    applicability_digest = applicability_decision.get("decision_digest")
    if not isinstance(applicability_digest, str) or not applicability_digest.startswith("sha256:"):
        reasons.append("APPLICABILITY_DECISION_DIGEST_MISSING")
        applicability_digest = _digest(applicability_decision)
        outcome = "BLOCKED"
        applicability = "BLOCKED"
        candidate_next = []
        effective_next_gate = None
        effective_terminal = None

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_type": "workflow-policy-runtime-decision",
        "workflow": {
            "id": str(flow_profile.get("id") or "unbound"),
            "version": str(flow_profile.get("version") or "unbound"),
            "digest": _workflow_digest(flow_profile),
            "profile_digest": _digest(flow_profile),
        },
        "policy": {
            "registry_id": str(policy_registry.get("registry_id") or "unbound"),
            "revision": str(policy_registry.get("revision") or "unbound"),
            "registry_digest": policy_registry_digest,
            "policy_ref": str(expected_policy_ref or "unbound"),
            "policy_version": str(decision_policy_version or "unbound"),
            "policy_digest": str(decision_policy_digest or selected_policy_digest or _digest({})),
        },
        "current_node": current_node,
        "current_gate": current_gate,
        "applicability": applicability,
        "outcome": outcome,
        "next_nodes": candidate_next,
        "next_gate": effective_next_gate,
        "terminal_disposition": effective_terminal,
        "authority_requirements": authority,
        "evidence_requirements": evidence,
        "prohibited_actions": prohibited,
        "terminal_acceptance": terminal_acceptance,
        "reason_codes": list(dict.fromkeys(reasons)),
        "context_digest": _digest(context),
        "compatibility_digest": str(compatibility["decision_digest"]),
        "applicability_decision_digest": applicability_digest,
    }
    artifact["decision_digest"] = _digest(artifact)
    return artifact


__all__ = ["compile_flow_policy_decision"]
