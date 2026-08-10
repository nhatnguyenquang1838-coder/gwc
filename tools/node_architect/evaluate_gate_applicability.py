"""Evaluate workflow gate applicability from a flow-profile policy.

The evaluator is intentionally pure and controller-agnostic. It consumes a
``flow-profile`` workflow gate binding plus runtime facts and returns exactly
one of ``REQUIRED``, ``NOT_APPLICABLE`` or ``BLOCKED``.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

DECISIONS = {"REQUIRED", "NOT_APPLICABLE", "BLOCKED"}
OPERATORS = {"equals", "in", "exists", "truthy"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Mapping[str, Any]) -> str:
    unsigned = dict(value)
    unsigned.pop("decision_digest", None)
    return "sha256:" + hashlib.sha256(_canonical(unsigned).encode("utf-8")).hexdigest()


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
        return exists is bool(expected)
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


def _decision(*, gate: str, policy_id: str | None, decision: str, reason_code: str,
              matched_rule: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "gate-applicability-decision",
        "gate": gate,
        "policy_id": policy_id,
        "decision": decision,
        "reason_code": reason_code,
        "matched_rule": matched_rule,
    }
    payload["decision_digest"] = _digest(payload)
    return payload


def evaluate_gate_applicability(*, flow_profile: Mapping[str, Any], gate: str,
                                context: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic applicability decision for ``gate``.

    Precedence is fail-closed and deterministic: ``BLOCKED`` rules win over
    ``REQUIRED`` rules, which win over explicit ``NOT_APPLICABLE`` rules, then
    the binding default applies. Duplicate or missing bindings are blocked.
    """
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return _decision(
            gate=gate, policy_id=None, decision="BLOCKED",
            reason_code="WORKFLOW_CONTRACT_MISSING",
        )
    bindings = [
        item for item in workflow.get("gate_bindings", [])
        if isinstance(item, Mapping) and item.get("gate") == gate
    ]
    if len(bindings) != 1:
        return _decision(
            gate=gate, policy_id=None, decision="BLOCKED",
            reason_code="GATE_BINDING_MISSING" if not bindings else "GATE_BINDING_AMBIGUOUS",
        )

    binding = bindings[0]
    policy_id = str(binding.get("policy_id") or "") or None
    blocked = _first_match(binding.get("blocked_when"), context)
    if blocked:
        return _decision(
            gate=gate, policy_id=policy_id, decision="BLOCKED",
            reason_code="GATE_POLICY_BLOCKED", matched_rule=blocked,
        )
    required = _first_match(binding.get("required_when"), context)
    if required:
        return _decision(
            gate=gate, policy_id=policy_id, decision="REQUIRED",
            reason_code="GATE_REQUIRED_BY_POLICY", matched_rule=required,
        )
    not_applicable = _first_match(binding.get("not_applicable_when"), context)
    if not_applicable:
        return _decision(
            gate=gate, policy_id=policy_id, decision="NOT_APPLICABLE",
            reason_code="GATE_NOT_APPLICABLE_BY_POLICY", matched_rule=not_applicable,
        )

    default = binding.get("default")
    if default not in DECISIONS:
        return _decision(
            gate=gate, policy_id=policy_id, decision="BLOCKED",
            reason_code="GATE_POLICY_INVALID",
        )
    reason = {
        "REQUIRED": "GATE_REQUIRED_BY_DEFAULT",
        "NOT_APPLICABLE": "GATE_NOT_APPLICABLE_BY_DEFAULT",
        "BLOCKED": "GATE_BLOCKED_BY_DEFAULT",
    }[str(default)]
    return _decision(
        gate=gate, policy_id=policy_id, decision=str(default), reason_code=reason,
    )


__all__ = ["evaluate_gate_applicability"]
