"""Compile approved research into an execution task and reconcile tracking projections."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
ALLOWED_G2 = {
    "create_guarded_branch_or_worktree",
    "modify_approved_files",
    "run_sandboxed_validation",
    "stage",
    "create_commit",
    "push_working_branch",
}
FORBIDDEN_CHILD_ACTIONS = {"merge", "auto_merge", "deploy", "release", "runtime_reload", "production_data_read", "production_data_write", "production_config_change", "credential_rotation", "migration"}
ALLOWED_G3 = {"open_or_update_draft_pr", "monitor_exact_head_ci", "repair_within_approved_scope", "run_independent_read_only_review", "mark_pr_ready_for_review"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode()).hexdigest()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must contain timezone")
    return parsed.astimezone(timezone.utc)


def _scope_digest(scope: Mapping[str, Any]) -> str:
    semantic = {k: v for k, v in scope.items() if k != "scope_digest"}
    return _digest(semantic)


def approval_scope_hash(approval: Mapping[str, Any]) -> str:
    """Canonical hash of every field that can change delegated execution authority."""
    payload = {
        "approval_id": approval.get("approval_id"),
        "issued_at": approval.get("issued_at"),
        "expires_at": approval.get("expires_at"),
        "authority_revision": approval.get("authority_revision"),
        "research_ref": approval.get("research_ref"),
        "research_digest": approval.get("research_digest"),
        "repository": approval.get("repository"),
        "base_ref": approval.get("base_ref"),
        "base_sha": approval.get("base_sha"),
        "active_lane": approval.get("active_lane"),
        "risk_ceiling": approval.get("risk_ceiling"),
        "approved_scope": approval.get("approved_scope"),
        "delegated_g2_actions": approval.get("delegated_g2_actions"),
        "delegated_g3_actions": approval.get("delegated_g3_actions"),
    }
    return _digest(payload)


def validate_research_approval(research: Mapping[str, Any], approval: Mapping[str, Any], *, now: datetime | None = None) -> tuple[bool, str]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if approval.get("g4_g5_g6_authority_granted") is not False:
        return False, "RESEARCH_APPROVAL_AUTHORITY_ESCALATION"
    if not isinstance(approval.get("human_approval"), Mapping) or approval["human_approval"].get("trusted_readback") is not True:
        return False, "RESEARCH_APPROVAL_UNTRUSTED"
    for field in ("research_ref", "research_digest", "repository"):
        if approval.get(field) != research.get(field):
            return False, "RESEARCH_DIGEST_DRIFT" if field == "research_digest" else "RESEARCH_SCOPE_DRIFT"
    if approval.get("active_lane") != research.get("lane"):
        return False, "RESEARCH_SCOPE_DRIFT"
    try:
        if _parse_utc(str(approval.get("expires_at", ""))) <= now:
            return False, "RESEARCH_APPROVAL_EXPIRED"
    except (TypeError, ValueError):
        return False, "RESEARCH_APPROVAL_INVALID"
    scope = approval.get("approved_scope")
    scopes = research.get("scopes")
    if not isinstance(scope, Mapping) or not isinstance(scopes, Mapping):
        return False, "RESEARCH_SCOPE_DRIFT"
    observed = scopes.get(scope.get("scope_id"))
    if not isinstance(observed, Mapping):
        return False, "RESEARCH_SCOPE_DRIFT"
    if scope.get("scope_digest") != _scope_digest(observed) or scope.get("scope_digest") != _scope_digest(scope):
        return False, "RESEARCH_SCOPE_DRIFT"

    ceiling = approval.get("risk_ceiling")
    risk = scope.get("risk_class")
    if ceiling not in RISK_ORDER or risk not in RISK_ORDER:
        return False, "RESEARCH_RISK_CEILING_INVALID"
    if RISK_ORDER[str(risk)] > RISK_ORDER[str(ceiling)]:
        return False, "CHILD_G2_RISK_EXCEEDS_PARENT_CEILING"

    g2 = approval.get("delegated_g2_actions", [])
    g3 = approval.get("delegated_g3_actions", [])
    if not isinstance(g2, Sequence) or isinstance(g2, (str, bytes)) or not g2:
        return False, "CHILD_G2_SCOPE_EXPANSION_REJECTED"
    if not isinstance(g3, Sequence) or isinstance(g3, (str, bytes)):
        return False, "CHILD_G3_SCOPE_EXPANSION_REJECTED"
    if not set(g2) <= ALLOWED_G2:
        return False, "CHILD_G2_ACTION_FORBIDDEN"
    if set(g2) & FORBIDDEN_CHILD_ACTIONS or set(g3) & FORBIDDEN_CHILD_ACTIONS or not set(g3) <= ALLOWED_G3:
        return False, "RESEARCH_APPROVAL_AUTHORITY_ESCALATION"

    expected_scope_hash = approval_scope_hash(approval)
    if approval.get("scope_hash") != expected_scope_hash:
        return False, "RESEARCH_APPROVAL_SCOPE_HASH_MISMATCH"
    return True, "RESEARCH_APPROVAL_VALID"


def _child_authority(approval: Mapping[str, Any], materialization_key: str) -> dict[str, Any]:
    scope = approval["approved_scope"]
    common = {
        "source": "human_research_execution_approval", "parent_approval_id": approval["approval_id"],
        "parent_scope_hash": approval["scope_hash"], "materialization_key": materialization_key,
        "repository": approval["repository"], "base_ref": approval["base_ref"], "base_sha": approval["base_sha"],
        "risk_class": scope["risk_class"], "risk_ceiling": approval["risk_ceiling"],
        "expires_at": approval["expires_at"], "g4_g5_g6_authority_granted": False,
    }
    g2 = {**common, "gate": "G2_EXECUTION", "authorized_paths": list(scope["authorized_paths"]), "authorized_actions": list(approval["delegated_g2_actions"]), "authority_granted": True}
    g3_actions = list(approval.get("delegated_g3_actions", []))
    g3 = ({**common, "gate": "G3_PR", "authorized_actions": g3_actions, "authority_granted": True} if g3_actions else None)
    return {"g2": g2, "g3": g3}


def compile_execution_task_spec(research: Mapping[str, Any], approval: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    valid, reason = validate_research_approval(research, approval, now=now)
    if not valid:
        raise ValueError(reason)
    scope = approval["approved_scope"]
    identity = {
        "research_ref": approval["research_ref"], "research_digest": approval["research_digest"],
        "approved_scope_digest": scope["scope_digest"], "repository": approval["repository"],
        "authority_revision": approval["authority_revision"],
    }
    materialization_key = _digest(identity)
    value: dict[str, Any] = {
        "schema_version": "1.0", "artifact_type": "execution-task-spec", "materialization_key": materialization_key,
        "origin_research_ref": approval["research_ref"], "approved_research_digest": approval["research_digest"],
        "approved_scope_id": scope["scope_id"], "approved_scope_digest": scope["scope_digest"],
        "repository": approval["repository"], "base_ref": approval["base_ref"], "base_sha": approval["base_sha"],
        "active_lane": approval["active_lane"], "objective": scope["objective"],
        "implementation_guidance": list(scope.get("implementation_guidance", [])), "acceptance_criteria": list(scope["acceptance_criteria"]),
        "dependencies": list(scope.get("dependencies", [])), "risk_class": scope["risk_class"],
        "authorized_paths": list(scope["authorized_paths"]), "excluded_actions": list(scope.get("excluded_actions", [])),
        "delegated_g2_actions": list(approval["delegated_g2_actions"]), "delegated_g3_actions": list(approval.get("delegated_g3_actions", [])),
        "projection_refs": {"github": None, "jira": None}, "child_authority": _child_authority(approval, materialization_key),
        "g4_g5_g6_authority_granted": False,
    }
    value["spec_digest"] = _digest(value)
    return value


def _match_candidates(provider: str, candidates: Any, key: str, origin: str) -> tuple[dict[str, Any] | None, str | None]:
    if candidates is None:
        candidates = []
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return None, "EXECUTION_PROJECTION_READBACK_INVALID"
    matched = [dict(x) for x in candidates if isinstance(x, Mapping) and x.get("materialization_key") == key]
    if len(matched) > 1:
        return None, "EXECUTION_MATERIALIZATION_CONFLICT"
    if not matched:
        return None, None
    item = matched[0]
    if item.get("origin_research_ref") != origin or not item.get("id"):
        return None, "EXECUTION_MATERIALIZATION_CONFLICT"
    item["provider"] = provider
    return item, None


def materialize_research_execution(research: Mapping[str, Any], approval: Mapping[str, Any], readbacks: Mapping[str, Any] | None = None, *, effects_started: Sequence[str] | None = None, now: datetime | None = None) -> dict[str, Any]:
    spec = compile_execution_task_spec(research, approval, now=now)
    key, origin = spec["materialization_key"], spec["origin_research_ref"]
    readbacks = readbacks or {}
    gh, gh_err = _match_candidates("github", readbacks.get("github"), key, origin)
    jira, jira_err = _match_candidates("jira", readbacks.get("jira"), key, origin)
    error = gh_err or jira_err
    if error:
        outcome, reason, intents = "CONFLICT", error, []
    else:
        missing = [p for p, item in (("github", gh), ("jira", jira)) if item is None]
        started = set(effects_started or [])
        if any(p in started for p in missing):
            outcome, reason, intents = "RECONCILIATION_REQUIRED", "EXECUTION_PROJECTION_RECONCILIATION_REQUIRED", []
        else:
            intents = [{"provider": p, "action": "ensure_execution_task", "idempotency_key": f"{key}:{p}", "materialization_key": key, "origin_research_ref": origin, "task_spec_digest": spec["spec_digest"]} for p in missing]
            if not missing:
                outcome, reason = "READY", "EXECUTION_PROJECTIONS_RECONCILED"
            else:
                outcome, reason = "ACTION_REQUIRED", "EXECUTION_PROJECTION_CREATE_REQUIRED"
    spec["projection_refs"] = {"github": gh, "jira": jira}
    spec["spec_digest"] = _digest({k:v for k,v in spec.items() if k != "spec_digest"})
    claim = None if outcome != "READY" else {"action": "claim_execution_task", "idempotency_key": f"{key}:claim", "materialization_key": key, "expected_projection_ids": {"github": gh["id"], "jira": jira["id"]}}
    result: dict[str, Any] = {
        "schema_version": "1.0", "artifact_type": "research-execution-materialization", "materialization_key": key,
        "outcome": outcome, "reason_code": reason, "execution_task_spec": spec,
        "projection_state": {"github": gh, "jira": jira}, "projection_intents": intents, "claim_intent": claim,
        "authority_granted": False, "g4_g5_g6_authority_granted": False,
    }
    result["decision_digest"] = _digest(result)
    return result
