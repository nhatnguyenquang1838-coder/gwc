"""Deterministic, replay-safe GWC gate-state resolution."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from tools.node_architect.evidence_artifact_map import _GATE_REQUIREMENTS
from tools.node_architect.scope_hash_calculation import (
    BINDING_KEYS,
    CANONICAL_ACTIONS,
    calculate_gate_scope_identity,
)

GATE_ORDER = (
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION_DATA",
)
AUTHORITY_FLAGS = (
    "authority_granted",
    "write_authority_granted",
    "pr_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
)
CANONICAL_CLASSES = {
    "CANONICAL_AUTHORITY",
    "CANONICAL_GATE_EVIDENCE",
    "DELIVERY_EVIDENCE",
}
ALL_CLASSES = CANONICAL_CLASSES | {"AUDIT_PROJECTION", "RESUME_HINT"}
READ_ONLY_ACTIONS = {
    "read_repository",
    "inspect_connector",
    "inspect_task",
    "materialize_g1_artifacts",
    "run_read_only_validation",
    "run_independent_review",
    "verify_post_merge_ci",
    "readback_branch_pr_diff_ci",
}
PRODUCTION_ACTIONS = {
    "production_data_read",
    "production_data_write",
    "production_config_change",
    "credential_rotation",
    "migration",
}
EVIDENCE_BLOCKERS = {
    "EVIDENCE_INPUT_INVALID",
    "EVIDENCE_BINDING_MISMATCH",
    "EVIDENCE_CONFLICT",
    "EVIDENCE_PROJECTION_ONLY",
    "EVIDENCE_STALE",
    "EVIDENCE_REQUIRED_MISSING",
    "EVIDENCE_OBSERVABILITY_INCOMPLETE",
    "EVIDENCE_CI_BINDING_MISMATCH",
}
EVIDENCE_REASONS = EVIDENCE_BLOCKERS | {
    "EVIDENCE_MAP_READY",
    "EVIDENCE_G6_NOT_APPLICABLE",
}
REASON_PRECEDENCE = (
    "GATE_STATE_INPUT_INVALID",
    "GATE_STATE_REPLAY_CONFLICT",
    "GATE_STATE_BINDING_MISMATCH",
    "GATE_STATE_EVIDENCE_CONFLICT",
    "GATE_STATE_GATE_FAILED",
    "GATE_STATE_DRIFT",
    "GATE_STATE_EVIDENCE_STALE",
    "GATE_STATE_REQUIRED_EVIDENCE_MISSING",
    "GATE_STATE_LATER_GATE_INHERITANCE_REJECTED",
    "GATE_STATE_RESOLVED",
    "GATE_STATE_PROJECTION_MISMATCH",
    "GATE_STATE_G6_NOT_APPLICABLE",
)
TRANSITION_DIGEST = "3246896730efb267cd61e377ae9a1ab8365733ab4ddd532b80fd1ce2d82be62f"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY_PATTERN = re.compile(r"^[^/\s]+/[^/\s]+$")
OBSERVATION_FIELDS = {
    "observed_at",
    "mapped_at",
    "calculated_at",
    "generated_at",
    "updated_at",
    "created_at",
    "decision_digest",
    "resolution_digest",
    "map_digest",
}
SCOPE_FIELDS = {
    "schema_version",
    "artifact_type",
    "task_id",
    "repository",
    "base_ref",
    "base_sha",
    "working_branch",
    "head_sha",
    "risk_class",
    "authorized_paths",
    "authorized_actions",
    "excluded_actions",
    "additional_bindings",
    "outcome",
    "reason_codes",
    "calculated_at",
    "scope_hash",
    "approval_request_digest",
    "authority_granted",
}
MAP_FIELDS = {
    "schema_version",
    "artifact_type",
    "task_id",
    "repository",
    "base_sha",
    "head_sha",
    "policy_revision",
    "mapped_at",
    "outcome",
    "reason_codes",
    "entries",
    "requirements",
    "missing_required",
    "stale_required",
    "projection_only",
    "map_digest",
    "authority_granted",
}
ENTRY_FIELDS = {
    "evidence_key",
    "gate",
    "artifact_role",
    "artifact_type",
    "classification",
    "required",
    "source_type",
    "target",
    "ref",
    "revision",
    "digest",
    "binding_status",
    "freshness_status",
    "materialization_status",
    "source_of_truth",
    "reason_codes",
}
ENTRY_REQUIRED_FIELDS = ENTRY_FIELDS


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _strip_observation_fields(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_observation_fields(item)
            for key, item in value.items()
            if str(key) not in OBSERVATION_FIELDS
        }
    if isinstance(value, list):
        return [_strip_observation_fields(item) for item in value]
    return value


def _string_list(value: object, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (not nonempty or bool(value))
        and len(value) == len(set(value))
        and all(isinstance(item, str) and item for item in value)
    )


def _sorted_reason_codes(values: list[str]) -> list[str]:
    return sorted(
        set(values),
        key=lambda value: (
            REASON_PRECEDENCE.index(value)
            if value in REASON_PRECEDENCE
            else len(REASON_PRECEDENCE),
            value,
        ),
    )


def _public_requirements(task_id: str) -> list[dict[str, object]]:
    return [
        {
            "gate": requirement["gate"],
            "artifact_role": requirement["artifact_role"],
            "target": requirement["target"].replace("<task-id>", task_id),
            "required": requirement.get("required", "true") == "true",
        }
        for requirement in _GATE_REQUIREMENTS
    ]


def _requirement_policy(task_id: str) -> dict[str, dict[str, object]]:
    return {
        requirement["target"].replace("<task-id>", task_id): {
            "gate": requirement["gate"],
            "artifact_role": requirement["artifact_role"],
            "target": requirement["target"].replace("<task-id>", task_id),
            "classification": requirement["class_"],
            "required": requirement.get("required", "true") == "true",
        }
        for requirement in _GATE_REQUIREMENTS
    }


def _scope_valid(scope: object) -> bool:
    required = {
        "schema_version",
        "artifact_type",
        "task_id",
        "repository",
        "base_ref",
        "base_sha",
        "risk_class",
        "authorized_paths",
        "authorized_actions",
        "excluded_actions",
        "outcome",
        "scope_hash",
        "authority_granted",
    }
    if not isinstance(scope, Mapping) or set(scope) - SCOPE_FIELDS or not required <= set(scope):
        return False
    if (
        scope.get("schema_version") != "1.0"
        or scope.get("artifact_type") != "gate-scope-identity"
        or scope.get("outcome") != "READY"
        or scope.get("authority_granted") is not False
    ):
        return False
    if not isinstance(scope.get("task_id"), str) or not scope["task_id"]:
        return False
    if not isinstance(scope.get("repository"), str) or not REPOSITORY_PATTERN.match(scope["repository"]):
        return False
    if not isinstance(scope.get("base_ref"), str) or not scope["base_ref"]:
        return False
    if not isinstance(scope.get("base_sha"), str) or not SHA_PATTERN.match(scope["base_sha"]):
        return False
    if scope.get("head_sha") is not None and (
        not isinstance(scope["head_sha"], str) or not SHA_PATTERN.match(scope["head_sha"])
    ):
        return False
    if scope.get("risk_class") not in {"R0", "R1", "R2", "R3"}:
        return False
    if not _string_list(scope.get("authorized_paths")):
        return False
    if not _string_list(scope.get("authorized_actions"), nonempty=True):
        return False
    if not _string_list(scope.get("excluded_actions")):
        return False
    actions = set(scope["authorized_actions"])
    if not actions <= CANONICAL_ACTIONS:
        return False
    if actions & set(scope["excluded_actions"]):
        return False
    if not scope["authorized_paths"] and not actions <= READ_ONLY_ACTIONS:
        return False
    bindings = scope.get("additional_bindings", [])
    if not isinstance(bindings, list) or any(
        not isinstance(binding, Mapping)
        or set(binding) != {"key", "value"}
        or binding.get("key") not in BINDING_KEYS
        or not isinstance(binding.get("value"), str)
        or not binding["value"]
        for binding in bindings
    ):
        return False
    if not isinstance(scope.get("scope_hash"), str) or not DIGEST_PATTERN.match(scope["scope_hash"]):
        return False
    try:
        rebuilt = calculate_gate_scope_identity(
            task_id=scope["task_id"],
            repository=scope["repository"],
            base_ref=scope["base_ref"],
            base_sha=scope["base_sha"],
            working_branch=scope.get("working_branch"),
            head_sha=scope.get("head_sha"),
            risk_class=scope["risk_class"],
            authorized_paths=scope["authorized_paths"],
            authorized_actions=scope["authorized_actions"],
            excluded_actions=scope["excluded_actions"],
            additional_bindings=bindings,
            calculated_at=scope.get("calculated_at"),
        )
    except Exception:
        return False
    semantic_keys = (
        "task_id",
        "repository",
        "base_ref",
        "base_sha",
        "working_branch",
        "head_sha",
        "risk_class",
        "authorized_paths",
        "authorized_actions",
        "excluded_actions",
        "additional_bindings",
        "outcome",
        "reason_codes",
        "scope_hash",
        "authority_granted",
    )
    return all(scope.get(key) == rebuilt.get(key) for key in semantic_keys)


def _entry_shape_valid(entry: object) -> bool:
    if not isinstance(entry, Mapping) or set(entry) - ENTRY_FIELDS or not ENTRY_REQUIRED_FIELDS <= set(entry):
        return False
    if entry.get("gate") not in GATE_ORDER or entry.get("classification") not in ALL_CLASSES:
        return False
    for key in (
        "evidence_key",
        "artifact_role",
        "artifact_type",
        "source_type",
        "target",
        "ref",
        "revision",
        "digest",
    ):
        if not isinstance(entry.get(key), str) or not entry[key]:
            return False
    if not SHA_PATTERN.match(entry["revision"]) or not DIGEST_PATTERN.match(entry["digest"]):
        return False
    if not isinstance(entry.get("required"), bool) or not isinstance(entry.get("source_of_truth"), bool):
        return False
    if entry.get("binding_status") not in {"BOUND", "MISMATCHED", "UNOBSERVED", "NOT_APPLICABLE"}:
        return False
    if entry.get("freshness_status") not in {"FRESH", "STALE", "UNOBSERVED"}:
        return False
    if entry.get("materialization_status") not in {"MATERIALIZED", "MISSING", "UNOBSERVED"}:
        return False
    return _string_list(entry.get("reason_codes"))


def _map_valid(evidence_map: object, task_id: str) -> bool:
    required = {
        "schema_version",
        "artifact_type",
        "task_id",
        "repository",
        "base_sha",
        "head_sha",
        "policy_revision",
        "outcome",
        "reason_codes",
        "entries",
        "requirements",
        "missing_required",
        "stale_required",
        "projection_only",
        "map_digest",
        "authority_granted",
    }
    if not isinstance(evidence_map, Mapping) or set(evidence_map) - MAP_FIELDS or not required <= set(evidence_map):
        return False
    if (
        evidence_map.get("schema_version") != "1.0"
        or evidence_map.get("artifact_type") != "gate-evidence-artifact-map"
        or evidence_map.get("task_id") != task_id
        or evidence_map.get("authority_granted") is not False
    ):
        return False
    if not isinstance(evidence_map.get("repository"), str) or not REPOSITORY_PATTERN.match(evidence_map["repository"]):
        return False
    if not isinstance(evidence_map.get("base_sha"), str) or not SHA_PATTERN.match(evidence_map["base_sha"]):
        return False
    if evidence_map.get("head_sha") is not None and (
        not isinstance(evidence_map["head_sha"], str)
        or not SHA_PATTERN.match(evidence_map["head_sha"])
    ):
        return False
    if not isinstance(evidence_map.get("policy_revision"), str) or not evidence_map["policy_revision"]:
        return False
    reason_codes = evidence_map.get("reason_codes")
    if (
        not _string_list(reason_codes, nonempty=True)
        or any(reason not in EVIDENCE_REASONS for reason in reason_codes)
    ):
        return False
    if evidence_map.get("outcome") not in {"READY", "BLOCKED"}:
        return False
    expected_requirements = sorted(
        _public_requirements(task_id),
        key=lambda item: (str(item["gate"]), str(item["artifact_role"])),
    )
    actual_requirements = evidence_map.get("requirements")
    if not isinstance(actual_requirements, list):
        return False
    try:
        normalized_requirements = sorted(
            actual_requirements,
            key=lambda item: (str(item.get("gate")), str(item.get("artifact_role"))),
        )
    except AttributeError:
        return False
    if normalized_requirements != expected_requirements:
        return False
    entries = evidence_map.get("entries")
    if not isinstance(entries, list) or not all(_entry_shape_valid(entry) for entry in entries):
        return False
    for key in ("missing_required", "stale_required", "projection_only"):
        if not _string_list(evidence_map.get(key)):
            return False
    blockers = set(reason_codes) & EVIDENCE_BLOCKERS
    listed = any(evidence_map[key] for key in ("missing_required", "stale_required", "projection_only"))
    if evidence_map["outcome"] == "READY" and (blockers or listed):
        return False
    if evidence_map["outcome"] == "BLOCKED" and not (blockers or listed):
        return False
    semantic = {
        "task_id": evidence_map["task_id"],
        "repository": evidence_map["repository"],
        "base_sha": evidence_map["base_sha"],
        "head_sha": evidence_map["head_sha"],
        "policy_revision": evidence_map["policy_revision"],
        "requirements": evidence_map["requirements"],
        "entries": sorted(
            evidence_map["entries"],
            key=lambda entry: (str(entry.get("gate")), str(entry.get("evidence_key"))),
        ),
        "missing_required": evidence_map["missing_required"],
        "stale_required": evidence_map["stale_required"],
        "projection_only": evidence_map["projection_only"],
    }
    return (
        isinstance(evidence_map.get("map_digest"), str)
        and evidence_map["map_digest"] == _digest(semantic)
    )


def _transition_valid(transition_map: object) -> bool:
    keys = ("contract_version", "authority", "rules", "terminal_states", "verification")
    return (
        isinstance(transition_map, Mapping)
        and all(key in transition_map for key in keys)
        and hashlib.sha256(
            _canonical_json({key: transition_map[key] for key in keys}).encode("utf-8")
        ).hexdigest()
        == TRANSITION_DIGEST
    )


def _status(entry: Mapping[str, object]) -> str | None:
    for key in ("gate_status", "status", "outcome"):
        if entry.get(key) is not None:
            return str(entry[key]).upper()
    return None


def _entry_policy_valid(
    entry: Mapping[str, object],
    *,
    evidence_map: Mapping[str, object],
    scope_identity: Mapping[str, object],
) -> bool:
    if not _entry_shape_valid(entry):
        return False
    if entry.get("classification") not in CANONICAL_CLASSES:
        return False
    if entry.get("source_of_truth") is not True:
        return False
    if entry.get("materialization_status") != "MATERIALIZED":
        return False
    if entry.get("binding_status") != "BOUND":
        return False
    if entry.get("freshness_status") != "FRESH":
        return False
    if set(entry.get("reason_codes", [])) & EVIDENCE_BLOCKERS:
        return False
    if _status(entry) not in {None, "PASS", "READY", "SUCCESS", "VALID", "COMPLETED"}:
        return False

    target = str(entry["target"])
    if entry.get("evidence_key") != target or entry.get("ref") != target:
        return False
    policy = _requirement_policy(str(evidence_map["task_id"])).get(target)
    if policy is None:
        is_g5_status = (
            entry.get("gate") == "G5_DEPLOY"
            and entry.get("artifact_role") == "status-verification"
            and entry.get("classification") == "DELIVERY_EVIDENCE"
            and entry.get("required") is False
            and entry.get("source_type") == "github_actions"
        )
        if not is_g5_status:
            return False
    else:
        if (
            entry.get("gate") != policy["gate"]
            or entry.get("artifact_role") != policy["artifact_role"]
            or entry.get("classification") != policy["classification"]
            or entry.get("required") is not policy["required"]
        ):
            return False

    head_sha = evidence_map.get("head_sha")
    expected_revision = (
        head_sha
        if head_sha is not None and entry.get("gate") in {
            "G3_PR",
            "G4_MERGE",
            "G5_DEPLOY",
            "G6_PRODUCTION_DATA",
        }
        else evidence_map["base_sha"]
    )
    if entry.get("revision") != expected_revision:
        return False
    if scope_identity.get("head_sha") is not None and head_sha != scope_identity.get("head_sha"):
        return False
    return True


def _analyze_evidence(
    evidence_map: Mapping[str, object],
    scope_identity: Mapping[str, object],
    production_scope: bool,
) -> dict[str, object]:
    entries = evidence_map["entries"]
    requirements = evidence_map["requirements"]
    top_reasons = set(evidence_map["reason_codes"])
    missing = set(evidence_map["missing_required"]) | set(evidence_map["projection_only"])
    stale = set(evidence_map["stale_required"])
    conflicts: set[str] = set()
    binding: set[str] = set()
    valid_refs: set[str] = set()
    seen_digests: dict[str, str] = {}

    for entry in entries:
        target = str(entry["target"])
        codes = set(entry.get("reason_codes", []))
        if _entry_policy_valid(entry, evidence_map=evidence_map, scope_identity=scope_identity):
            valid_refs.add(target)
        else:
            if entry.get("freshness_status") == "STALE" or "EVIDENCE_STALE" in codes:
                stale.add(target)
            elif entry.get("materialization_status") in {"MISSING", "UNOBSERVED"}:
                missing.add(target)
            else:
                binding.add(target)
        if {"EVIDENCE_CONFLICT"} & codes:
            conflicts.add(target)
        if {"EVIDENCE_BINDING_MISMATCH", "EVIDENCE_CI_BINDING_MISMATCH"} & codes:
            binding.add(target)
        key = str(entry["evidence_key"])
        digest = str(entry["digest"])
        if key in seen_digests and seen_digests[key] != digest:
            conflicts.add(key)
        seen_digests[key] = digest

    if "EVIDENCE_CONFLICT" in top_reasons:
        conflicts.add("evidence_map")
    if "EVIDENCE_STALE" in top_reasons and not stale:
        stale.add("evidence_map")
    if top_reasons & {
        "EVIDENCE_REQUIRED_MISSING",
        "EVIDENCE_PROJECTION_ONLY",
        "EVIDENCE_OBSERVABILITY_INCOMPLETE",
    } and not missing:
        missing.add("evidence_map")
    if top_reasons & {"EVIDENCE_BINDING_MISMATCH", "EVIDENCE_CI_BINDING_MISMATCH"}:
        binding.add("evidence_map")

    evaluations: list[dict[str, object]] = []
    first_gate: str | None = None
    first_status: str | None = None
    first_failed = False
    last_passed: str | None = None
    policy = _requirement_policy(str(evidence_map["task_id"]))

    for gate in GATE_ORDER:
        if gate == "G6_PRODUCTION_DATA" and not production_scope:
            evaluations.append({
                "gate": gate,
                "status": "NOT_APPLICABLE",
                "reason_codes": ["GATE_STATE_G6_NOT_APPLICABLE"],
            })
            continue
        required_targets = sorted({
            str(requirement["target"])
            for requirement in requirements
            if requirement["gate"] == gate
            and (requirement["required"] or (production_scope and gate == "G6_PRODUCTION_DATA"))
        })
        gate_entries = [entry for entry in entries if entry["gate"] == gate]
        valid = {
            str(entry["target"])
            for entry in gate_entries
            if _entry_policy_valid(entry, evidence_map=evidence_map, scope_identity=scope_identity)
        }
        running = {
            str(entry["target"])
            for entry in gate_entries
            if _status(entry) in {"RUNNING", "PENDING", "IN_PROGRESS"}
        }
        failed = {
            str(entry["target"])
            for entry in gate_entries
            if _status(entry) in {"FAILED", "FAIL", "ERROR", "BLOCKED"}
        }
        gate_stale = {item for item in stale if item in required_targets or any(str(entry["target"]) == item for entry in gate_entries)}
        gate_conflicts = {item for item in conflicts if item in required_targets or any(str(entry["target"]) == item for entry in gate_entries)}
        gate_binding = {item for item in binding if item in required_targets or any(str(entry["target"]) == item for entry in gate_entries)}
        gate_missing = set(required_targets) - valid - running - failed
        if gate == "G5_DEPLOY" and not required_targets and not (valid or running or failed):
            gate_missing.add("G5_STATUS_VERIFY")
        if gate == "G6_PRODUCTION_DATA" and production_scope and not required_targets and not (valid or running or failed):
            gate_missing.add("G6_PRODUCTION_SCOPE_EVIDENCE")

        if failed:
            status = "FAILED"
        elif gate_conflicts or gate_binding or gate_stale or gate_missing:
            status = "BLOCKED"
        elif running:
            status = "RUNNING"
        else:
            status = "PASS"
        evaluations.append({"gate": gate, "status": status, "reason_codes": []})
        if first_gate is None and status != "PASS":
            first_gate = gate
            first_status = status
            first_failed = bool(failed)
        if first_gate is None:
            last_passed = gate

    later_gate_inheritance = bool(
        first_gate
        and any(
            evaluation["status"] in {"PASS", "RUNNING"}
            for evaluation in evaluations[GATE_ORDER.index(first_gate) + 1 :]
            if evaluation["gate"] != "G6_PRODUCTION_DATA"
        )
    )
    return {
        "evaluations": evaluations,
        "refs": sorted(valid_refs),
        "missing": sorted(missing),
        "stale": sorted(stale),
        "conflicts": sorted(conflicts),
        "binding": sorted(binding),
        "input_invalid": "EVIDENCE_INPUT_INVALID" in top_reasons,
        "first_gate": first_gate,
        "first_status": first_status,
        "first_failed": first_failed,
        "last_passed": last_passed,
        "later": later_gate_inheritance,
    }


def _drift_reasons(
    current_base_sha: str,
    scope_identity: Mapping[str, object],
    evidence_map: Mapping[str, object],
) -> list[str]:
    reasons: list[str] = []
    if scope_identity.get("base_sha") != current_base_sha:
        reasons.append("BASE_SHA_DRIFT")
    if evidence_map.get("base_sha") != current_base_sha:
        reasons.append("EVIDENCE_BASE_SHA_DRIFT")
    scope_head = scope_identity.get("head_sha")
    map_head = evidence_map.get("head_sha")
    if scope_head is not None and map_head != scope_head:
        reasons.append("HEAD_SHA_DRIFT")
    if any(
        entry.get("binding_status") == "MISMATCHED"
        and any("DRIFT" in code or "CI_BINDING" in code for code in entry.get("reason_codes", []))
        for entry in evidence_map["entries"]
    ):
        reasons.append("ENTRY_DRIFT")
    return sorted(set(reasons))


def _projection_warnings(
    projection: object,
    task_id: str,
    repository: str,
    current_gate: str,
    gate_status: str,
    transition_map: Mapping[str, object],
) -> list[str]:
    if projection is None:
        return []
    if not isinstance(projection, Mapping):
        return ["PROJECTION_INVALID"]
    warnings: list[str] = []
    if projection.get("task_id") not in {None, task_id}:
        warnings.append("TASK_ID_MISMATCH")
    if projection.get("repository") not in {None, repository}:
        warnings.append("REPOSITORY_MISMATCH")
    if projection.get("current_gate") not in {None, current_gate}:
        warnings.append("CURRENT_GATE_MISMATCH")
    if projection.get("status") not in {None, gate_status}:
        warnings.append("STATUS_MISMATCH")
    states = {"completed", "cancelled"} | {
        rule["from_state"] for rule in transition_map["rules"]
    } | {
        rule["expected_state"] for rule in transition_map["rules"]
    }
    if projection.get("state") not in states | {None}:
        warnings.append("PROJECTION_STATE_UNKNOWN")
    if projection.get("state") == "cancelled":
        warnings.append("CANCELLED_PROJECTION_WITHOUT_CANONICAL_EVIDENCE")
    return sorted(set(warnings))


def _next_action(reason_codes: list[str], status: str, next_gate: str | None) -> str:
    mapping = (
        ("GATE_STATE_INPUT_INVALID", "FIX_INPUT"),
        ("GATE_STATE_REPLAY_CONFLICT", "STOP_AND_RECONCILE_REPLAY"),
        ("GATE_STATE_BINDING_MISMATCH", "REBUILD_BINDINGS"),
        ("GATE_STATE_EVIDENCE_CONFLICT", "RESOLVE_EVIDENCE_CONFLICT"),
        ("GATE_STATE_GATE_FAILED", "RECOVER_FAILED_GATE"),
        ("GATE_STATE_DRIFT", "REVALIDATE_OR_REAPPROVE"),
        ("GATE_STATE_EVIDENCE_STALE", "REFRESH_EVIDENCE"),
        ("GATE_STATE_REQUIRED_EVIDENCE_MISSING", "MATERIALIZE_REQUIRED_EVIDENCE"),
    )
    for reason, action in mapping:
        if reason in reason_codes:
            return action
    if status == "RUNNING":
        return "WAIT_FOR_GATE_COMPLETION"
    return "COMPLETE" if next_gate is None else "ADVANCE_GATE"


def _empty_resolution(
    task_id: str,
    repository: str,
    current_base_sha: str,
    scope_hash: str | None,
    event_key: str,
    observed_at: str | None,
    resolution_digest: str,
) -> dict[str, object]:
    output: dict[str, object] = {
        "schema_version": "1.0",
        "artifact_type": "gate-state-resolution",
        "task_id": task_id,
        "repository": repository,
        "current_base_sha": current_base_sha,
        "scope_hash": scope_hash,
        "head_sha": None,
        "current_gate": "G0_CONTEXT",
        "gate_status": "BLOCKED",
        "last_passed_gate": None,
        "next_gate": "G0_CONTEXT",
        "next_action_class": "FIX_INPUT",
        "canonical_evidence_refs": [],
        "projection_warnings": [],
        "missing_evidence": [],
        "stale_evidence": [],
        "conflicting_evidence": [],
        "drift_decision": {"status": "NO_DRIFT", "reason_codes": []},
        "primary_reason_code": "GATE_STATE_INPUT_INVALID",
        "reason_codes": ["GATE_STATE_INPUT_INVALID"],
        "event_id_or_idempotency_key": event_key,
        "replay_status": "FIRST_SEEN",
        "resolution_digest": resolution_digest,
        "observed_at": observed_at,
        "gate_evaluations": [],
    }
    output.update({flag: False for flag in AUTHORITY_FLAGS})
    return output


def resolve_gate_state(
    *,
    task_id: str,
    repository: str,
    current_base_sha: str,
    scope_identity: dict[str, object],
    evidence_map: dict[str, object],
    transition_map: dict[str, object],
    task_projection: dict[str, object] | None,
    event_id_or_idempotency_key: str,
    prior_resolution: dict[str, object] | None = None,
    observed_at: str | None = None,
) -> dict[str, object]:
    semantic_input = {
        "task_id": task_id,
        "repository": repository,
        "current_base_sha": current_base_sha,
        "scope_identity": _strip_observation_fields(scope_identity),
        "evidence_map": _strip_observation_fields(evidence_map),
        "transition_map": _strip_observation_fields(transition_map),
        "task_projection": _strip_observation_fields(task_projection),
        "event_id_or_idempotency_key": event_id_or_idempotency_key,
    }
    resolution_digest = _digest(semantic_input)
    scope_hash = scope_identity.get("scope_hash") if isinstance(scope_identity, Mapping) else None
    output = _empty_resolution(
        task_id if isinstance(task_id, str) else "",
        repository if isinstance(repository, str) else "",
        current_base_sha if isinstance(current_base_sha, str) else "",
        scope_hash if isinstance(scope_hash, str) else None,
        event_id_or_idempotency_key if isinstance(event_id_or_idempotency_key, str) else "",
        observed_at,
        resolution_digest,
    )

    if (
        not isinstance(task_id, str)
        or not task_id
        or not isinstance(repository, str)
        or not REPOSITORY_PATTERN.match(repository)
        or not isinstance(current_base_sha, str)
        or not SHA_PATTERN.match(current_base_sha)
        or not _scope_valid(scope_identity)
        or not _map_valid(evidence_map, task_id)
        or not _transition_valid(transition_map)
        or not isinstance(event_id_or_idempotency_key, str)
        or not event_id_or_idempotency_key
        or (prior_resolution is not None and not isinstance(prior_resolution, Mapping))
    ):
        return output

    binding_mismatches: list[str] = []
    if scope_identity.get("task_id") != task_id or scope_identity.get("repository") != repository:
        binding_mismatches.append("scope")
    if evidence_map.get("task_id") != task_id or evidence_map.get("repository") != repository:
        binding_mismatches.append("evidence")
    if prior_resolution and (
        prior_resolution.get("task_id") != task_id
        or prior_resolution.get("repository") != repository
        or prior_resolution.get("scope_hash") != scope_identity.get("scope_hash")
    ):
        binding_mismatches.append("prior")

    production_scope = bool(set(scope_identity["authorized_actions"]) & PRODUCTION_ACTIONS)
    analysis = _analyze_evidence(evidence_map, scope_identity, production_scope)
    output.update({
        "gate_evaluations": analysis["evaluations"],
        "canonical_evidence_refs": analysis["refs"],
        "missing_evidence": analysis["missing"],
        "stale_evidence": analysis["stale"],
        "conflicting_evidence": sorted(set(analysis["conflicts"]) | set(analysis["binding"])),
        "last_passed_gate": analysis["last_passed"],
        "head_sha": scope_identity.get("head_sha"),
    })

    first_gate = analysis["first_gate"]
    if first_gate is None:
        current_gate = "G6_PRODUCTION_DATA"
        gate_status = "PASS" if production_scope else "NOT_APPLICABLE"
        next_gate = None
        if production_scope:
            output["last_passed_gate"] = current_gate
    else:
        current_gate = str(first_gate)
        gate_status = str(analysis["first_status"])
        next_gate = current_gate

    same_event = bool(
        prior_resolution
        and prior_resolution.get("event_id_or_idempotency_key") == event_id_or_idempotency_key
    )
    replay_conflict = bool(
        same_event and prior_resolution.get("resolution_digest") != resolution_digest
    )
    idempotent_replay = bool(
        same_event and prior_resolution.get("resolution_digest") == resolution_digest
    )
    drift = _drift_reasons(current_base_sha, scope_identity, evidence_map)
    reasons: list[str] = []
    if analysis["input_invalid"]:
        reasons.append("GATE_STATE_INPUT_INVALID")
    if replay_conflict:
        reasons.append("GATE_STATE_REPLAY_CONFLICT")
    if binding_mismatches or analysis["binding"]:
        reasons.append("GATE_STATE_BINDING_MISMATCH")
    if analysis["conflicts"]:
        reasons.append("GATE_STATE_EVIDENCE_CONFLICT")
    if analysis["first_failed"]:
        reasons.append("GATE_STATE_GATE_FAILED")
    if drift:
        reasons.append("GATE_STATE_DRIFT")
    if analysis["stale"]:
        reasons.append("GATE_STATE_EVIDENCE_STALE")
    if analysis["missing"]:
        reasons.append("GATE_STATE_REQUIRED_EVIDENCE_MISSING")
    if analysis["later"]:
        reasons.append("GATE_STATE_LATER_GATE_INHERITANCE_REJECTED")
    if not reasons:
        reasons = ["GATE_STATE_RESOLVED"]
        if not production_scope:
            reasons.append("GATE_STATE_G6_NOT_APPLICABLE")

    blockers = {
        "GATE_STATE_INPUT_INVALID",
        "GATE_STATE_REPLAY_CONFLICT",
        "GATE_STATE_BINDING_MISMATCH",
        "GATE_STATE_EVIDENCE_CONFLICT",
        "GATE_STATE_GATE_FAILED",
        "GATE_STATE_DRIFT",
        "GATE_STATE_EVIDENCE_STALE",
        "GATE_STATE_REQUIRED_EVIDENCE_MISSING",
    }
    if set(reasons) & blockers:
        gate_status = "FAILED" if analysis["first_failed"] else "BLOCKED"
        if "GATE_STATE_INPUT_INVALID" in reasons or binding_mismatches:
            current_gate = "G0_CONTEXT"
            output["last_passed_gate"] = None
        elif set(drift) & {"BASE_SHA_DRIFT", "EVIDENCE_BASE_SHA_DRIFT"}:
            current_gate = "G0_CONTEXT"
            output["last_passed_gate"] = None
        elif "HEAD_SHA_DRIFT" in drift:
            current_gate = "G2_EXECUTION"
            output["last_passed_gate"] = "G1_ALIGNMENT"
        next_gate = current_gate

    warnings = _projection_warnings(
        task_projection,
        task_id,
        repository,
        current_gate,
        gate_status,
        transition_map,
    )
    if warnings:
        reasons.append("GATE_STATE_PROJECTION_MISMATCH")
    reasons = _sorted_reason_codes(reasons)
    output.update({
        "current_gate": current_gate,
        "gate_status": gate_status,
        "next_gate": next_gate,
        "projection_warnings": warnings,
        "drift_decision": {
            "status": "REAPPROVE" if drift else "NO_DRIFT",
            "reason_codes": drift,
        },
        "primary_reason_code": reasons[0],
        "reason_codes": reasons,
        "replay_status": (
            "REPLAY_CONFLICT"
            if replay_conflict
            else "IDEMPOTENT_REPLAY"
            if idempotent_replay
            else "FIRST_SEEN"
        ),
    })
    output["next_action_class"] = _next_action(reasons, gate_status, next_gate)
    return output
