"""Evaluate the generic gate Policy contract for one canonical gate.

The evaluator is pure, controller-agnostic and side-effect free. Workflow
composition only binds ``gate -> policy_ref``; every applicability, authority,
evidence, prohibition and terminal-acceptance rule lives in the Policy
registry. The result is a deterministic, digest-bound decision artifact.

Policy MUST NOT define node ordering, execute actions, invent gates outside
G0..G6, or weaken the registry's canonical minimum constraints
(``tighten_only``). Unknown, stale or conflicting input fails closed to
``BLOCKED``.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

EVALUATOR_NAME = "evaluate_gate_applicability"
EVALUATOR_VERSION = "1.1.0"
DECISION_SCHEMA_VERSION = "1.1"

DECISIONS = {"REQUIRED", "NOT_APPLICABLE", "BLOCKED"}
OPERATORS = {"equals", "in", "exists", "truthy"}
CANONICAL_GATES = (
    "G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR",
    "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA",
)
# Strength ordering used by tighten_only: a Policy may strengthen the canonical
# minimum (NOT_APPLICABLE -> REQUIRED -> BLOCKED) but never weaken it.
_STRENGTH = {"NOT_APPLICABLE": 0, "REQUIRED": 1, "BLOCKED": 2}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def policy_digest(policy: Mapping[str, Any]) -> str:
    """Stable digest of a single Policy unit."""
    return _sha256(policy)


def policy_registry_digest(policy_registry: Mapping[str, Any]) -> str:
    """Stable digest of the whole Policy registry, independent of Workflow."""
    return _sha256(policy_registry)


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


def _unmatched(conditions: Any, context: Mapping[str, Any]) -> list[str]:
    if not isinstance(conditions, list):
        return []
    unmet: list[str] = []
    for index, condition in enumerate(conditions):
        if not isinstance(condition, Mapping) or not _condition_matches(condition, context):
            unmet.append(str((condition or {}).get("id") if isinstance(condition, Mapping)
                             else None) or f"rule-{index + 1}")
    return unmet


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _evaluate_authority(policy: Mapping[str, Any],
                        context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Report authority requirements. Never grants authority."""
    results: list[dict[str, Any]] = []
    requirements = policy.get("authority_requirements")
    if not isinstance(requirements, list):
        return results

    _, bound = _read_path(context, "authority")
    bound_list = [item for item in bound if isinstance(item, Mapping)] if isinstance(bound, list) else []
    now = _parse_timestamp(context.get("now"))

    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, Mapping):
            continue
        req_id = str(requirement.get("id") or f"authority-{index + 1}")
        req_type = str(requirement.get("authority_type") or "")
        raw_equivalence = requirement.get("equivalence")
        equivalence: Mapping[str, Any] = raw_equivalence if isinstance(raw_equivalence, Mapping) else {}
        raw_accepts = equivalence.get("accepts")
        accepts: list[Any] = raw_accepts if isinstance(raw_accepts, list) else []
        accepted_types = {req_type, *(str(item) for item in accepts)}

        candidates = [item for item in bound_list if str(item.get("authority_type") or "") in accepted_types]
        if not candidates:
            results.append({"id": req_id, "authority_type": req_type, "satisfied": False,
                            "reason_code": "AUTHORITY_MISSING"})
            continue

        reason = "AUTHORITY_SATISFIED"
        satisfied = False
        for candidate in candidates:
            providers = requirement.get("allowed_providers")
            if isinstance(providers, list) and providers and str(candidate.get("provider") or "") not in {str(p) for p in providers}:
                reason = "AUTHORITY_PROVIDER_NOT_ALLOWED"
                continue
            bindings = requirement.get("required_bindings")
            if isinstance(bindings, list) and bindings:
                raw_bindings = candidate.get("bindings")
                candidate_bindings: Mapping[str, Any] = raw_bindings if isinstance(raw_bindings, Mapping) else {}
                missing = [str(name) for name in bindings
                           if not str(candidate_bindings.get(str(name)) or "")]
                if missing:
                    reason = "AUTHORITY_BINDING_MISSING"
                    continue
            max_age = requirement.get("max_age_seconds")
            issued_at = _parse_timestamp(candidate.get("issued_at"))
            if isinstance(max_age, int):
                if now is None or issued_at is None:
                    reason = "AUTHORITY_FRESHNESS_UNKNOWN"
                    continue
                if (now - issued_at).total_seconds() > max_age:
                    reason = "AUTHORITY_EXPIRED"
                    continue
            expires_at = _parse_timestamp(candidate.get("expires_at"))
            if expires_at is not None and now is not None and now > expires_at:
                reason = "AUTHORITY_EXPIRED"
                continue
            if str(candidate.get("authority_type") or "") != req_type and \
                    str(equivalence.get("mode") or "exact") == "exact":
                reason = "AUTHORITY_EQUIVALENCE_NOT_DECLARED"
                continue
            satisfied = True
            reason = "AUTHORITY_SATISFIED"
            break

        results.append({"id": req_id, "authority_type": req_type,
                        "satisfied": satisfied, "reason_code": reason})
    return results


