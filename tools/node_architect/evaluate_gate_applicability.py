"""Evaluate gate applicability from a workflow-bound policy registry.

The evaluator is pure, controller-agnostic and fail-closed. Workflow
composition only binds ``gate -> policy_ref``; applicability rules, authority
constraints, evidence requirements, prohibitions and terminal acceptance live
in a separate policy registry.

The result is a deterministic, digest-bound decision artifact emitting exactly
one of ``REQUIRED``, ``NOT_APPLICABLE`` or ``BLOCKED``. The evaluator contains
no route-specific, controller-specific or task-specific branching: every
route-dependent outcome is expressed by policy data plus runtime context.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

DECISIONS = {"REQUIRED", "NOT_APPLICABLE", "BLOCKED"}
OPERATORS = {"equals", "in", "exists", "truthy"}
CANONICAL_GATES = (
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION_DATA",
)

#: Terminal acceptance semantics. ``NOT_APPLICABLE`` is explicit skip evidence
#: and is never an implicit PASS.
DEFAULT_TERMINAL_EFFECT = {
    "REQUIRED": "GATE_MUST_BE_SATISFIED",
    "NOT_APPLICABLE": "GATE_SKIPPED_WITH_EXPLICIT_EVIDENCE",
    "BLOCKED": "GATE_PROGRESS_HALTED",
}

_UNSATISFIED_EVIDENCE_STATES = {"MISSING", "STALE", "CONFLICTING", "INVALID", "UNKNOWN"}


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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item) for item in value if isinstance(item, str) and item})


def _binding(context: Mapping[str, Any]) -> dict[str, str]:
    exists, raw = _read_path(context, "binding")
    source = raw if exists and isinstance(raw, Mapping) else {}
    return {
        "run_id": str(source.get("run_id") or "unbound"),
        "task_id": str(source.get("task_id") or "unbound"),
        "repository": str(source.get("repository") or "unbound"),
    }


def _terminal_effect(policy: Mapping[str, Any], decision: str) -> str:
    declared = policy.get("terminal_effect")
    if isinstance(declared, Mapping):
        value = declared.get(decision)
        if isinstance(value, str) and value:
            return value
    return DEFAULT_TERMINAL_EFFECT[decision]


def _decision(*, flow_profile_id: str, flow_profile_version: str,
              flow_profile_digest: str, policy_registry_ref: str,
              policy_registry_digest: str, gate: str, policy_ref: str | None,
              policy_version: str | None, policy_digest: str | None,
              decision: str, reason_code: str, context: Mapping[str, Any],
              matched_rule: str | None = None,
              required_evidence: list[str] | None = None,
              prohibitions: list[str] | None = None,
              authority_source: str | None = None,
              authority_type: str | None = None,
              terminal_effect: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "artifact_type": "gate-applicability-decision",
        "binding": _binding(context),
        "flow_profile_id": flow_profile_id or "unbound",
        "flow_profile_version": flow_profile_version or "unbound",
        "flow_profile_digest": flow_profile_digest,
        "policy_registry_ref": policy_registry_ref or "unbound",
        "policy_registry_digest": policy_registry_digest,
        "gate": gate,
        "policy_ref": policy_ref,
        "policy_version": policy_version,
        "policy_digest": policy_digest,
        "decision": decision,
        "reason_code": reason_code,
        "matched_rule": matched_rule,
        "required_evidence": required_evidence or [],
        "prohibitions": prohibitions or [],
        "authority_source": authority_source,
        "authority_type": authority_type,
        "terminal_effect": terminal_effect or DEFAULT_TERMINAL_EFFECT[decision],
        "context_digest": _sha256(context),
    }
    payload["decision_digest"] = _sha256(payload)
    return payload


def _context_binding_failure(policy: Mapping[str, Any],
                             context: Mapping[str, Any]) -> str | None:
    """Return a fail-closed reason code when the bound context is unusable."""
    requirements = policy.get("context_requirements")
    if not isinstance(requirements, Mapping):
        return None

    for field in _string_list(requirements.get("required_fields")):
        exists, value = _read_path(context, field)
        if not exists or value is None:
            return "CONTEXT_BINDING_INCOMPLETE"

    expected_digest = requirements.get("expected_context_digest")
    if isinstance(expected_digest, str) and expected_digest:
        exists, actual = _read_path(context, "context_digest")
        if not exists or str(actual) != expected_digest:
            return "CONTEXT_DIGEST_MISMATCH"

    max_age = requirements.get("max_context_age_seconds")
    if isinstance(max_age, int) and not isinstance(max_age, bool):
        has_age, age = _read_path(context, "context_age_seconds")
        if not has_age or not isinstance(age, (int, float)) or isinstance(age, bool):
            return "CONTEXT_FRESHNESS_UNKNOWN"
        if age < 0 or age > max_age:
            return "CONTEXT_STALE"
    return None


def _evidence_failure(policy: Mapping[str, Any], context: Mapping[str, Any],
                      required_evidence: list[str]) -> str | None:
    """Evidence required by policy must be present and unambiguous."""
    if not required_evidence:
        return None
    if not policy.get("evidence_must_be_bound"):
        return None
    exists, evidence = _read_path(context, "evidence")
    if not exists or not isinstance(evidence, Mapping):
        return "EVIDENCE_BINDING_MISSING"
    for name in required_evidence:
        if name not in evidence:
            return "EVIDENCE_BINDING_MISSING"
        state = evidence[name]
        if isinstance(state, str) and state.upper() in _UNSATISFIED_EVIDENCE_STATES:
            return "EVIDENCE_BINDING_UNSATISFIED"
        if state is None or state is False:
            return "EVIDENCE_BINDING_UNSATISFIED"
    return None


def _authority(policy: Mapping[str, Any], context: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Resolve (source, type, failure_reason) for an applicable gate."""
    declared = policy.get("authority")
    if not isinstance(declared, Mapping):
        return None, None, None

    allowed_sources = _string_list(declared.get("allowed_sources"))
    allowed_types = _string_list(declared.get("allowed_types"))
    exists, runtime = _read_path(context, "authority")
    runtime = runtime if exists and isinstance(runtime, Mapping) else {}
    source = runtime.get("source") or declared.get("default_source")
    kind = runtime.get("type") or declared.get("default_type")

    if declared.get("required") and (not source or not kind):
        return None, None, "AUTHORITY_SOURCE_UNRESOLVED"
    if source is not None and allowed_sources and str(source) not in allowed_sources:
        return None, None, "AUTHORITY_SOURCE_NOT_PERMITTED"
    if kind is not None and allowed_types and str(kind) not in allowed_types:
        return None, None, "AUTHORITY_TYPE_NOT_PERMITTED"
    return (str(source) if source else None, str(kind) if kind else None, None)


