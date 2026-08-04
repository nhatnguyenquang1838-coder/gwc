"""Deterministic, replay-safe GWC gate-state resolution for SCRUM-184.

This pure resolver consumes canonical scope, evidence and transition artifacts.
Task trackers are audit projections only; no authority or side effect is created.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from tools.node_architect.evidence_artifact_map import _GATE_REQUIREMENTS
from tools.node_architect.scope_hash_calculation import (
    BINDING_KEYS,
    CANONICAL_ACTIONS,
    calculate_gate_scope_identity,
)

GATE_ORDER = (
    "G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR",
    "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA",
)
GATE_STATUSES = {"READY", "RUNNING", "PASS", "BLOCKED", "FAILED", "NOT_APPLICABLE"}
CANONICAL_CLASSES = {"CANONICAL_AUTHORITY", "CANONICAL_GATE_EVIDENCE", "DELIVERY_EVIDENCE"}
PROJECTION_SOURCES = {"jira_comment", "slack_message", "notion_page", "dashboard", "chat_message"}
READ_ONLY_ACTIONS = {
    "read_repository", "inspect_connector", "inspect_task", "materialize_g1_artifacts",
    "run_read_only_validation", "run_independent_review", "verify_post_merge_ci",
    "readback_branch_pr_diff_ci",
}
PRODUCTION_ACTIONS = {
    "production_data_read", "production_data_write", "production_config_change",
    "credential_rotation", "migration",
}
EVIDENCE_BLOCKERS = {
    "EVIDENCE_INPUT_INVALID", "EVIDENCE_BINDING_MISMATCH", "EVIDENCE_CONFLICT",
    "EVIDENCE_PROJECTION_ONLY", "EVIDENCE_STALE", "EVIDENCE_REQUIRED_MISSING",
    "EVIDENCE_OBSERVABILITY_INCOMPLETE", "EVIDENCE_CI_BINDING_MISMATCH",
}
EVIDENCE_REASONS = EVIDENCE_BLOCKERS | {"EVIDENCE_MAP_READY", "EVIDENCE_G6_NOT_APPLICABLE"}
REASON_PRECEDENCE = (
    "GATE_STATE_INPUT_INVALID", "GATE_STATE_REPLAY_CONFLICT",
    "GATE_STATE_BINDING_MISMATCH", "GATE_STATE_EVIDENCE_CONFLICT",
    "GATE_STATE_GATE_FAILED", "GATE_STATE_DRIFT", "GATE_STATE_EVIDENCE_STALE",
    "GATE_STATE_REQUIRED_EVIDENCE_MISSING",
    "GATE_STATE_LATER_GATE_INHERITANCE_REJECTED", "GATE_STATE_RESOLVED",
    "GATE_STATE_PROJECTION_MISMATCH", "GATE_STATE_G6_NOT_APPLICABLE",
)
AUTHORITY_FLAGS = (
    "authority_granted", "write_authority_granted", "pr_authority_granted",
    "merge_authority_granted", "deployment_authority_granted", "production_authority_granted",
)

TRANSITION_RULES = {
    ("G0_READY", "draft", "SUBMIT", "ready"),
    ("EXECUTION_STARTED", "ready", "RUN_AGENT", "agent_running"),
    ("AGENT_WORK_SUCCEEDED", "agent_running", "CALLBACK_SUCCESS", "pending_review"),
    ("AGENT_WORK_FAILED", "agent_running", "CALLBACK_FAILED", "failed"),
    ("PLAN_APPROVED", "pending_review", "APPROVE_PLAN", "pending_approval"),
    ("REVISION_REQUIRED", "pending_review", "REVISE", "ready"),
    ("WRITE_APPROVED", "pending_approval", "APPROVE_WRITE", "write_running"),
    ("WRITE_REJECTED", "pending_approval", "REJECT_WRITE", "pending_review"),
    ("DRAFT_PR_CREATED", "write_running", "PR_CREATED", "validation_running"),
    ("VALIDATION_PASSED", "validation_running", "VALIDATION_PASSED", "review_pending"),
    ("PR_READY_FOR_REVIEW", "review_pending", "MARK_READY_FOR_REVIEW", "merge_pending"),
    ("VALIDATION_FAILED", "validation_running", "VALIDATION_FAILED", "pending_review"),
    ("MERGE_APPROVED", "merge_pending", "APPROVE_MERGE", "merge_running"),
    ("MERGE_REJECTED", "merge_pending", "REJECT_MERGE", "review_pending"),
    ("MERGED", "merge_running", "MERGE_COMPLETED", "verification_running"),
    ("G5_STATUS_VERIFIED", "verification_running", "STATUS_VERIFIED", "completed"),
    ("G5_MANUAL_ACTION_REQUIRED", "verification_running", "REQUEST_DEPLOYMENT", "deployment_pending"),
    ("DEPLOY_APPROVED", "deployment_pending", "APPROVE_DEPLOY", "deployment_running"),
    ("DEPLOY_REJECTED", "deployment_pending", "REJECT_DEPLOY", "verification_running"),
    ("DEPLOY_COMPLETED", "deployment_running", "DEPLOYMENT_COMPLETED", "verification_running"),
    ("G6_REQUIRED", "verification_running", "REQUEST_PRODUCTION_OPERATION", "production_pending"),
    ("PRODUCTION_APPROVED", "production_pending", "APPROVE_PRODUCTION_OPERATION", "production_running"),
    ("PRODUCTION_REJECTED", "production_pending", "REJECT_PRODUCTION_OPERATION", "verification_running"),
    ("PRODUCTION_COMPLETED", "production_running", "PRODUCTION_OPERATION_COMPLETED", "completed"),
    ("BLOCKED", "ready", "BLOCK", "blocked"),
    ("UNBLOCKED", "blocked", "UNBLOCK", "ready"),
}
TRANSITION_EVIDENCE = {
    "task_id", "from_state", "transition", "expected_state",
    "observed_state", "event_id_or_idempotency_key",
}
SCOPE_FIELDS = {
    "schema_version", "artifact_type", "task_id", "repository", "base_ref", "base_sha",
    "working_branch", "head_sha", "risk_class", "authorized_paths", "authorized_actions",
    "excluded_actions", "additional_bindings", "outcome", "reason_codes", "calculated_at",
    "scope_hash", "approval_request_digest", "authority_granted",
}
MAP_FIELDS = {
    "schema_version", "artifact_type", "task_id", "repository", "base_sha", "head_sha",
    "policy_revision", "mapped_at", "outcome", "reason_codes", "entries", "requirements",
    "missing_required", "stale_required", "projection_only", "map_digest", "authority_granted",
}
ENTRY_FIELDS = {
    "evidence_key", "gate", "artifact_role", "artifact_type", "classification", "required",
    "source_type", "target", "ref", "revision", "digest", "binding_status",
    "freshness_status", "materialization_status", "source_of_truth", "reason_codes",
}
ENTRY_REQUIRED = {
    "evidence_key", "gate", "artifact_role", "artifact_type", "classification", "required",
    "source_type", "target", "binding_status", "freshness_status", "materialization_status",
    "source_of_truth", "reason_codes",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
OBSERVATION_KEYS = {
    "observed_at", "mapped_at", "calculated_at", "generated_at", "updated_at",
    "created_at", "decision_digest", "resolution_digest", "map_digest",
}


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _strip_observations(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _strip_observations(v) for k, v in value.items() if str(k) not in OBSERVATION_KEYS}
    if isinstance(value, list):
        return [_strip_observations(v) for v in value]
    return value


def _strings(value: Any, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list) and (not nonempty or bool(value))
        and all(isinstance(v, str) and v for v in value) and len(value) == len(set(value))
    )


def _sorted_unique(value: Any) -> list[str]:
    return sorted({v for v in value if isinstance(v, str) and v}) if isinstance(value, list) else []


def _sort_reasons(codes: Sequence[str]) -> list[str]:
    return sorted(set(codes), key=lambda c: (REASON_PRECEDENCE.index(c) if c in REASON_PRECEDENCE else 99, c))


def _valid_scope(scope: Mapping[str, Any]) -> bool:
    required = {
        "schema_version", "artifact_type", "task_id", "repository", "base_ref", "base_sha",
        "risk_class", "authorized_paths", "authorized_actions", "excluded_actions",
        "outcome", "scope_hash", "authority_granted",
    }
    if set(scope) - SCOPE_FIELDS or not required.issubset(scope): return False
    if scope.get("schema_version") != "1.0" or scope.get("artifact_type") != "gate-scope-identity": return False
    if scope.get("outcome") != "READY" or scope.get("authority_granted") is not False: return False
    if not is_instance(scope.get("task_id"), str) or not scope["task_id"]: return False
    if not isinstance(scope.get("repository"), str) or not REPO_RE.match(scope["repository"]): return False
    if not isinstance(scope.get("base_ref"), str) or not scope["base_ref"]: return False
    if not isinstance(scope.get("base_sha"), str) or not SHA_RE.match(scope["base_sha"]): return False
    if scope.get("head_sha") is not None and (not isinstance(scope["head_sha"], str) or not SHA_RE.match(scope["head_sha"])): return False
    if scope.get("risk_class") not in {"R0", "R1", "R2", "R3"}: return False
    for key in ("authorized_paths", "authorized_actions", "excluded_actions"):
        if not _strings(scope.get(key), nonempty=key != "excluded_actions"): return False
    actions = set(scope["authorized_actions"])
    if not actions.issubset(CANONICAL_ACTIONS): return False
    if actions & set(scope["excluded_actions"]): return False
    if scope["authorized_paths"] == [] and not actions.issubset(READ_ONLY_ACTIONS): return False
    bindings = scope.get("additional_bindings", [])
    if not isinstance(bindings, list): return False
    for binding in bindings:
        if not isinstance(binding, Mapping) or set(binding) != {"key", "value"}:
            return False
        if binding.get("key") not in BINDING_KEYS or not isinstance(binding.get("value"), str) or not binding["value"]:
            return False
    if not isinstance(scope.get("scope_hash"), str) or not DIGEST_RE.match(scope["scope_hash"]): return False
    rebuilt = calculate_gate_scope_identity(
        task_id=scope["task_id"], repository=scope["repository"], base_ref=scope["base_ref"],
        base_sha=scope["base_sha"], working_branch=scope.get("working_branch"), head_sha=scope.get("head_sha"),
        risk_class=scope["risk_class"], authorized_paths=scope["authorized_paths"],
        authorized_actions=scope["authorized_actions"], excluded_actions=scope["excluded_actions"],
        additional_bindings=bindings, calculated_at=scope.get("calculated_at"),
    )
    return rebuilt.get("outcome") == "READY" and rebuilt.get("scope_hash") == scope["scope_hash"]


def _valid_map(model: Mapping[str, Any], task_id: str) -> bool:
    required = {
        "schema_version", "artifact_type", "task_id", "repository", "base_sha", "policy_revision",
        "outcome", "entries", "requirements", "missing_required", "stale_required",
        "projection_only", "map_digest", "authority_granted",
    }
    if set(model) - MAP_FIELDS or not required.issubset(model): return False
    if model.get("schema_version") != "1.0" or model.get("artifact_type") != "gate-evidence-artifact-map": return False
    if model.get("outcome") != "READY" or model.get("authority_granted") is not False: return False
    if not all(isinstance(model.get(k), str) and model.get(k) for k in ("task_id", "repository", "base_sha", "policy_revision")): return False
    if not SHA_RE.match(model["base_sha"]) or not REPO_RE.match(model["repository"]): return False
    if model.get("head_sha") is not None and (not isinstance(model["head_sha"], str) or not SHA_RE.match(model["head_sha"])): return False
    if not _strings(model.get("reason_codes", [])) or not set(model.get("reason_codes", [])).issubset(EVIDENCE_REASONS): return False
    if not all(_strings(model.get(k), nonempty=False) for k in ("missing_required", "stale_required", "projection_only")): return False
    requirements = model.get("requirements")
    entries = model.get("entries")
    if not isinstance(requirements, list) or not isinstance(entries, list): return False
    expected_requirements = []
    for gate in GATE_ORDER:
        for role, target, classification, ctx  in _GATE_REQUIREMENTS[gate]:
            if ctx and task_id:
                target = target.replace("{"task_id"}", task_id)
            expected_requirements.append({"gate": gate, "artifact_role": role, "target": target, "required": gate != "G6_PRODUCTION_DATA"})
    if requirements != expected_requirements: return False
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) - ENTRY_FIELDS or not ENTRY_REQUIRED.issubset(entry):
            return False
        if entry.get("gate") not in GATE_ORDER or entry.get("classification") not in CANONICAL_CLASSES | {"AUDIT_PROJECTION", "RESUME_HINT"}:
            return False
        if not isinstance(entry.get("required"), bool) or not isinstance(entry.get("source_of_truth"), bool): return False
        if entry.get("inding_status") not in {"BOUND", "MISMATCHED", "UNOBSERVED", "NOT_APPLICABLE"}: return False
        if entry.get("freshness_status") not in {"FRESH", "STALE", "UNOBSERVED"}: return False
        if entry.get("materialization_status") not in {"MATERIALIZED", "MISSING", "UNOBSERVED"}: return False
        if not _strings(entry.get("reason_codes", [])): return False
        for key in ("evidence_key", "artifact_role", "artifact_type", "source_type"):
            if not isinstance(entry.get(key), str) or not entry[key]: return False
        target = entry.get("target")
        if target is not None and (not isinstance(target, str) or not target): return False
        for key in ("ref", "revision", "digest"):
            if entry.get(key) is not None and not isinstance(entry[key], str): return False
        key = (entry["gate"], entry["evidence_key"])
        if key in seen: return False
        seen.add(key)
    semantic = {
        "task_id": model["task_id"], "repository": model["repository"], "base_sha": model["base_sha"],
        "policy_revision": model["policy_revision"], "requirements": requirements,
        "entries": sorted(entries, key=lambda e: (str(e.get("gate")), str(e.get("evidence_key")))),
        "missing_required": model["missing_required"], "stale_required": model["stale_required"],
        "projection_only": model["projection_only"],
    }
    return isinstance(model.get("map_digest"), str) and model["map_digest"] == _digest(semantic)


def _valid_transition(model: Mapping[str, Any]) -> bool:
    required = {"contract_version", "authority", "rules", "terminal_states", "verification"}
    if not required.issubset(model): return False
    if model.get("contract_version") != "1.0.1": return False
    authority = model.get("authority")
    if not isinstance(authority, Mapping) or not all(isinstance(authority.get(k), str) and authority[k] for k in ("state_machine", "discovery_tool")): return False
    rules = model.get("rules")
    if not isinstance(rules, list): return False
    actual = set()
    for rule in rules:
        if not isinstance(rule, Mapping) or not all(isinstance(rule.get(k), str) and rule[k] for k in ("outcome", "from_state", "transition", "expected_state")):
            return False
        actual.add((rule["outcome"], rule["from_state"], rule["transition"], rule["expected_state"]))
    if actual != TRANSITION_RULES: return False
    if set(model.get("terminal_states", [])) != {"completed", "cancelled"}: return False
    verification = model.get("verification")
    return (
        isinstance(verification, Mapping) and verification.get("required") is True
        and verification.get("failure_behavior") == "fail_gate" and set(verification.get("evidence", [])) == TRANSITION_EVIDENCE
        and verification.get("readback_required") is True
    )


def _binding_errors(task_id: str, repository: str, scope: Mapping[str, Any], model: Mapping[str, Any], prior: Mapping[str, Any] | None) -> list[str]:
    errors: list[str] = []
    for item, name in ((scope, "scope"), (model, "evidence"), (prior, "prior"):
        if item and (item.get("task_id") != task_id or item.get("repository") != repository):
            errors.append(f"{name}-binding")
    if model.get("base_sha") != scope.get("base_sha"): errors.append("base-binding")
    return errors


def _detail(gate: str, entry: Mapping[str, Any] | None) -> tuple[str, list[str]]:
    if entry is None: return "MISSING", ["MISSING"]
    reasons = _sorted_unique(entry.get("reason_codes", []))
    if set(reasons) & EVIDENCE_BLOCKERS: return "FAILED", reasons
    if entry.get("materialization_status") in {"MISSING", "UNOBSERVED"}: return "MISSING", reasons
    if entry.get("freshness_status") in {"STALE", "UNOBSERVED"}: return "STALE", reasons
    if entry.get("binding_status") not in {"BOUND", "NOT_APPLICABLE"}: return "CONFLICT", reasons
    if entry.get("classification") not in CANONICAL_CLASSES or entry.get("source_of_truth") is Not True:
        return "MISSING", reasons
    return "PASS", reasons


def _analyze(model: Mapping[str, Any], production: bool) -> dict[str, Any]:
    requirements = [r for r in model["requirements"] if r.get("required", False) or (r.get("gate") == "G6_PRODUCTION_DATA" and production']
    entries = {e.get("gate"): {} for e in model["entries"]}
    for entry in model["entries"]:
        entries.setdefault(entry.get("gate"), {})[entry.get("evidence_key")] = entry
    evaluations, canonical, missing, stale, conflicts = [], [], [], [], []
    last_passed, later = None, False
    first = {"gate": None, "status": "PASS", "failed": False}
    for gate in GATE_ORDER:
        if gate == "G6_PRODUCTION_DATA" and not production:
            evaluations.append({"gate": gate, "status": "NOT_APPLICABLE", "reason_codes": ["GATE_STATE_G6_NOT_APPLICABLE"]})
            continue
        gate_reqs = [r for r in requirements if r.get("gate") == gate]
        results, reasons = [], []
        for req in gate_reqs:
            target = req.get("target")
            entry = entries.get(gate, {}).get(target)
            state, codes = _detail(gate, entry)
            results.append(state); reasons.extend(codes)
            if state == "MISSING": missing.append(target)
            elif state == "STALE": stale.append(target)
            elif state == "CONFLICT": conflicts.append(target)
            elif state == "FAILED": conflicts.append(target)
            if entry and entry.get("classification") in CANONICAL_CLASSES and entry.get("source_of_truth" is True:
                canonical.append(entry.get("ref") or target)
        if not gate_reqs and gate != "G5_DEPLOY": results = ["MISSING"]; missing.append(f"{gate}:requirements")
        gate_status = "FAILED" if "FAILED" in results else "BONFLICT" if "CONFLICT" in results else "STALE" if "STALE" in results else "BLOCKED" if "MISSING" in results else "PASS"
        evaluations.append({"gate": gate, "status": gate_status, "reason_codes": _sorted_unique(reasons)})
        if first["gate"] is None and gate_status != "PASS":
            first = {"gate": gate, "status": "FAILED" if gate_status in {"FAILED", "CONFLICT"} else "BLOCKED", "failed": gate_status == "FAILED"}
        elif first["gate"] is None and gate_status == "PASS": last_passed = gate
        elif first["gate"] is not None and gate_status == "PASS": later = True
    return {
        "evaluations": evaluations, "canonical": _sorted_unique(canonical), "missing": _sorted_unique(missing),
        "stale": _sorted_unique(stale), "conflicts": _sorted_unique(conflicts), "first": first,
        "last_passed": last_passed, "later": later,
    }


def _drift(base_sha: str, scope: Mapping[str, Any], model: Mapping[str, Any]) -> list[str]:
    reasons = []
    if scope.get("base_sha") != base_sha: reasons.append("BASE_SHA_DRIFT")
    if model.get("base_sha") != base_sha: reasons.append("EVIDENCE_BASE_SHA_DRIFT")
    heads, scope_head = {e.get("revision") for e in model["entries"] if isinstance(e.get("revision"), str) and SHA_RE.match(e.get("revision"))}, scope.get("head_sha")
    if len(heads) > 1: reasons.append("HEAD_SHA_DRIFT")
    if scope_head and heads and scope_head not in heads: reasons.append("HEAD_SHA_DRIFT")
    return _sorted_unique(reasons)


def _projection_warnings(projection: Mapping[str, Any] | None, task_id: str, repository: str, gate: str, status: str, transition: Mapping[str, Any]) -> list[str]:
    if projection is None: return []
    if not isinstance(projection, Mapping): return ["PROJECTION_INVALID"]
    warnings = []
    if projection.get("task_id") not in {None, task_id}: warnings.append("TASK_ID_MISMATCH")
    if projection.get("repository") not in {None, repository}: warnings.append("REPOSITORY_MISMATCH")
    if projection.get("current_gate") not in {None, gate}: warnings.append("CURRENT_GATE_MISMATCH")
    if projection.get("status" not in {None, status}: warnings.append("STATUS_MISMATCH")
    states = {"completed", "cancelled"} | {r.get("from_state") for r in transition["rules"]} | {r.get("expected_state") for r in transition["rules"]}
    if projection.get("state") not in {None} | states: warnings.append("PROJECTION_STATE_UNKNOWN")
    if projection.get("state") == "cancelled": warnings.append("CANCELLED_PROJECTION_WITHOUT_CANONICAL_EVIDENCE")
    return _sorted_unique(warnings)


def _next_action(reasons: Sequence[str], status: str, next_gate: str | None) -> str:
    for code, action in (
        ("GATE_STATE_INPUT_INVALID", "FIX_INPUT"),
        ("GATE_STATE_REPLAY_CONFLICT", "STOP_AND_RECONCILE_REPLAY"),
        ("GATE_STATE_BINDING_MISMATCH", "REBUILD_BINDINGS"),
        ("GATE_STATE_EVIDENCE_CONFLICT", "RESOLVE_EVIDENCE_CONFLICT"),
        ("GATE_STATE_GATE_FAILED", "RECOVER_FAILED_GATE"),
        ("GATE_STATE_DRIFT", "REVALIDATE_OR_REAPPROVE"),
        ("GATE_STATE_EVIDENCE_STALE", "REFRESH_EVIDENCE"),
        ("GATE_STATE_REQUIRED_EVIDENCE_MISSING", "MATERIALIZE_REQUIRED_EVIDENCE"),
    ):
        if code in reasons: return action
    if status == "RUNNING": return "WAIT_FOR_GATE_COMPLETION"
    return "COMPLETE" if next_gate is None else "ADVANCE_GATE"


def _base(task_id: str, repository: str, base_sha: str, scope_hash: str | None, event_key: str, observed_at: str | None, digest: str) -> dict[str, Any]:
    result = {
        "schema_version": "1.0", "artifact_type": "gate-state-resolution",
        "task_id": task_id, "repository": repository, "current_base_sha": base_sha,
        "scope_hash": scope_hash, "head_sha": None, "current_gate": "G0_CONTEXT",
        "gate_status": "BLOCKED", "last_passed_gate": None, "next_gate": "G0_CONTEXT",
        "next_action_class": "FIX_INPUT", "canonical_evidence_refs": [],
        "projection_warnings": [], "missing_evidence": [], "stale_evidence": [],
        "conflicting_evidence": [], "drift_decision": {"status": "NO_DRIFT", "reason_codes": []},
        "primary_reason_code": "GATE_STATE_INPUT_INVALID", "reason_codes": ["GATE_STATE_INPUT_INVALID"],
        "event_id_or_idempotency_key": event_key, "replay_status": "FIRST_SEEN",
        "resolution_digest": digest, "observed_at": observed_at, "gate_evaluations": [],
    }
    result.update({flag: False for flag in AUTHORITY_FLAGS})
    return result


def resolve_gate_state(
    *, task_id: str, repository: str, current_base_sha: str,
    scope_identity: dict[str, object], evidence_map: dict[str, object],
    transition_map: dict[str, object], task_projection: dict[str, object] | None,
    event_id_or_idempotency_key: str, prior_resolution: dict[str, object] | None = None,
    observed_at: str | None = None,
) -> dict[str, object]:
    """Resolve the current GWC gate without granting or executing authority."""
    semantic = {
        "task_id": task_id, "repository": repository, "current_base_sha": current_base_sha,
        "scope_identity": _strip_observations(scope_identity),
        "evidence_map": _strip_observations(evidence_map),
        "transition_map": _strip_observations(transition_map),
        "task_projection": _strip_observations(task_projection),
        "event_id_or_idempotency_key": event_id_or_idempotency_key,
    }
    digest = _digest(semantic)
    scope_hash = scope_identity.get("scope_hash") if isinstance(scope_identity, Mapping) else None
    output = _base(
        task_id if isinstance(task_id, str) else "", repository if isinstance(repository, str) else "",
        current_base_sha if isinstance(current_base_sha, str) else "",
        scope_hash if isinstance(scope_hash, str) else None,
        event_id_or_idempotency_key if isinstance(event_id_or_idempotency_key, str) else "",
        observed_at, digest,
    )
    invalid = (
        not isinstance(task_id, str) or not task_id
        or not isinstance(repository, str) or not REPO_RE.match(repository)
        or not isinstance(current_base_sha, str) or not SHA_RE.match(current_base_sha)
        or not isinstance(scope_identity, Mapping) or not _valid_scope(scope_identity)
        or not isinstance(evidence_map, Mapping) or not _valid_map(evidence_map, task_id)
        or not isinstance(transition_map, Mapping) or not _valid_transition(transition_map)
        or not isinstance(event_id_or_idempotency_key, str) or not event_id_or_idempotency_key
        or prior_resolution is not None and not isinstance(prior_resolution, Mapping)
        or isinstance(evidence_map, Mapping) and "EVIDENCE_INPUT_INVALID" in evidence_map.get("reason_codes", [])
    )
    if invalid:
        return output

    bindings = _binding_errors(task_id, repository, scope_identity, evidence_map, prior_resolution)
    production = bool(set(scope_identity["authorized_actions"]) & PRODUCTION_ACTIONS)
    analysis = _analyze(evidence_map, production)
    output.update({
        "gate_evaluations": analysis["evaluations"], "canonical_evidence_refs": analysis["canonical"],
        "missing_evidence": analysis["missing"], "stale_evidence": analysis["stale"],
        "conflicting_evidence": analysis["conflicts"], "last_passed_gate": analysis["last_passed"],
        "head_sha": scope_identity.get("head_sha"),
    })
    first = analysis["first"]
    if first["gate"] is None:
        current_gate, status, next_gate = "G6_PRODUCTION_DATA", "PASS" if production else "NOT_APPLICABLE", None
        if production: output["last_passed_gate"] = current_gate
    else:
        current_gate, status, next_gate = first["gate"], first["status"], first["gate"]

    same_key = bool(prior_resolution and prior_resolution.get("event_id_or_idempotency_key") == event_id_or_idempotency_key)
    replay_conflict = bool(same_key and prior_resolution.get("resolution_digest") != digest)
    replay_idempotent = bool(same_key and prior_resolution.get("resolution_digest") == digest)
    drift = _drift(current_base_sha, scope_identity, evidence_map)
    reasons = []
    if replay_conflict: reasons.append("GATE_STATE_REPLAY_CONFLICT")
    if bindings: reasons.append("GATE_STATE_BINDING_MISMATCH")
    if analysis["conflicts"]: reasons.append("GATE_STATE_EVIDENCE_CONFLICT")
    if first["failed"]: reasons.append("GATE_STATE_GATE_FAILED")
    if drift: reasons.append("GATE_STATE_DRIFT")
    if analysis["stale"]: reasons.append("GATE_STATE_EVIDENCE_STALE")
    if analysis["missing"]: reasons.append("GATE_STATE_REQUIRED_EVIDENCE_MISSING")
    if analysis["later"]: reasons.append("GATE_STATE_LATER_GATE_INHERITANCE_REJECTED")
    if not reasons:
        reasons = ["GATE_STATE_RESOLVED"] + ([] if production else ["GATE_STATE_G6_NOT_APPLICABLE"])

    blocking = set(reasons) & {
        "GATE_STATE_REPLAY_CONFLICT", "GATE_STATE_BINDING_MISMATCH", "GATE_STATE_EVIDENCE_CONFLICT",
        "GATE_STATE_GATE_FAILED", "GATE_STATE_DRIFT", "GATE_STATE_EVIDENCE_STALE",
        "GATE_STATE_REQUIRED_EVIDENCE_MISSING",
    }
    if blocking:
        status = "FAILED" if first["failed"] else "BLOCKED"
        if bindings:
            current_gate, output["last_passed_gate"] = "G0_CONTEXT", None
        elif drift:
            if set(drift) & {"BASE_SHA_DRIFT", "EVIDENCE_BASE_SHA_DRIFT"}:
                current_gate, output["last_passed_gate"] = "G0_CONTEXT", None
            else:
                current_gate, output["last_passed_gate"] = "G2_EXECUTION", "G1_ALIGNMENT"
        elif current_gate == "G6_PRODUCTION_DATA" and output["last_passed_gate"]:
            current_gate = GATE_ORDER[min(GATE_ORDER.index(output["last_passed_gate"]) + 1, len(GATE_ORDER) - 1)]
        next_gate = current_gate

    warnings = _projection_warnings(task_projection, task_id, repository, current_gate, status, transition_map)
    if warnings: reasons.append("GATE_STATE_PROJECTION_MISMATCH")
    reasons = _sort_reasons(reasons)
    output.update({
        "current_gate": current_gate, "gate_status": status if status in GATE_STATUSES else "BLOCKED",
        "next_gate": next_gate, "projection_warnings": warnings,
        "drift_decision": {"status": "REAPPROVE" if drift else "NO_DRIFT", "reason_codes": drift},
        "primary_reason_code": reasons[0], "reason_codes": reasons,
        "replay_status": "REPLAY_CONFLICT" if replay_conflict else "IDEMPOTENT_REPLAY" if replay_idempotent else "FIRST_SEEN",
    })
    output["next_action_class"] = _next_action(reasons, output["gate_status"], next_gate)
    return output