def _evaluate_evidence(policy: Mapping[str, Any],
                       context: Mapping[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    requirements = policy.get("evidence_requirements")
    if not isinstance(requirements, list):
        return results

    _, present = _read_path(context, "evidence")
    present_list = [item for item in present if isinstance(item, Mapping)] if isinstance(present, list) else []

    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, Mapping):
            continue
        req_id = str(requirement.get("id") or f"evidence-{index + 1}")
        req_type = str(requirement.get("evidence_type") or "")
        matches = [item for item in present_list if str(item.get("evidence_type") or "") == req_type]
        if not matches:
            results.append({"id": req_id, "evidence_type": req_type, "satisfied": False,
                            "reason_code": "EVIDENCE_MISSING"})
            continue
        acceptance = requirement.get("acceptance")
        if isinstance(acceptance, list) and acceptance:
            accepted = any(not _unmatched(acceptance, {"evidence_item": item, **context})
                           for item in matches)
            results.append({"id": req_id, "evidence_type": req_type, "satisfied": accepted,
                            "reason_code": "EVIDENCE_SATISFIED" if accepted else "EVIDENCE_NOT_ACCEPTED"})
            continue
        results.append({"id": req_id, "evidence_type": req_type, "satisfied": True,
                        "reason_code": "EVIDENCE_SATISFIED"})
    return results


def _evaluate_terminal_acceptance(policy: Mapping[str, Any],
                                  context: Mapping[str, Any]) -> dict[str, Any] | None:
    terminal = policy.get("terminal_acceptance")
    if not isinstance(terminal, Mapping):
        return None
    predicates = terminal.get("predicates")
    if not isinstance(predicates, list) or not predicates:
        return {"accepted": False, "reason_code": "TERMINAL_ACCEPTANCE_UNDEFINED", "unmet": []}
    mode = str(terminal.get("mode") or "all")
    unmet = _unmatched(predicates, context)
    accepted = (not unmet) if mode == "all" else len(unmet) < len(predicates)
    return {
        "accepted": accepted,
        "reason_code": "TERMINAL_ACCEPTED" if accepted else "TERMINAL_ACCEPTANCE_UNMET",
        "unmet": unmet,
    }


def _tighten_only_violation(policy_registry: Mapping[str, Any], gate: str,
                            policy: Mapping[str, Any], decision: str) -> str | None:
    """Return a reason code when the Policy weakens the canonical minimum."""
    if not bool(policy_registry.get("tighten_only", False)):
        return None
    minimums = policy_registry.get("canonical_minimums")
    if not isinstance(minimums, Mapping):
        return None
    minimum = minimums.get(gate)
    if not isinstance(minimum, Mapping):
        return None

    min_decision = minimum.get("min_decision")
    if isinstance(min_decision, str) and min_decision in _STRENGTH:
        if _STRENGTH.get(decision, -1) < _STRENGTH[min_decision]:
            return "POLICY_WEAKENS_CANONICAL_MINIMUM"

    required_authority = minimum.get("required_authority_types")
    if isinstance(required_authority, list) and required_authority:
        declared = {str(item.get("authority_type") or "")
                    for item in policy.get("authority_requirements") or []
                    if isinstance(item, Mapping)}
        if not {str(t) for t in required_authority} <= declared:
            return "POLICY_WEAKENS_CANONICAL_AUTHORITY"

    required_evidence = minimum.get("required_evidence_types")
    if isinstance(required_evidence, list) and required_evidence:
        declared_ev = {str(item.get("evidence_type") or "")
                       for item in policy.get("evidence_requirements") or []
                       if isinstance(item, Mapping)}
        if not {str(t) for t in required_evidence} <= declared_ev:
            return "POLICY_WEAKENS_CANONICAL_EVIDENCE"

    prohibited = minimum.get("prohibited_actions")
    if isinstance(prohibited, list) and prohibited:
        declared_actions = {str(item.get("action") or "")
                            for item in policy.get("prohibited_actions") or []
                            if isinstance(item, Mapping)}
        if not {str(a) for a in prohibited} <= declared_actions:
            return "POLICY_WEAKENS_CANONICAL_PROHIBITIONS"
    return None


def _decision(*, flow_profile_id: str, policy_registry_ref: str, gate: str,
              policy_ref: str | None, decision: str, reason_code: str,
              context: Mapping[str, Any], matched_rule: str | None = None,
              policy: Mapping[str, Any] | None = None,
              policy_registry: Mapping[str, Any] | None = None,
              authority: list[dict[str, Any]] | None = None,
              evidence: list[dict[str, Any]] | None = None,
              terminal: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = policy_registry if isinstance(policy_registry, Mapping) else {}
    payload: dict[str, Any] = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "artifact_type": "gate-applicability-decision",
        "flow_profile_id": flow_profile_id or "unbound",
        "policy_registry_ref": policy_registry_ref or "unbound",
        "gate": gate,
        "policy_ref": policy_ref,
        "policy_version": str(policy.get("version")) if isinstance(policy, Mapping) and policy.get("version") else None,
        "policy_digest": policy_digest(policy) if isinstance(policy, Mapping) else None,
        "policy_registry_digest": policy_registry_digest(registry) if registry else None,
        "decision": decision,
        "reason_code": reason_code,
        "matched_rule": matched_rule,
        "authority_requirements": authority or [],
        "evidence_requirements": evidence or [],
        "prohibited_actions": sorted(
            {str(item.get("action") or "") for item in (policy or {}).get("prohibited_actions") or []
             if isinstance(item, Mapping) and item.get("action")}
        ),
        "terminal_acceptance": terminal,
        "provenance": {
            "evaluator": EVALUATOR_NAME,
            "evaluator_version": EVALUATOR_VERSION,
            "policy_contract_version": str(registry.get("policy_contract_version"))
            if registry.get("policy_contract_version") else None,
            "tighten_only": bool(registry.get("tighten_only", False)),
        },
        "context_digest": _sha256(context),
    }
    payload["decision_digest"] = _sha256(payload)
    return payload


def evaluate_gate_applicability(*, flow_profile: Mapping[str, Any],
                                policy_registry: Mapping[str, Any], gate: str,
                                context: Mapping[str, Any]) -> dict[str, Any]:
    """Return REQUIRED, NOT_APPLICABLE or BLOCKED for one canonical gate.

    Precedence is deterministic and fail-closed: non-canonical gates, missing
    or ambiguous bindings/policies, expired policies and ``tighten_only``
    violations block; then BLOCKED rules win over REQUIRED rules, which win
    over explicit NOT_APPLICABLE rules; otherwise the policy default applies.
    """
    flow_profile_id = str(flow_profile.get("id") or "unbound")
    expected_registry = str(flow_profile.get("policy_registry_ref") or "")
    actual_registry = str(policy_registry.get("registry_id") or "")
    registry_ref = expected_registry or actual_registry or "unbound"

    def block(reason: str, *, policy_ref: str | None = None,
              policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=policy_ref, decision="BLOCKED",
            reason_code=reason, context=context, policy=policy,
            policy_registry=policy_registry,
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
        return block("GATE_POLICY_MISSING" if not policies else "GATE_POLICY_AMBIGUOUS",
                     policy_ref=policy_ref)

    policy = policies[0]

    expires_at = policy.get("expires_at")
    if expires_at is not None:
        expiry = _parse_timestamp(expires_at)
        now = _parse_timestamp(context.get("now"))
        if expiry is None:
            return block("POLICY_EXPIRY_UNPARSEABLE", policy_ref=policy_ref, policy=policy)
        if now is None:
            return block("POLICY_FRESHNESS_UNKNOWN", policy_ref=policy_ref, policy=policy)
        if now > expiry:
            return block("POLICY_EXPIRED", policy_ref=policy_ref, policy=policy)

    applies_when = policy.get("applies_when")
    scoped_out = isinstance(applies_when, list) and applies_when and \
        _first_match(applies_when, context) is None

    authority = _evaluate_authority(policy, context)
    evidence = _evaluate_evidence(policy, context)
    terminal = _evaluate_terminal_acceptance(policy, context)

    def emit(decision: str, reason: str, matched: str | None = None) -> dict[str, Any]:
        violation = _tighten_only_violation(policy_registry, gate, policy, decision)
        if violation:
            return _decision(
                flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
                gate=gate, policy_ref=policy_ref, decision="BLOCKED",
                reason_code=violation, context=context, policy=policy,
                policy_registry=policy_registry, authority=authority,
                evidence=evidence, terminal=terminal,
            )
        return _decision(
            flow_profile_id=flow_profile_id, policy_registry_ref=registry_ref,
            gate=gate, policy_ref=policy_ref, decision=decision,
            reason_code=reason, matched_rule=matched, context=context,
            policy=policy, policy_registry=policy_registry, authority=authority,
            evidence=evidence, terminal=terminal,
        )

    if scoped_out:
        return emit("NOT_APPLICABLE", "POLICY_SCOPE_NOT_MATCHED")

    blocked = _first_match(policy.get("blocked_when"), context)
    if blocked:
        return emit("BLOCKED", "GATE_POLICY_BLOCKED", blocked)
    required = _first_match(policy.get("required_when"), context)
    if required:
        return emit("REQUIRED", "GATE_REQUIRED_BY_POLICY", required)
    not_applicable = _first_match(policy.get("not_applicable_when"), context)
    if not_applicable:
        return emit("NOT_APPLICABLE", "GATE_NOT_APPLICABLE_BY_POLICY", not_applicable)

    default = policy.get("default")
    if default not in DECISIONS:
        return block("GATE_POLICY_INVALID", policy_ref=policy_ref, policy=policy)
    reason = {
        "REQUIRED": "GATE_REQUIRED_BY_DEFAULT",
        "NOT_APPLICABLE": "GATE_NOT_APPLICABLE_BY_DEFAULT",
        "BLOCKED": "GATE_BLOCKED_BY_DEFAULT",
    }[str(default)]
    return emit(str(default), reason)


__all__ = [
    "evaluate_gate_applicability",
    "policy_digest",
    "policy_registry_digest",
    "EVALUATOR_VERSION",
    "CANONICAL_GATES",
]
