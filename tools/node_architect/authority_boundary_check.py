"""Pure, replay-safe evaluation of one requested GWC authority boundary.

The evaluator describes the minimum gate and the next safe preparation only. It
never invokes a connector, changes state, or grants execution authority.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import re
from datetime import datetime
from typing import Any


# NOTE on the nested `scope_identity` projection (MINOR#4 clarification)
# --------------------------------------------------------------------------
# Each emitted `authority-boundary-decision` embeds a *compact* `scope_identity`
# projection (see `_base_output` / `schema $defs.scope_identity`). It is a
# deliberately bounded subset of the canonical `gate-scope-identity` artifact
# produced by `scope_hash_calculation.calculate_gate_scope_identity` (SCRUM-187):
#   - It reuses the SAME key set and value constraints as the canonical schema
#     (`task_id`, `repository`, `base_sha`, `head_sha`, `scope_hash`,
#     `authorized_actions`, `excluded_actions`, plus optional `schema_version`,
#     `artifact_type`, `base_ref`, `working_branch`, `risk_class`,
#     `authorized_paths`, `additional_bindings`, `outcome`, `authority_granted`).
#   - It is bound to the live decision's scope_hash/base_sha/head_sha for
#     replay-key stability and drift detection; it does NOT itself recompute or
#     re-authorize the canonical semantic scope_hash.
#   - It MUST NOT be treated as a standalone scope-identity approval: the
#     authoritative, hash-independent canonical artifact lives in
#     `.gwc/tasks/<task>/g2/execution-envelope.yaml` (G2) and the canonical
#     `gate-scope-identity` node. The nested projection only mirrors those
#     bindings for traceability inside the decision payload.
# This intentional asymmetry (bounded projection vs full canonical identity) is
# by design; the schema's own description states the projection "does not
# replace the standalone canonical artifact."

GATE_ORDER = (
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION_DATA",
)
GATE_INDEX = {gate: index for index, gate in enumerate(GATE_ORDER)}
VALID_RISK_CLASSES = {"R0", "R1", "R2", "R3"}
GATE_STATUSES = {"READY", "RUNNING", "PASS", "BLOCKED", "FAILED", "NOT_APPLICABLE"}
REPOSITORY_PATTERN = re.compile(r"^[^/\s]+/[^/\s]+$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SCOPE_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
# SCRUM-311: if a caller supplies both an evidence age and this threshold, ages
# beyond it are rejected as stale. None => not enforced (opt-in, fail-soft-open).
STALE_EVIDENCE_MAX_AGE_S: int | None = None
SCOPE_IDENTITY_KEYS = {
    "schema_version", "artifact_type", "task_id", "repository", "base_ref",
    "base_sha", "working_branch", "head_sha", "risk_class", "authorized_paths",
    "authorized_actions", "excluded_actions", "additional_bindings", "outcome",
    "scope_hash", "authority_granted",
}


def _normalize_action(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _make_action_map() -> dict[str, str]:
    groups = {
        "G0_CONTEXT": {
            "read", "search", "fetch", "read_repository", "inspect_repository",
            "inspect_task", "inspect_connector", "read_only_read", "read_only_inspection",
            "read_search_fetch",
        },
        "G1_ALIGNMENT": {
            "g1_artifact_preparation", "g1_read_only_validation", "materialize_g1_artifacts",
            "run_read_only_validation", "run_independent_review", "validation",
            "g1_artifact_read_only_validation",
        },
        "G2_EXECUTION": {
            "branch", "worktree", "file", "files", "modify_file", "modify_approved_files",
            "commit", "push", "branch_creation", "worktree_creation", "repository_write",
            "branch_worktree_file_commit_push",
        },
        "G3_PR": {
            "draft_pr", "create_draft_pr", "open_or_update_draft_pr", "ready_for_review",
            "mark_pr_ready_for_review", "ready_for_review_metadata", "draft_pr_ready_for_review_metadata",
        },
        "G4_MERGE": {"merge", "auto_merge", "merge_approved_pr", "enable_auto_merge"},
        "G5_DEPLOY": {
            "post_merge_status", "postmerge_status", "verify_post_merge_ci",
            "read_only_post_merge_status", "g5_status_verify", "status_verification",
            "deploy", "redeploy", "publish", "release", "runtime_reload",
            "deploy_approved_release", "manual_deploy", "manual_release",
        },
        "G6_PRODUCTION_DATA": {
            "production_data_read", "production_data_write", "production_data",
            "production_configuration", "production_config_change", "production_config",
            "migration", "credential", "credential_rotation", "secret", "secret_operation",
            "production_secret_operation", "production_data_configuration_migration_credential_secret",
        },
    }
    return {action: gate for gate, actions in groups.items() for action in actions}


ACTION_TO_MINIMUM_GATE = _make_action_map()
READ_ONLY_ACTIONS = {
    action for action, gate in ACTION_TO_MINIMUM_GATE.items()
    if gate in {"G0_CONTEXT", "G1_ALIGNMENT"}
}
G5_STATUS_ACTIONS = {
    "post_merge_status", "postmerge_status", "verify_post_merge_ci",
    "read_only_post_merge_status", "g5_status_verify", "status_verification",
}
MANUAL_G5_ACTIONS = {
    "deploy", "redeploy", "publish", "release", "runtime_reload",
    "deploy_approved_release", "manual_deploy", "manual_release",
}
PRODUCTION_ACTIONS = {
    action for action, gate in ACTION_TO_MINIMUM_GATE.items()
    if gate == "G6_PRODUCTION_DATA"
}
PROHIBITED_ACTIONS = {
    "force_push", "shared_history_rewrite", "rewrite_shared_history",
    "unauthorized_branch_deletion", "delete_branch", "branch_deletion",
}

# A scope commonly names the operation rather than the low-level action. Keep
# both forms equivalent without weakening the explicit excluded-actions check.
SCOPE_ACTION_ALIASES: dict[str, set[str]] = {
    "read": {"read", "read_repository", "inspect_repository"},
    "search": {"search", "read_repository"},
    "fetch": {"fetch", "read_repository"},
    "read_search_fetch": {"read_search_fetch", "read_repository"},
    "g1_artifact_read_only_validation": {"g1_artifact_read_only_validation", "run_read_only_validation"},
    "branch": {"branch", "branch_creation", "modify_approved_files"},
    "worktree": {"worktree", "worktree_creation", "modify_approved_files"},
    "file": {"file", "files", "modify_file", "modify_approved_files", "repository_write"},
    "files": {"file", "files", "modify_file", "modify_approved_files", "repository_write"},
    "commit": {"commit", "modify_approved_files"},
    "push": {"push", "push_working_branch"},
    "draft_pr": {"draft_pr", "create_draft_pr", "open_or_update_draft_pr"},
    "create_draft_pr": {"draft_pr", "create_draft_pr", "open_or_update_draft_pr"},
    "ready_for_review": {"ready_for_review", "mark_pr_ready_for_review"},
    "merge": {"merge", "merge_approved_pr"},
    "auto_merge": {"auto_merge", "enable_auto_merge", "merge_approved_pr"},
    "deploy": {"deploy", "deploy_approved_release"},
    "redeploy": {"redeploy", "deploy_approved_release"},
    "publish": {"publish", "deploy_approved_release"},
    "release": {"release", "deploy_approved_release"},
    "runtime_reload": {"runtime_reload", "deploy_approved_release"},
    "production_configuration": {"production_configuration", "production_config_change"},
    "production_config_change": {"production_configuration", "production_config_change"},
    "production_data": {"production_data", "production_data_read", "production_data_write"},
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_iso8601(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _as_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_PATTERN.fullmatch(value) is not None


def _valid_scope_hash(value: Any) -> bool:
    return isinstance(value, str) and SCOPE_HASH_PATTERN.fullmatch(value) is not None


def _valid_string_list(value: Any, *, minimum: int = 0) -> bool:
    if not isinstance(value, list) or len(value) < minimum:
        return False
    if any(not isinstance(item, str) or not item for item in value):
        return False
    return len(value) == len(set(value))


def _valid_risk_class(value: Any) -> bool:
    return isinstance(value, str) and value in VALID_RISK_CLASSES


def _valid_bindings(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    keys: list[str] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"key", "value"}
            or not isinstance(item["key"], str)
            or not item["key"]
            or not isinstance(item["value"], str)
            or not item["value"]
        ):
            return False
        keys.append(item["key"])
    return len(keys) == len(set(keys))


def _valid_scope_identity(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) - SCOPE_IDENTITY_KEYS:
        return False
    required = {"task_id", "repository", "base_sha", "head_sha", "scope_hash", "authorized_actions", "excluded_actions"}
    if not required.issubset(value):
        return False
    if not isinstance(value["task_id"], str) or not value["task_id"]:
        return False
    if not isinstance(value["repository"], str) or REPOSITORY_PATTERN.fullmatch(value["repository"]) is None:
        return False
    if not _valid_sha(value["base_sha"]) or not _valid_sha(value["head_sha"]):
        return False
    if not _valid_scope_hash(value["scope_hash"]):
        return False
    if not _valid_string_list(value["authorized_actions"], minimum=1):
        return False
    if not _valid_string_list(value["excluded_actions"]):
        return False
    if "schema_version" in value and value["schema_version"] != "1.0":
        return False
    if "artifact_type" in value and value["artifact_type"] != "gate-scope-identity":
        return False
    if "base_ref" in value and (not isinstance(value["base_ref"], str) or not value["base_ref"]):
        return False
    if "working_branch" in value and value["working_branch"] is not None and (
        not isinstance(value["working_branch"], str) or not value["working_branch"]
    ):
        return False
    if "risk_class" in value and not _valid_risk_class(value["risk_class"]):
        return False
    if "authorized_paths" in value and not _valid_string_list(value["authorized_paths"], minimum=1):
        return False
    if "additional_bindings" in value:
        if not _valid_bindings(value["additional_bindings"]):
            return False
    if "outcome" in value and value["outcome"] not in {"READY", "BLOCKED"}:
        return False
    if "authority_granted" in value and value["authority_granted"] is not False:
        return False
    return True


def _safe_text(value: Any, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _safe_repository(value: Any) -> str:
    return value if isinstance(value, str) and REPOSITORY_PATTERN.fullmatch(value) else "invalid/invalid"


def _safe_scope_identity(value: Any, *, task_id: str, repository: str) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    safe: dict[str, Any] = {
        "task_id": _safe_text(raw.get("task_id"), task_id),
        "repository": _safe_repository(raw.get("repository")) if raw.get("repository") is not None else repository,
        "base_sha": raw.get("base_sha") if _valid_sha(raw.get("base_sha")) else "0" * 40,
        "head_sha": raw.get("head_sha") if _valid_sha(raw.get("head_sha")) else "0" * 40,
        "scope_hash": raw.get("scope_hash") if _valid_scope_hash(raw.get("scope_hash")) else "sha256:" + "0" * 64,
        "authorized_actions": raw.get("authorized_actions") if _valid_string_list(raw.get("authorized_actions"), minimum=1) else ["invalid_action"],
        "excluded_actions": raw.get("excluded_actions") if _valid_string_list(raw.get("excluded_actions")) else [],
    }
    optional = {
        "schema_version": lambda item: item == "1.0",
        "artifact_type": lambda item: item == "gate-scope-identity",
        "base_ref": lambda item: isinstance(item, str) and bool(item),
        "working_branch": lambda item: item is None or (isinstance(item, str) and bool(item)),
        "risk_class": _valid_risk_class,
        "authorized_paths": lambda item: _valid_string_list(item, minimum=1),
        "outcome": lambda item: item in {"READY", "BLOCKED"},
        "authority_granted": lambda item: item is False,
    }
    for key, predicate in optional.items():
        if key in raw and predicate(raw[key]):
            safe[key] = raw[key]
    bindings = raw.get("additional_bindings")
    if _valid_bindings(bindings):
        safe["additional_bindings"] = bindings
    return safe


def _normalize_list(value: Any) -> list[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if any(not isinstance(item, str) or not item for item in value):
        return None
    return [_normalize_action(item) for item in value]


def _get_gate(state: Mapping[str, Any]) -> str | None:
    value = state.get("current_gate", state.get("gate"))
    return value if isinstance(value, str) and value in GATE_INDEX else None


def _get_status(state: Mapping[str, Any]) -> str | None:
    value = state.get("gate_status", state.get("status", "PASS"))
    if value is None:
        return None
    return value if isinstance(value, str) else None


def _scope_action_allowed(action: str, scope: Mapping[str, Any]) -> tuple[bool, bool]:
    authorized = _normalize_list(scope.get("authorized_actions"))
    excluded = _normalize_list(scope.get("excluded_actions", []))
    if authorized is None or not authorized or excluded is None:
        return False, False
    aliases = SCOPE_ACTION_ALIASES.get(action, {action})
    is_excluded = action in excluded or bool(aliases & set(excluded))
    is_authorized = action in authorized or bool(aliases & set(authorized))
    return is_authorized, is_excluded


def _scope_mismatch(
    *, task_id: str, repository: str, scope: Mapping[str, Any], state: Mapping[str, Any]
) -> bool:
    for key, expected in (("task_id", task_id), ("repository", repository)):
        left = scope.get(key)
        right = state.get(key)
        if left is not None and left != expected:
            return True
        if right is not None and right != expected:
            return True
        if left is not None and right is not None and left != right:
            return True
    for scope_key, state_keys in (
        ("scope_hash", ("scope_hash",)),
        ("base_sha", ("base_sha", "current_base_sha")),
        ("head_sha", ("head_sha",)),
    ):
        left = scope.get(scope_key)
        right = next((state.get(key) for key in state_keys if state.get(key) is not None), None)
        if left is not None and right is not None and left != right:
            return True
    drift = state.get("drift_decision", state.get("drift"))
    if isinstance(drift, Mapping):
        if drift.get("status") in {"REVALIDATE", "REAPPROVE", "STOP", "DRIFT"}:
            return True
        if drift.get("has_drift") is True:
            return True
    if drift is True or state.get("scope_drift") is True or state.get("base_drift") is True or state.get("head_drift") is True:
        return True
    return False


def _policy_gate(action: str, policy: Mapping[str, Any], default: str) -> str | None:
    candidate = policy.get("action_map", policy.get("action_to_minimum_gate"))
    if not isinstance(candidate, Mapping):
        candidate = policy.get("actions")
    if isinstance(candidate, Mapping):
        missing = object()
        value = candidate.get(action, missing)
        if value is missing:
            return default
        if isinstance(value, Mapping):
            value = value.get("minimum_gate", value.get("gate"))
        if not isinstance(value, str) or value not in GATE_INDEX or value != default:
            return None
        return default
    return default


def _request_fingerprint(
    *, task_id: str, repository: str, action: str | None, minimum_gate: str | None,
    current_gate: str | None, scope: Mapping[str, Any], state: Mapping[str, Any],
    risk_class: str, production_scope_applicable: bool, manual_g5_action: bool,
    envelope_expires_at: str | None = None, stale_evidence: bool = False,
    evidence_age_s: int | None = None,
) -> str:
    payload = {
        "task_id": task_id,
        "repository": repository,
        "action": action,
        "minimum_gate": minimum_gate,
        "current_gate": current_gate,
        "scope_hash": scope.get("scope_hash"),
        "base_sha": scope.get("base_sha", state.get("current_base_sha", state.get("base_sha"))),
        "head_sha": scope.get("head_sha", state.get("head_sha")),
        "risk_class": risk_class,
        "production_scope_applicable": production_scope_applicable,
        "manual_g5_action": manual_g5_action,
        "envelope_expires_at": envelope_expires_at,
        "stale_evidence": stale_evidence,
        "evidence_age_s": evidence_age_s,
    }
    return _digest(payload)


def _dedupe(codes: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(code for code in codes if code))


def _decision_digest(output: Mapping[str, Any]) -> str:
    stable = {
        key: value for key, value in output.items()
        if key not in {"decision_digest", "evaluated_at", "replay_status"}
    }
    return _digest(stable)


def _base_output(
    *, task_id: str, repository: str, requested_action: str, canonical_action: str | None,
    minimum_gate: str | None, current_gate: str | None, current_gate_status: str | None,
    scope_identity: Mapping[str, Any], gate_state: Mapping[str, Any], risk_class: str,
    production_scope_applicable: bool, manual_g5_action: bool,
    event_id_or_idempotency_key: str, replay_status: str, request_fingerprint: str,
    evaluated_at: str | None, envelope_expires_at: str | None = None,
    stale_evidence: bool = False,
) -> dict[str, Any]:
    # Nested `scope_identity` is the compact projection described in the module
    # note (MINOR#4): it mirrors the canonical gate-scope-identity bindings for
    # this decision and must not be read as a standalone approval artifact.
    scope_hash = scope_identity.get("scope_hash", gate_state.get("scope_hash"))
    base_sha = scope_identity.get("base_sha", gate_state.get("current_base_sha", gate_state.get("base_sha")))
    head_sha = scope_identity.get("head_sha", gate_state.get("head_sha"))
    return {
        "schema_version": "1.0",
        "artifact_type": "authority-boundary-decision",
        "task_id": task_id,
        "repository": repository,
        "requested_action": requested_action,
        "canonical_action": canonical_action,
        "minimum_gate": minimum_gate,
        "current_gate": current_gate,
        "current_gate_status": current_gate_status,
        "decision": "BLOCK",
        "approval_required": False,
        "required_approval_gate": None,
        "prohibited": False,
        "next_authorized_preparation": [],
        "reason_codes": ["AUTHORITY_INPUT_INVALID"],
        "primary_reason_code": "AUTHORITY_INPUT_INVALID",
        "scope_identity": dict(scope_identity),
        "scope_hash": scope_hash,
        "current_base_sha": base_sha,
        "head_sha": head_sha,
        "risk_class": risk_class,
        "production_scope_applicable": production_scope_applicable,
        "manual_g5_action": manual_g5_action,
        "envelope_expires_at": envelope_expires_at,
        "stale_evidence": stale_evidence,
        "event_id_or_idempotency_key": event_id_or_idempotency_key,
        "replay_status": replay_status,
        "request_fingerprint": request_fingerprint,
        "evaluated_at": evaluated_at,
        "decision_digest": "",
        "authority_granted": False,
        "execution_authority_granted": False,
        "write_authority_granted": False,
        "pr_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _finish(output: dict[str, Any], reasons: Sequence[str]) -> dict[str, Any]:
    output["reason_codes"] = _dedupe(reasons)
    output["primary_reason_code"] = output["reason_codes"][0]
    output["decision_digest"] = _decision_digest(output)
    return output


def _prior_conflicts(prior: Mapping[str, Any], fingerprint: str, output: Mapping[str, Any]) -> bool:
    for key in ("task_id", "repository", "requested_action", "canonical_action", "minimum_gate", "current_gate", "scope_hash"):
        if key in prior and prior.get(key) != output.get(key):
            return True
    previous_fingerprint = prior.get("request_fingerprint")
    if isinstance(previous_fingerprint, str):
        return previous_fingerprint != fingerprint
    return False


def check_authority_boundary(
    *,
    task_id: str,
    repository: str,
    requested_action: str,
    gate_state_resolution: dict[str, object],
    scope_identity: dict[str, object],
    gate_policy: dict[str, object],
    risk_class: str,
    production_scope_applicable: bool,
    manual_g5_action: bool,
    event_id_or_idempotency_key: str,
    prior_decision: dict[str, object] | None = None,
    evaluated_at: str | None = None,
    envelope_expires_at: str | None = None,
    stale_evidence: bool = False,
    evidence_age_s: int | None = None,
) -> dict[str, object]:
    """Evaluate one action without performing it or granting authority."""
    state = gate_state_resolution if isinstance(gate_state_resolution, Mapping) else {}
    scope = scope_identity if isinstance(scope_identity, Mapping) else {}
    policy = gate_policy if isinstance(gate_policy, Mapping) else {}
    action = _normalize_action(requested_action)
    safe_task_id = _safe_text(task_id, "invalid-task")
    safe_repository = _safe_repository(repository)
    safe_requested_action = _safe_text(requested_action, "invalid-action")
    safe_scope = _safe_scope_identity(scope, task_id=safe_task_id, repository=safe_repository)
    safe_risk_class = risk_class if _valid_risk_class(risk_class) else "R0"
    safe_production_scope = production_scope_applicable if isinstance(production_scope_applicable, bool) else False
    safe_manual_g5 = manual_g5_action if isinstance(manual_g5_action, bool) else False
    safe_envelope_expires_at = envelope_expires_at if isinstance(envelope_expires_at, str) else None
    safe_stale_evidence = stale_evidence if isinstance(stale_evidence, bool) else False
    safe_event_id = _safe_text(event_id_or_idempotency_key, "invalid-event")
    safe_evaluated_at = evaluated_at if isinstance(evaluated_at, str) else None
    minimum_gate = ACTION_TO_MINIMUM_GATE.get(action)
    if minimum_gate is None and action in PROHIBITED_ACTIONS:
        # Prohibited history operations are known actions at the execution
        # boundary; they must report PROHIBITED rather than UNKNOWN.
        minimum_gate = "G2_EXECUTION"
    current_gate = _get_gate(state)
    current_status = _get_status(state)
    fingerprint = _request_fingerprint(
        task_id=task_id, repository=repository, action=action or None,
        minimum_gate=minimum_gate, current_gate=current_gate, scope=scope,
        state=state, risk_class=risk_class,
        production_scope_applicable=production_scope_applicable,
        manual_g5_action=manual_g5_action,
        envelope_expires_at=envelope_expires_at, stale_evidence=stale_evidence,
        evidence_age_s=evidence_age_s,
    )
    output = _base_output(
        task_id=safe_task_id, repository=safe_repository, requested_action=safe_requested_action,
        canonical_action=action or None, minimum_gate=minimum_gate,
        current_gate=current_gate, current_gate_status=current_status,
        scope_identity=safe_scope, gate_state=state, risk_class=safe_risk_class,
        production_scope_applicable=safe_production_scope,
        manual_g5_action=safe_manual_g5,
        envelope_expires_at=safe_envelope_expires_at,
        stale_evidence=safe_stale_evidence,
        event_id_or_idempotency_key=safe_event_id,
        replay_status="FIRST_SEEN", request_fingerprint=fingerprint,
        evaluated_at=safe_evaluated_at,
    )

    invalid = [
        not isinstance(task_id, str) or not task_id,
        not isinstance(repository, str) or not repository,
        not isinstance(requested_action, str) or not requested_action,
        not isinstance(gate_state_resolution, dict),
        not _valid_scope_identity(scope_identity),
        not isinstance(gate_policy, dict),
        not _valid_risk_class(risk_class),
        not isinstance(production_scope_applicable, bool),
        not isinstance(manual_g5_action, bool),
        not isinstance(event_id_or_idempotency_key, str) or not event_id_or_idempotency_key,
        evaluated_at is not None and not isinstance(evaluated_at, str),
        not isinstance(envelope_expires_at, (str, type(None))),
        not isinstance(stale_evidence, bool),
        not isinstance(evidence_age_s, (int, type(None))),
    ]
    if any(invalid) or not current_gate or not current_status or current_status not in GATE_STATUSES:
        return _finish(output, ["AUTHORITY_INPUT_INVALID"])

    # SCRUM-311: closed-envelope expiry + stale-evidence determinism.
    exp = _parse_iso8601(envelope_expires_at)
    ref = _parse_iso8601(evaluated_at) if isinstance(evaluated_at, str) else None
    if envelope_expires_at is not None:
        if exp is None or ref is None or ref > exp:
            return _finish(output, ["AUTHORITY_ENVELOPE_EXPIRED"])
    if stale_evidence:
        return _finish(output, ["AUTHORITY_STALE_EVIDENCE_REJECTED"])
    if (
        evidence_age_s is not None
        and STALE_EVIDENCE_MAX_AGE_S is not None
        and evidence_age_s > STALE_EVIDENCE_MAX_AGE_S
    ):
        return _finish(output, ["AUTHORITY_STALE_EVIDENCE_REJECTED"])

    if minimum_gate:
        policy_gate = _policy_gate(action, policy, minimum_gate)
        if policy_gate is None:
            output["minimum_gate"] = minimum_gate
            return _finish(output, ["AUTHORITY_POLICY_MISMATCH"])
        minimum_gate = policy_gate
    output["minimum_gate"] = minimum_gate
    output["request_fingerprint"] = _request_fingerprint(
        task_id=task_id, repository=repository, action=action,
        minimum_gate=minimum_gate, current_gate=current_gate, scope=scope,
        state=state, risk_class=risk_class,
        production_scope_applicable=production_scope_applicable,
        manual_g5_action=manual_g5_action,
        envelope_expires_at=envelope_expires_at, stale_evidence=stale_evidence,
        evidence_age_s=evidence_age_s,
    )
    fingerprint = output["request_fingerprint"]

    if minimum_gate is None:
        return _finish(output, ["AUTHORITY_ACTION_UNKNOWN"])

    if prior_decision and isinstance(prior_decision, Mapping):
        if prior_decision.get("event_id_or_idempotency_key") == event_id_or_idempotency_key:
            if _prior_conflicts(prior_decision, fingerprint, output):
                output["replay_status"] = "REPLAY_CONFLICT"
                output["decision"] = "BLOCK"
                return _finish(output, ["AUTHORITY_REPLAY_CONFLICT"])
            output["replay_status"] = "IDEMPOTENT_REPLAY"

    state_replay = state.get("replay_status")
    if state_replay == "REPLAY_CONFLICT":
        output["replay_status"] = "REPLAY_CONFLICT"
        return _finish(output, ["AUTHORITY_REPLAY_CONFLICT"])

    if _scope_mismatch(task_id=task_id, repository=repository, scope=scope, state=state):
        return _finish(output, ["AUTHORITY_SCOPE_MISMATCH"])

    authorized, excluded = _scope_action_allowed(action, scope)
    if action in PROHIBITED_ACTIONS or excluded:
        output["prohibited"] = True
        return _finish(output, ["AUTHORITY_ACTION_PROHIBITED"])
    if not authorized:
        return _finish(output, ["AUTHORITY_SCOPE_MISMATCH"])

    if action in PRODUCTION_ACTIONS and not production_scope_applicable:
        output["decision"] = "NOT_APPLICABLE"
        return _finish(output, ["AUTHORITY_G6_NOT_APPLICABLE"])

    if current_status in {"BLOCKED", "FAILED"}:
        return _finish(output, ["AUTHORITY_GATE_INSUFFICIENT"])

    current_index = GATE_INDEX[current_gate]
    minimum_index = GATE_INDEX[minimum_gate]
    is_g5_status = action in G5_STATUS_ACTIONS and not manual_g5_action
    if is_g5_status and current_index >= GATE_INDEX["G4_MERGE"]:
        output["decision"] = "ALLOW_PREPARATION"
        output["next_authorized_preparation"] = ["run_read_only_post_merge_status_verification"]
        return _finish(output, ["AUTHORITY_PREPARATION_ALLOWED"])

    if action in READ_ONLY_ACTIONS:
        if current_index < minimum_index:
            return _finish(output, ["AUTHORITY_GATE_INSUFFICIENT"])
        output["decision"] = "ALLOW_PREPARATION"
        output["next_authorized_preparation"] = [f"run_read_only_{action}"]
        return _finish(output, ["AUTHORITY_PREPARATION_ALLOWED"])

    output["decision"] = "REQUIRE_APPROVAL"
    output["approval_required"] = True
    output["required_approval_gate"] = minimum_gate
    output["next_authorized_preparation"] = [f"prepare_{action}_approval"]
    reasons: list[str] = []
    if current_index < minimum_index:
        reasons.append("AUTHORITY_GATE_INSUFFICIENT")
        if current_index >= GATE_INDEX["G3_PR"] and minimum_index > current_index:
            reasons.append("AUTHORITY_LATER_GATE_INHERITANCE_REJECTED")
    else:
        reasons.append("AUTHORITY_APPROVAL_REQUIRED")
    if action in MANUAL_G5_ACTIONS or manual_g5_action:
        reasons.insert(0, "AUTHORITY_G5_MANUAL_APPROVAL_REQUIRED")
    return _finish(output, reasons)


__all__ = ["ACTION_TO_MINIMUM_GATE", "check_authority_boundary"]
