"""Validate static compatibility between a Flow Profile and generic Policy registry.

The validator is side-effect free. Workflow owns composition; Policy owns
constraints. This module only proves that the two contracts can be activated
together and that their exact revision/digest bindings are current.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from tools.node_architect.validate_flow_profile_workflow import CANONICAL_GATES, compile_workflow_projection

_STRENGTH = {"NOT_APPLICABLE": 0, "REQUIRED": 1, "BLOCKED": 2}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _declared_types(policy: Mapping[str, Any], field: str, key: str) -> set[str]:
    return {str(item.get(key) or "") for item in _mappings(policy.get(field)) if item.get(key)}


def validate_flow_policy_compatibility(*, flow_profile: Mapping[str, Any], policy_registry: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        workflow = {}
        reasons.append("WORKFLOW_CONTRACT_MISSING")

    expected_registry = str(flow_profile.get("policy_registry_ref") or "")
    actual_registry = str(policy_registry.get("registry_id") or "")
    registry_digest = _digest(policy_registry)
    if not expected_registry or expected_registry != actual_registry:
        reasons.append("POLICY_REGISTRY_BINDING_MISMATCH")

    policy_bindings = [item for item in _mappings(flow_profile.get("registry_bindings")) if item.get("registry") == "policy"]
    if len(policy_bindings) != 1:
        reasons.append("POLICY_REGISTRY_EXACT_BINDING_MISSING")
    else:
        binding = policy_bindings[0]
        if str(binding.get("registry_id") or "") != actual_registry:
            reasons.append("POLICY_REGISTRY_ID_DRIFT")
        if str(binding.get("revision") or "") != str(policy_registry.get("revision") or ""):
            reasons.append("POLICY_REGISTRY_REVISION_DRIFT")
        if str(binding.get("schema_version") or "") != str(policy_registry.get("schema_version") or ""):
            reasons.append("POLICY_REGISTRY_SCHEMA_DRIFT")
        if str(binding.get("digest") or "") != registry_digest:
            reasons.append("POLICY_REGISTRY_DIGEST_DRIFT")

    policies = _mappings(policy_registry.get("policies"))
    policy_ids = [str(item.get("id") or "") for item in policies]
    if any(not item for item in policy_ids) or len(policy_ids) != len(set(policy_ids)):
        reasons.append("POLICY_IDENTITY_INVALID")
    policy_map = {str(item.get("id")): item for item in policies if item.get("id")}

    bindings = _mappings(workflow.get("gate_bindings"))
    gates = [str(item.get("gate") or "") for item in bindings]
    if len(gates) != len(set(gates)):
        reasons.append("GATE_BINDING_AMBIGUOUS")
    if set(gates) != set(CANONICAL_GATES):
        reasons.append("GATE_BINDING_INCOMPLETE")
    if any(gate not in CANONICAL_GATES for gate in gates):
        reasons.append("NON_CANONICAL_GATE")

    gate_policy: dict[str, Mapping[str, Any]] = {}
    for binding in bindings:
        gate = str(binding.get("gate") or "")
        policy_ref = str(binding.get("policy_ref") or "")
        if not policy_ref or policy_ref not in policy_map:
            reasons.append("GATE_POLICY_MISSING")
            continue
        gate_policy[gate] = policy_map[policy_ref]

    if policy_registry.get("tighten_only") is not True:
        reasons.append("POLICY_TIGHTEN_ONLY_REQUIRED")
    minimums = policy_registry.get("canonical_minimums")
    if not isinstance(minimums, Mapping) or set(minimums) != set(CANONICAL_GATES):
        reasons.append("CANONICAL_MINIMUMS_INCOMPLETE")
        minimums = {}

    for gate in CANONICAL_GATES:
        policy = gate_policy.get(gate)
        minimum = minimums.get(gate) if isinstance(minimums, Mapping) else None
        if not isinstance(policy, Mapping) or not isinstance(minimum, Mapping):
            continue
        default = str(policy.get("default") or "")
        min_decision = str(minimum.get("min_decision") or "")
        if default not in _STRENGTH or min_decision not in _STRENGTH:
            reasons.append("POLICY_DECISION_STRENGTH_INVALID")
        elif _STRENGTH[default] < _STRENGTH[min_decision]:
            reasons.append("POLICY_WEAKENS_CANONICAL_MINIMUM")
        required_authority = {str(item) for item in minimum.get("required_authority_types", [])}
        if required_authority - _declared_types(policy, "authority_requirements", "authority_type"):
            reasons.append("POLICY_WEAKENS_CANONICAL_AUTHORITY")
        required_evidence = {str(item) for item in minimum.get("required_evidence_types", [])}
        if required_evidence - _declared_types(policy, "evidence_requirements", "evidence_type"):
            reasons.append("POLICY_WEAKENS_CANONICAL_EVIDENCE")
        prohibited = {str(item) for item in minimum.get("prohibited_actions", [])}
        if prohibited - _declared_types(policy, "prohibited_actions", "action"):
            reasons.append("POLICY_WEAKENS_CANONICAL_PROHIBITIONS")

    compiled_expected = None
    try:
        compiled_expected = compile_workflow_projection(dict(flow_profile))["workflow_digest"]
    except Exception:
        reasons.append("WORKFLOW_COMPILE_FAILED")
    compiled_declared = flow_profile.get("compiled", {}).get("workflow_digest") if isinstance(flow_profile.get("compiled"), Mapping) else None
    if not compiled_declared:
        reasons.append("WORKFLOW_COMPILED_DIGEST_MISSING")
    elif compiled_expected and compiled_declared != compiled_expected:
        reasons.append("WORKFLOW_COMPILED_DIGEST_DRIFT")

    unique = list(dict.fromkeys(reasons))
    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_type": "flow-policy-compatibility-decision",
        "flow_profile_id": str(flow_profile.get("id") or "unbound"),
        "flow_profile_version": str(flow_profile.get("version") or "unbound"),
        "flow_profile_digest": _digest(flow_profile),
        "workflow_digest": str(compiled_declared or compiled_expected or "unbound"),
        "policy_registry_id": actual_registry or "unbound",
        "policy_registry_revision": str(policy_registry.get("revision") or "unbound"),
        "policy_registry_digest": registry_digest,
        "compatible": not unique,
        "reason_codes": unique or ["FLOW_POLICY_COMPATIBLE"],
    }
    artifact["decision_digest"] = _digest(artifact)
    return artifact


__all__ = ["validate_flow_policy_compatibility"]