def evaluate_gate_applicability(*, flow_profile: Mapping[str, Any],
                                policy_registry: Mapping[str, Any], gate: str,
                                context: Mapping[str, Any]) -> dict[str, Any]:
    """Return REQUIRED, NOT_APPLICABLE or BLOCKED for one canonical gate.

    Precedence is deterministic and fail-closed: binding/context/evidence
    integrity failures block first, then BLOCKED rules win over REQUIRED
    rules, which win over explicit NOT_APPLICABLE rules; otherwise the policy
    default applies. Missing/ambiguous bindings or policies block.
    """
    flow_profile_id = str(flow_profile.get("id") or "unbound")
    flow_profile_version = str(flow_profile.get("version") or "unbound")
    flow_profile_digest = _sha256(flow_profile)
    policy_registry_digest = _sha256(policy_registry)
    expected_registry = str(flow_profile.get("policy_registry_ref") or "")
    actual_registry = str(policy_registry.get("registry_id") or "")
    registry_ref = expected_registry or actual_registry or "unbound"

    def block(reason: str, policy_ref: str | None = None, **extra: Any) -> dict[str, Any]:
        return _decision(
            flow_profile_id=flow_profile_id,
            flow_profile_version=flow_profile_version,
            flow_profile_digest=flow_profile_digest,
            policy_registry_ref=registry_ref,
            policy_registry_digest=policy_registry_digest,
            gate=gate, policy_ref=policy_ref, policy_version=extra.pop("policy_version", None),
            policy_digest=extra.pop("policy_digest", None),
            decision="BLOCKED", reason_code=reason, context=context, **extra,
        )

    if gate not in CANONICAL_GATES:
        return block("GATE_NOT_CANONICAL")

    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return block("WORKFLOW_CONTRACT_MISSING")
    if not expected_registry or expected_registry != actual_registry:
        return block("POLICY_REGISTRY_BINDING_MISMATCH")

    bindings = [
        item for item in workflow.get("gate_bindings", [])
        if isinstance(item, Mapping) and item.get("gate") == gate
    ]
    if len(bindings) != 1:
        return block("GATE_BINDING_MISSING" if not bindings else "GATE_BINDING_AMBIGUOUS")

    policy_ref = str(bindings[0].get("policy_ref") or "") or None
    policies = [
        item for item in policy_registry.get("policies", [])
        if isinstance(item, Mapping) and item.get("id") == policy_ref
    ]
    if len(policies) != 1:
        return block(
            "GATE_POLICY_MISSING" if not policies else "GATE_POLICY_AMBIGUOUS",
            policy_ref=policy_ref,
        )

    policy = policies[0]
    policy_version = str(policy.get("version") or "") or None
    policy_digest = _sha256(policy)
    required_evidence = _string_list(policy.get("required_evidence"))
    prohibitions = _string_list(policy.get("prohibitions"))

    def emit(decision: str, reason: str, matched_rule: str | None = None,
             authority_source: str | None = None, authority_type: str | None = None) -> dict[str, Any]:
        return _decision(
            flow_profile_id=flow_profile_id,
            flow_profile_version=flow_profile_version,
            flow_profile_digest=flow_profile_digest,
            policy_registry_ref=registry_ref,
            policy_registry_digest=policy_registry_digest,
            gate=gate, policy_ref=policy_ref, policy_version=policy_version,
            policy_digest=policy_digest, decision=decision, reason_code=reason,
            context=context, matched_rule=matched_rule,
            required_evidence=required_evidence, prohibitions=prohibitions,
            authority_source=authority_source, authority_type=authority_type,
            terminal_effect=_terminal_effect(policy, decision),
        )

    if policy_version is None:
        return emit("BLOCKED", "GATE_POLICY_UNVERSIONED")

    context_failure = _context_binding_failure(policy, context)
    if context_failure:
        return emit("BLOCKED", context_failure)

    blocked = _first_match(policy.get("blocked_when"), context)
    if blocked:
        return emit("BLOCKED", "GATE_POLICY_BLOCKED", matched_rule=blocked)

    required = _first_match(policy.get("required_when"), context)
    not_applicable = _first_match(policy.get("not_applicable_when"), context)
    default = policy.get("default")
    if default not in DECISIONS:
        return emit("BLOCKED", "GATE_POLICY_INVALID")

    if required:
        decision, reason, matched = "REQUIRED", "GATE_REQUIRED_BY_POLICY", required
    elif not_applicable:
        decision, reason, matched = "NOT_APPLICABLE", "GATE_NOT_APPLICABLE_BY_POLICY", not_applicable
    else:
        decision = str(default)
        matched = None
        reason = {
            "REQUIRED": "GATE_REQUIRED_BY_DEFAULT",
            "NOT_APPLICABLE": "GATE_NOT_APPLICABLE_BY_DEFAULT",
            "BLOCKED": "GATE_BLOCKED_BY_DEFAULT",
        }[decision]

    if decision != "REQUIRED":
        return emit(decision, reason, matched_rule=matched)

    evidence_failure = _evidence_failure(policy, context, required_evidence)
    if evidence_failure:
        return emit("BLOCKED", evidence_failure, matched_rule=matched)

    source, kind, authority_failure = _authority(policy, context)
    if authority_failure:
        return emit("BLOCKED", authority_failure, matched_rule=matched)
    return emit(decision, reason, matched_rule=matched,
                authority_source=source, authority_type=kind)


__all__ = [
    "evaluate_gate_applicability",
    "CANONICAL_GATES",
    "DECISIONS",
    "DEFAULT_TERMINAL_EFFECT",
]
