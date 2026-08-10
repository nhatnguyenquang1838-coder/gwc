"""Evaluate gate applicability from a workflow-bound policy registry.

The evaluator is pure and controller-agnostic. Workflow composition only binds
``gate -> policy_ref``; applicability rules live in a separate policy registry.
The result is a deterministic, digest-bound decision artifact.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

DECISIONS = {"REQUIRED", "NOT_APPLICABLE", "BLOCKED"}
OPERATORS = {"equals", "in", "exists", "truthy"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _read_path(context: Mapping[str, Any], dotted_path: str) -> tuple[bool, Any]:
    current: Any = context
    for segment in dotted_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def _condition_matches(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    field = condition.get("field")
    operator = condition.get("operator")
    if not isinstance(field, str) or not field or operator not in OPERATORS:
        return False

    exists, actual = _read_path(context, field)
    if operator == "exists":
        expected = condition.get("value", True)
        return exists == bool(expected)
    if not exists:
        return False
    if operator == "truthy":
        return bool(actual)
    if operator == "equals":
        return actual == condition.get("value")

    values = condition.get("values")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return False
    if isinstance(actual, Sequence) and not isinstance(actual, (str, bytes)):
        return any(item in values for item in actual)
    return actual in values


def _first_match(conditions: Any, context: Mapping[str, Any]) -> str | None:
    if not isinstance(conditions, list):
        return None
    for index, condition in enumerate(conditions):
        if isinstance(condition, Mapping) and _condition_matches(condition, context):
            return str(condition.get("id") or f"rule-{index + 1}")
    return None


def _decision(*, flow_profile_id: str, policy_registry_ref: str, gate: str,
              policy_ref: str | None, decision: str, reason_code: str,
              context: Mapping[str, Any], matched_rule: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "gate-applicability-decision",
        "flow_profile_id": flow_profile_id or "unbound",
        "policy_registry_ref": policy_registry_ref or "unbound",
        "gate": gate,
        "policy_ref": policy_ref,
        "decision": decision,
        "reason_code": reason_code,
        "matched_rule": matched_rule,
        "context_digest": _sha256(context),
    }
    payload["decision_digest"] = _sha256(payload)
    return payload


def evaluate_gate_applicability(*, flow_profile: Mapping[str, Any],
                                policy_registry: Mapping[str, Any], gate: str,
                                context: Mapping[str, Any]) -> dict[str, Any]:
    """Return REQUIRED, NOT_APPLICABLE or BLOCKED for one canonical gate.

    Precedence is deterministic and fail-closed: BLOCKED rules win over
    REQUIRED rules, which win over explicit NOT_APPLICABLE rules; otherwise
    the policy default applies. Missing/ambiguous bindings or policies block.
    """
    flow_profile_id = str(flow_profile.get("id") or "unbound")
    expected_registry = str(flow_profile.get("policy_registry_ref") or "")
    actual_registry = str(policy_registry.get("registry_id") or "")
    registry_ref = expected_registry or actual_registry or "unbound"

    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=None, decision="BLOCKED",
            reason_code="WORKFLOW_CONTRACT_MISSING", context=context,
        )
    if not expected_registry or expected_registry != actual_registry:
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=None, decision="BLOCKED",
            reason_code="POLICY_REGISTRY_BINDING_MISMATCH", context=context,
        )

    bindings = [
        item for item in workflow.get("gate_bindings", [])
        if isinstance(item, Mapping) and item.get("gate") == gate
    ]
    if len(bindings) != 1:
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=None, decision="BLOCKED",
            reason_code="GATE_BINDING_MISSING" if not bindings else "GATE_BINDING_AMBIGUOUS",
            context=context,
        )

    policy_ref = str(bindings[0].get("policy_ref") or "") or None
    policies = [
        item for item in policy_registry.get("policies", [])
        if isinstance(item, Mapping) and item.get("id") == policy_ref
    ]
    if len(policies) != 1:
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=policy_ref, decision="BLOCKED",
            reason_code="GATE_POLICY_MISSING" if not policies else "GATE_POLICY_AMBIGUOUS",
            context=context,
        )

    policy = policies[0]
    blocked = _first_match(policy.get("blocked_when"), context)
    if blocked:
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=policy_ref, decision="BLOCKED",
            reason_code="GATE_POLICY_BLOCKED", matched_rule=blocked, context=context,
        )
    required = _first_match(policy.get("required_when"), context)
    if required:
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=policy_ref, decision="REQUIRED",
            reason_code="GATE_REQUIRED_BY_POLICY", matched_rule=required, context=context,
        )
    not_applicable = _first_match(policy.get("not_applicable_when"), context)
    if not_applicable:
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=policy_ref, decision="NOT_APPLICABLE",
            reason_code="GATE_NOT_APPLICABLE_BY_POLICY", matched_rule=not_applicable,
            context=context,
        )

    default = policy.get("default")
    if default not in DECISIONS:
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=policy_ref, decision="BLOCKED",
            reason_code="GATE_POLICY_INVALID", context=context,
        )
    reason = {
        "REQUIRED": "GATE_REQUIRED_BY_DEFAULT",
        "NOT_APPLICABLE": "GATE_NOT_APPLICABLE_BY_DEFAULT",
        "BLOCKED": "GATE_BLOCKED_BY_DEFAULT",
    }[str(default)]
    return _decision(
        flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
        gate=gate, policy_ref=policy_ref, decision=str(default),
        reason_code=reason, context=context,
    )


__all__ = ["evaluate_gate_applicability"]
