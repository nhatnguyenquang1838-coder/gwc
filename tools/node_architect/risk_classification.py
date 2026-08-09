#!/usr/bin/env python3
"""Deterministic, read-only risk classification for intake_context.

The evaluator consumes verified upstream intake artifacts and an explicitly
versioned policy. It never grants execution, merge, deployment, or production
authority. Unknown evidence and policy drift fail closed.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "risk-profile"
CONTRACT_REVISION = "risk-classification/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[^/\s]+/[^/\s]+$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")

AUTH_FIELDS = (
    "write_authority_granted",
    "commit_authority_granted",
    "push_authority_granted",
    "pr_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
)

RISK_LEVELS = ("R0", "R1", "R2", "R3")
RISK_ORDER = {level: index for index, level in enumerate(RISK_LEVELS)}
REASON_CODES = {
    "RISK_PRODUCTION_OPERATION",
    "RISK_SECRET_CHANGE",
    "RISK_DESTRUCTIVE_OPERATION",
    "RISK_MIGRATION",
    "RISK_RELEASE_DEPLOYMENT",
    "RISK_SCOPE_AMBIGUOUS",
    "RISK_SOURCE_STALE",
    "RISK_UNCLASSIFIED",
    "RISK_CLASSIFIED_R0",
    "RISK_CLASSIFIED_R1",
    "RISK_CLASSIFIED_R2",
    "RISK_CLASSIFIED_R3",
}

UPSTREAM_TYPES = {
    "request_intake": "intake-request",
    "source_resolution": "source-resolution",
    "repo_identity": "repo-identity",
    "protected_base_snapshot": "protected-base-capture",
}

SIGNAL_PATTERNS = {
    "production_scope": re.compile(r"\b(production|prod[- ]data|prod[- ]config)\b", re.I),
    "secret_change": re.compile(r"\b(secret|credential|token|password|api[- ]key|private[- ]key)\b", re.I),
    "destructive_operation": re.compile(r"\b(destructive|irreversible|destroy|delete[- ]branch|force[- ]push)\b", re.I),
    "migration": re.compile(r"\b(migration|migrate|cutover|schema[- ]migration)\b", re.I),
    "release_deployment": re.compile(r"\b(deploy|deployment|release|publish|rollout)\b", re.I),
    "schema_change": re.compile(r"\b(schema|contract|typed)\b", re.I),
    "workflow_change": re.compile(r"\b(workflow|gate|authority|route)\b", re.I),
    "repository_change": re.compile(r"\b(implement|add|update|fix|change|modify|build|test)\b", re.I),
}

DEFAULT_RULES = {
    "production_scope": {"risk_level": "R3", "risk_flag": "production_scope", "reason_code": "RISK_PRODUCTION_OPERATION", "additional_authority_gates": ["G6_PRODUCTION_DATA"]},
    "secret_change": {"risk_level": "R3", "risk_flag": "secret_change", "reason_code": "RISK_SECRET_CHANGE", "additional_authority_gates": ["G6_PRODUCTION_DATA"]},
    "destructive_operation": {"risk_level": "R3", "risk_flag": "destructive_operation", "reason_code": "RISK_DESTRUCTIVE_OPERATION", "additional_authority_gates": []},
    "migration": {"risk_level": "R2", "risk_flag": "migration", "reason_code": "RISK_MIGRATION", "additional_authority_gates": []},
    "release_deployment": {"risk_level": "R3", "risk_flag": "release_deployment", "reason_code": "RISK_RELEASE_DEPLOYMENT", "additional_authority_gates": ["G5_DEPLOY"]},
    "schema_change": {"risk_level": "R2", "risk_flag": "schema_change", "reason_code": "RISK_UNCLASSIFIED", "additional_authority_gates": []},
    "workflow_change": {"risk_level": "R2", "risk_flag": "workflow_change", "reason_code": "RISK_UNCLASSIFIED", "additional_authority_gates": []},
    "repository_change": {"risk_level": "R1", "risk_flag": "bounded_repository_change", "reason_code": "RISK_UNCLASSIFIED", "additional_authority_gates": []},
}

REQUIRED_GATE_BY_LEVEL = {
    "R0": "G2_AUTOMATIC_BOUNDED",
    "R1": "G2_AUTOMATIC_BOUNDED",
    "R2": "G2_HUMAN_DIRECTION",
    "R3": "G2_HUMAN_DIRECTION",
}


def _canon(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        items = [_canon(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canon(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def compute_policy_digest(policy: Mapping[str, Any]) -> str:
    return digest_payload({key: value for key, value in policy.items() if key != "digest"})


def build_default_policy() -> dict[str, Any]:
    policy: dict[str, Any] = {
        "policy_id": "gwc-risk-policy",
        "version": "1.0",
        "rules": DEFAULT_RULES,
        "required_gate_by_level": REQUIRED_GATE_BY_LEVEL,
    }
    policy["digest"] = compute_policy_digest(policy)
    return policy


def _safe_identity(task_id: Any, repository: Any, base_sha: Any) -> tuple[str, str, str]:
    safe_task = task_id if isinstance(task_id, str) and task_id else "UNKNOWN"
    safe_repo = repository if isinstance(repository, str) and REPO.fullmatch(repository) else "invalid/invalid"
    safe_base = base_sha if isinstance(base_sha, str) and SHA40.fullmatch(base_sha) else "0" * 40
    return safe_task, safe_repo, safe_base


def _policy_provenance(policy: Any) -> dict[str, Any]:
    if not isinstance(policy, Mapping):
        return {"policy_id": None, "version": None, "digest": None, "rules_digest": None, "source": None}
    rules = policy.get("rules")
    return {
        "policy_id": policy.get("policy_id") if isinstance(policy.get("policy_id"), str) else None,
        "version": policy.get("version") if isinstance(policy.get("version"), str) else None,
        "digest": policy.get("digest") if isinstance(policy.get("digest"), str) else None,
        "rules_digest": digest_payload(rules) if isinstance(rules, Mapping) else None,
        "source": "declared-policy",
    }


def _source_bindings(artifacts: Mapping[str, Any], repository: str, base_sha: str) -> dict[str, Any]:
    def first_digest(artifact: Any, *keys: str) -> str | None:
        if not isinstance(artifact, Mapping):
            return None
        for key in keys:
            value = artifact.get(key)
            if isinstance(value, str) and SHA256.fullmatch(value):
                return value
        return None

    return {
        "request_intake": first_digest(artifacts.get("request_intake"), "decision_digest"),
        "source_resolution": first_digest(artifacts.get("source_resolution"), "source_set_digest", "decision_digest"),
        "repo_identity": first_digest(artifacts.get("repo_identity"), "decision_digest"),
        "protected_base_capture": first_digest(artifacts.get("protected_base_snapshot"), "decision_digest"),
        "repository": repository,
        "base_sha": base_sha,
    }


def _routing(reason_code: str) -> tuple[str, str, dict[str, str]]:
    if reason_code == "RISK_SCOPE_AMBIGUOUS":
        return "HUMAN_REQUIRED", "G2_HUMAN_DIRECTION", {"route": "REQUEST_HUMAN_INPUT", "next_action": "Resolve conflicting risk scope and replay classification.", "stop_condition": "Stop until a human resolves the risk ambiguity."}
    if reason_code == "RISK_SOURCE_STALE":
        return "BLOCKED", "G1_ALIGNMENT", {"route": "REFRESH_SOURCE", "next_action": "Refresh stale policy or upstream evidence and recompute risk.", "stop_condition": "Stop until all risk evidence is current and rebound."}
    return "BLOCKED", "G1_ALIGNMENT", {"route": "BLOCK_G1_REVIEW", "next_action": "Repair missing, unknown, or malformed risk evidence.", "stop_condition": "Stop until required risk inputs are verified."}


def _artifact(
    *, task_id: str, repository: str, base_sha: str, outcome: str, risk_level: str | None,
    risk_flags: list[str], required_gate: str, additional_authority_gates: list[str],
    approval_requirements: list[str], reason_code: str, reason_codes: list[str],
    source_bindings: Mapping[str, Any], policy_provenance: Mapping[str, Any],
    contributing_signals: list[Mapping[str, Any]], remediation: Mapping[str, Any] | None,
    next_allowed_nodes: list[str], classified_at: str | None,
) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "contract_revision": CONTRACT_REVISION,
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "outcome": outcome,
        "risk_level": risk_level,
        "risk_flags": sorted(set(risk_flags)),
        "required_gate": required_gate,
        "additional_authority_gates": sorted(set(additional_authority_gates)),
        "approval_requirements": list(dict.fromkeys(approval_requirements)),
        "reason_code": reason_code,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "source_bindings": dict(source_bindings),
        "policy_provenance": dict(policy_provenance),
        "contributing_signals": [dict(signal) for signal in contributing_signals],
        "remediation": dict(remediation) if remediation else None,
        "next_allowed_nodes": list(next_allowed_nodes),
        "classified_at": classified_at,
        "read_only_projection": True,
        **{field: False for field in AUTH_FIELDS},
    }
    digest_input = {key: value for key, value in artifact.items() if key not in {"decision_digest", "classified_at"}}
    artifact["decision_digest"] = digest_payload(digest_input)
    return artifact


def _blocked(
    *, task_id: str, repository: str, base_sha: str, reason_code: str,
    source_bindings: Mapping[str, Any], policy_provenance: Mapping[str, Any],
    classified_at: str | None, risk_flags: list[str] | None = None,
) -> dict[str, Any]:
    outcome, gate, remediation = _routing(reason_code)
    return _artifact(
        task_id=task_id, repository=repository, base_sha=base_sha,
        outcome=outcome, risk_level=None,
        risk_flags=risk_flags or ["unclassified" if reason_code == "RISK_UNCLASSIFIED" else "source_stale"],
        required_gate=gate, additional_authority_gates=[],
        approval_requirements=["No downstream gate may proceed until risk evidence is repaired or explicitly resolved."],
        reason_code=reason_code, reason_codes=[reason_code],
        source_bindings=source_bindings, policy_provenance=policy_provenance,
        contributing_signals=[], remediation=remediation,
        next_allowed_nodes=[], classified_at=classified_at,
    )


def _upstream_failure(
    *, artifacts: Mapping[str, Any], repository: str, base_sha: str,
) -> tuple[str | None, str | None]:
    for name, expected_type in UPSTREAM_TYPES.items():
        artifact = artifacts.get(name)
        if not isinstance(artifact, Mapping) or artifact.get("artifact_type") != expected_type:
            return "RISK_UNCLASSIFIED", None
        if artifact.get("repository") != repository or artifact.get("base_sha") != base_sha:
            return "RISK_SCOPE_AMBIGUOUS", None
        outcome = artifact.get("outcome")
        if outcome != "ACCEPTED":
            if name == "protected_base_snapshot" and artifact.get("drift_state") in {"STALE", "DRIFTED"}:
                return "RISK_SOURCE_STALE", None
            if outcome == "HUMAN_REQUIRED":
                return "RISK_SCOPE_AMBIGUOUS", None
            return "RISK_UNCLASSIFIED", None
    repo = artifacts["repo_identity"]
    protected = artifacts["protected_base_snapshot"]
    if repo.get("identity_match") is not True:
        return "RISK_SCOPE_AMBIGUOUS", None
    if protected.get("protected_base_sha") != base_sha or protected.get("verified_sha") not in {None, base_sha}:
        return "RISK_SOURCE_STALE", None
    if protected.get("readback_status") != "VERIFIED" or protected.get("drift_state") != "NONE":
        return "RISK_SOURCE_STALE", None
    bindings = _source_bindings(artifacts, repository, base_sha)
    if any(not isinstance(bindings[key], str) or not SHA256.fullmatch(bindings[key]) for key in ("request_intake", "source_resolution", "repo_identity", "protected_base_capture")):
        return "RISK_UNCLASSIFIED", None
    return None, "ok"


def _signals(request_intake: Mapping[str, Any]) -> tuple[list[str], str | None]:
    explicit = request_intake.get("risk_signals")
    if explicit is not None and (not isinstance(explicit, list) or not all(isinstance(item, str) and item for item in explicit)):
        return [], "RISK_UNCLASSIFIED"
    raw = request_intake.get("request", {}).get("raw_text", "") if isinstance(request_intake.get("request"), Mapping) else ""
    signals = set(explicit or [])
    if not isinstance(raw, str):
        return [], "RISK_UNCLASSIFIED"
    for signal, pattern in SIGNAL_PATTERNS.items():
        if pattern.search(raw):
            signals.add(signal)
    if not signals:
        return [], "RISK_UNCLASSIFIED"
    return sorted(signals), None


def render_risk_classification(
    *, task_id: str, repository: str, base_sha: str,
    request_intake: Mapping[str, Any], source_resolution: Mapping[str, Any],
    repo_identity: Mapping[str, Any], protected_base_snapshot: Mapping[str, Any],
    policy: Mapping[str, Any], prior_classification: Mapping[str, Any] | None = None,
    classified_at: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic risk-profile artifact without granting authority."""
    safe_task, safe_repo, safe_base = _safe_identity(task_id, repository, base_sha)
    artifacts = {
        "request_intake": request_intake,
        "source_resolution": source_resolution,
        "repo_identity": repo_identity,
        "protected_base_snapshot": protected_base_snapshot,
    }
    bindings = _source_bindings(artifacts, safe_repo, safe_base)
    provenance = _policy_provenance(policy)

    if not (isinstance(task_id, str) and task_id and isinstance(repository, str) and REPO.fullmatch(repository) and isinstance(base_sha, str) and SHA40.fullmatch(base_sha)):
        return _blocked(task_id=safe_task, repository=safe_repo, base_sha=safe_base, reason_code="RISK_UNCLASSIFIED", source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)

    failure, _ = _upstream_failure(artifacts=artifacts, repository=repository, base_sha=base_sha)
    if failure:
        return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code=failure, source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)

    if not isinstance(policy, Mapping) or not isinstance(policy.get("policy_id"), str) or not isinstance(policy.get("version"), str) or not SHA256.fullmatch(str(policy.get("digest", ""))) or not isinstance(policy.get("rules"), Mapping) or not isinstance(policy.get("required_gate_by_level"), Mapping):
        return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code="RISK_UNCLASSIFIED", source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)
    if compute_policy_digest(policy) != policy.get("digest"):
        return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code="RISK_SOURCE_STALE", source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)

    if isinstance(prior_classification, Mapping):
        prior_provenance = prior_classification.get("policy_provenance")
        if isinstance(prior_provenance, Mapping) and (prior_provenance.get("version") != policy.get("version") or prior_provenance.get("digest") != policy.get("digest")):
            return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code="RISK_SOURCE_STALE", source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)

    signals, signal_error = _signals(request_intake)
    if signal_error:
        return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code=signal_error, source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)

    rules = policy["rules"]
    unknown = [signal for signal in signals if signal not in rules]
    if unknown:
        return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code="RISK_UNCLASSIFIED", source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)

    contributing: list[dict[str, Any]] = []
    levels: list[str] = []
    flags: list[str] = []
    reasons: list[str] = []
    additional_gates: set[str] = set()
    for signal in signals:
        rule = rules.get(signal)
        if not isinstance(rule, Mapping) or rule.get("risk_level") not in RISK_LEVELS or not isinstance(rule.get("risk_flag"), str) or not isinstance(rule.get("reason_code"), str) or rule.get("reason_code") not in REASON_CODES:
            return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code="RISK_UNCLASSIFIED", source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)
        level = str(rule["risk_level"])
        levels.append(level)
        flags.append(str(rule["risk_flag"]))
        reason = str(rule["reason_code"])
        if reason not in {"RISK_UNCLASSIFIED", "RISK_SCOPE_AMBIGUOUS"}:
            reasons.append(reason)
        gates = rule.get("additional_authority_gates", [])
        if not isinstance(gates, list) or not all(gate in {"G5_DEPLOY", "G6_PRODUCTION_DATA"} for gate in gates):
            return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code="RISK_UNCLASSIFIED", source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)
        additional_gates.update(gates)
        contributing.append({"signal": signal, "risk_level": level, "reason_code": reason, "risk_flag": str(rule["risk_flag"]), "source": "request_intake"})

    risk_level = max(levels, key=lambda level: RISK_ORDER[level])
    declared_level = request_intake.get("declared_risk_level")
    if declared_level is not None and declared_level != risk_level:
        return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code="RISK_SCOPE_AMBIGUOUS", source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)
    gate = policy["required_gate_by_level"].get(risk_level)
    if gate not in {"G2_AUTOMATIC_BOUNDED", "G2_HUMAN_DIRECTION"}:
        return _blocked(task_id=task_id, repository=repository, base_sha=base_sha, reason_code="RISK_UNCLASSIFIED", source_bindings=bindings, policy_provenance=provenance, classified_at=classified_at)

    reason_code = f"RISK_CLASSIFIED_{risk_level}"
    reason_codes = sorted(set(reasons + [reason_code]))
    approvals = ["Bounded G2 execution envelope is required before any write."]
    if gate == "G2_HUMAN_DIRECTION":
        approvals.append("Explicit human direction is required before downstream execution.")
    for authority_gate in sorted(additional_gates):
        approvals.append(f"Separate {authority_gate} approval remains required; classification grants no authority.")
    return _artifact(
        task_id=task_id, repository=repository, base_sha=base_sha,
        outcome="ACCEPTED", risk_level=risk_level, risk_flags=flags,
        required_gate=gate, additional_authority_gates=sorted(additional_gates),
        approval_requirements=approvals, reason_code=reason_code,
        reason_codes=reason_codes, source_bindings=bindings,
        policy_provenance=provenance, contributing_signals=contributing,
        remediation=None, next_allowed_nodes=["intake_context.files-read-scope", "intake_context.files-write-scope"],
        classified_at=classified_at,
    )


if __name__ == "__main__":
    import sys
    print(json.dumps(render_risk_classification(**json.load(sys.stdin)), indent=2, ensure_ascii=False))
