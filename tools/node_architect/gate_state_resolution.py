"""Deterministic, replay-safe GWC gate-state resolution for SCRUM-184.

The resolver is pure: it consumes canonical scope/evidence/transition inputs and
returns a closed decision artifact. Jira or other task projections are audit
hints only. No connector call, task mutation, checkpoint write, or authority
action occurs here.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

GATE_ORDER: tuple[str, ...] = (
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION_DATA",
)

GATE_STATUSES = frozenset({"READY", "RUNNING", "PASS", "BLOCKED", "FAILED", "NOT_APPLICABLE"})
CANONICAL_EVIDENCE_CLASSES = frozenset({
    "CANONICAL_AUTHORITY",
    "CANONICAL_GATE_EVIDENCE",
    "DELIVERY_EVIDENCE",
})
PRODUCTION_ACTIONS = frozenset({
    "production_data_read",
    "production_data_write",
    "production_config_change",
    "credential_rotation",
    "migration",
})
BLOCKING_EVIDENCE_REASONS = frozenset({
    "EVIDENCE_INPUT_INVALID",
    "EVIDENCE_BINDING_MISMATCH",
    "EVIDENCE_CONFLICT",
    "EVIDENCE_PROJECTION_ONLY",
    "EVIDENCE_STALE",
    "EVIDENCE_REQUIRED_MISSING",
    "EVIDENCE_OBSERVABILITY_INCOMPLETE",
    "EVIDENCE_CI_BINDING_MISMATCH",
})
REASON_PRECEDENCE: tuple[str, ...] = (
    "GATE_STATE_INPUT_INVALID",
    "GATE_STATE_REPLAY_CONFLICT",
    "GATE_STATE_BINDING_MISMATCH",
    "GATE_STATE_EVIDENCE_CONFLICT",
    "GATE_STATE_DRIFT",
    "GATE_STATE_EVIDENCE_STALE",
    "GATE_STATE_REQUIRED_EVIDENCE_MISSING",
    "GATE_STATE_LATER_GATE_INHERITANCE_REJECTED",
    "GATE_STATE_RESOLVED",
    "GATE_STATE_PROJECTION_MISMATCH",
    "GATE_STATE_G6_NOT_APPLICABLE",
)
AUTHORITY_FLAGS: tuple[str, ...] = (
    "authority_granted",
    "write_authority_granted",
    "pr_authority_granted",
    "merge_authority_granted",
    "deployment_authority_granted",
    "production_authority_granted",
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
_OBSERVATION_KEYS = frozenset({
    "observed_at",
    "mapped_at",
    "calculated_at",
    "generated_at",
    "updated_at",
    "created_at",
    "decision_digest",
    "resolution_digest",
    "map_digest",
})


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _strip_observation_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_observation_fields(item)
            for key, item in value.items()
            if str(key) not in _OBSERVATION_KEYS
        }
    if isinstance(value, list):
        return [_strip_observation_fields(item) for item in value]
    return value


def _sorted_unique(values: Sequence[Any] | None) -> list[str]:
    return sorted({str(value) for value in (values or []) if isinstance(value, str) and value})


def _reason_sort(codes: Sequence[str]) -> list[str]:
    unique = list(dict.fromkeys(codes))
    return sorted(
        unique,
        key=lambda code: (
            REASON_PRECEDENCE.index(code) if code in REASON_PRECEDENCE else len(REASON_PRECEDENCE),
            code,
        ),
    )


def _valid_transition_map(transition_map: Mapping[str, Any]) -> bool:
    rules = transition_map.get("rules")
    terminal_states = transition_map.get("terminal_states")
    if not isinstance(rules, list) or not rules:
        return False
    if not isinstance(terminal_states, list) or not all(isinstance(item, str) and item for item in terminal_states):
        return False
    required = {"outcome", "from_state", "transition", "expected_state"}
    for rule in rules:
        if not isinstance(rule, Mapping) or not required.issubset(rule):
            return False
        if any(not isinstance(rule[key], str) or not rule[key] for key in required):
            return False
    return True


def _production_scope(scope_identity: Mapping[str, Any]) -> bool:
    actions = scope_identity.get("authorized_actions", [])
    return isinstance(actions, list) and bool(set(actions) & PRODUCTION_ACTIONS)


def _entry_gate(entry: Mapping[str, Any]) -> str:
    gate = str(entry.get("gate", ""))
    return gate if gate in GATE_ORDER else ""


def _entry_ref(entry: Mapping[str, Any]) -> str | None:
    for key in ("ref", "target", "evidence_key"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _entry_reason_codes(entry: Mapping[str, Any]) -> set[str]:
    raw = entry.get("reason_codes", [])
    return {str(item) for item in raw} if isinstance(raw, list) else set()


def _entry_is_stale(entry: Mapping[str, Any]) -> bool:
    freshness = str(entry.get("freshness_status", "")).upper()
    return freshness == "STALE" or "EVIDENCE_STALE" in _entry_reason_codes(entry)


def _entry_is_conflicting(entry: Mapping[str, Any]) -> bool:
    return "EVIDENCE_CONFLICT" in _entry_reason_codes(entry)


def _entry_is_running(entry: Mapping[str, Any]) -> bool:
    status = str(entry.get("gate_status", entry.get("status", entry.get("outcome", "")))).upper()
    return status in {"RUNNING", "PENDING", "IN_PROGRESS"}


def _entry_is_failed(entry: Mapping[str, Any]) -> bool:
    status = str(entry.get("gate_status", entry.get("status", entry.get("outcome", "")))).upper()
    return status in {"FAILED", "FAIL", "ERROR"}


def _entry_is_valid(entry: Mapping[str, Any]) -> bool:
    classification = str(entry.get("classification", ""))
    source_of_truth = entry.get("source_of_truth")
    if classification and classification not in CANONICAL_EVIDENCE_CLASSES:
        return False
    if source_of_truth is False:
        return False
    material = str(entry.get("materialization_status", "MATERIALIZED")).upper()
    if material not in {"MATERIALIZED", "PRESENT", "AVAILABLE", "VALID"}:
        return False
    binding = str(entry.get("binding_status", "MATCHED")).upper()
    if binding not in {"MATCHED", "EXACT", "VALID", "BOUND", "CONFIRMED"}:
        return False
    freshness = str(entry.get("freshness_status", "FRESH")).upper()
    if freshness not in {"FRESH", "CURRENT", "VALID"}:
        return False
    if _entry_reason_codes(entry) & BLOCKING_EVIDENCE_REASONS:
        return False
    if _entry_is_running(entry) or _entry_is_failed(entry):
        return False
    return True


def _requirements(evidence_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = evidence_map.get("requirements", [])
    requirements: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            gate = str(item.get("gate", ""))
            target = item.get("target")
            if gate in GATE_ORDER and isinstance(target, str) and target:
                requirements.append({
                    "gate": gate,
                    "target": target,
                    "required": bool(item.get("required", True)),
                })
    if requirements:
        return requirements
    entries = evidence_map.get("entries", [])
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, Mapping) or not bool(entry.get("required", False)):
                continue
            gate = _entry_gate(entry)
            target = _entry_ref(entry)
            if gate and target:
                requirements.append({"gate": gate, "target": target, "required": True})
    return requirements


def _binding_errors(
    *,
    task_id: str,
    repository: str,
    scope_identity: Mapping[str, Any],
    evidence_map: Mapping[str, Any],
    prior_resolution: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    scope_hash = scope_identity.get("scope_hash")
    if scope_identity.get("task_id") != task_id or scope_identity.get("repository") != repository:
        errors.append("scope_identity")
    if evidence_map.get("task_id") != task_id or evidence_map.get("repository") != repository:
        errors.append("evidence_map")
    evidence_scope_hash = evidence_map.get("scope_hash")
    if evidence_scope_hash is not None and evidence_scope_hash != scope_hash:
        errors.append("scope_hash")
    if prior_resolution is not None:
        if prior_resolution.get("task_id") != task_id or prior_resolution.get("repository") != repository:
            errors.append("prior_resolution")
        if prior_resolution.get("scope_hash") != scope_hash:
            errors.append("prior_scope_hash")
    return errors


def _drift_reasons(
    *,
    current_base_sha: str,
    scope_identity: Mapping[str, Any],
    evidence_map: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    scope_base = scope_identity.get("base_sha")
    evidence_base = evidence_map.get("base_sha")
    if scope_base != current_base_sha:
        reasons.append("BASE_SHA_DRIFT")
    if evidence_base != current_base_sha:
        reasons.append("EVIDENCE_BASE_SHA_DRIFT")
    scope_head = scope_identity.get("head_sha")
    evidence_head = evidence_map.get("head_sha")
    if scope_head and evidence_head and scope_head != evidence_head:
        reasons.append("HEAD_SHA_DRIFT")
    entries = evidence_map.get("entries", [])
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            binding = str(entry.get("binding_status", "")).upper()
            codes = _entry_reason_codes(entry)
            if binding == "MISMATCHED" and any("DRIFT" in code or "CI_BINDING" in code for code in codes):
                ref = _entry_ref(entry) or "unknown"
                reasons.append(f"ENTRY_DRIFT:{ref}")
    return sorted(set(reasons))


def _evidence_analysis(evidence_map: Mapping[str, Any], production_scope: bool) -> dict[str, Any]:
    entries_raw = evidence_map.get("entries", [])
    entries = [entry for entry in entries_raw if isinstance(entry, Mapping)] if isinstance(entries_raw, list) else []
    requirements = _requirements(evidence_map)

    missing = set(_sorted_unique(evidence_map.get("missing_required", [])))
    stale = set(_sorted_unique(evidence_map.get("stale_required", [])))
    conflicting = set(_sorted_unique(evidence_map.get("conflicting_evidence", [])))
    canonical_refs: set[str] = set()

    seen: dict[str, str] = {}
    for entry in entries:
        ref = _entry_ref(entry)
        if ref and _entry_is_valid(entry):
            canonical_refs.add(ref)
        if ref and _entry_is_stale(entry):
            stale.add(ref)
        if ref and _entry_is_conflicting(entry):
            conflicting.add(ref)
        key = str(entry.get("evidence_key", ref or ""))
        digest = str(entry.get("digest", ""))
        if key:
            previous = seen.get(key)
            if previous is not None and previous != digest:
                conflicting.add(key)
            seen[key] = digest

    top_reasons = set(_sorted_unique(evidence_map.get("reason_codes", [])))
    if "EVIDENCE_CONFLICT" in top_reasons:
        conflicting.add("evidence_map")

    evaluations: list[dict[str, Any]] = []
    last_passed: str | None = None
    first_unresolved: str | None = None
    first_status: str | None = None
    first_missing: list[str] = []
    first_stale: list[str] = []
    first_conflicts: list[str] = []

    for gate in GATE_ORDER:
        if gate == "G6_PRODUCTION_DATA" and not production_scope:
            evaluations.append({
                "gate": gate,
                "status": "NOT_APPLICABLE",
                "required_refs": [],
                "valid_refs": [],
            })
            continue

        gate_requirements = [item for item in requirements if item["gate"] == gate and item["required"]]
        required_refs = sorted({str(item["target"]) for item in gate_requirements})
        gate_entries = [entry for entry in entries if _entry_gate(entry) == gate]
        valid_refs = sorted({ref for entry in gate_entries if _entry_is_valid(entry) for ref in [_entry_ref(entry)] if ref})
        running_refs = sorted({ref for entry in gate_entries if _entry_is_running(entry) for ref in [_entry_ref(entry)] if ref})
        failed_refs = sorted({ref for entry in gate_entries if _entry_is_failed(entry) for ref in [_entry_ref(entry)] if ref})
        gate_stale = sorted({ref for ref in stale if ref in required_refs or any(_entry_ref(entry) == ref for entry in gate_entries)})
        gate_conflicts = sorted({ref for ref in conflicting if ref in required_refs or any(_entry_ref(entry) == ref for entry in gate_entries)})
        gate_missing = sorted(set(required_refs) - set(valid_refs) - set(running_refs) - set(failed_refs))

        if gate == "G5_DEPLOY" and not required_refs:
            status_refs = [entry for entry in gate_entries if _entry_is_valid(entry)]
            if not status_refs and not running_refs and not failed_refs:
                gate_missing = ["G5_STATUS_VERIFY"]
            elif status_refs:
                valid_refs = sorted({ref for entry in status_refs for ref in [_entry_ref(entry)] if ref})
        if gate == "G6_PRODUCTION_DATA" and production_scope and not required_refs:
            production_refs = [entry for entry in gate_entries if _entry_is_valid(entry)]
            if not production_refs and not running_refs and not failed_refs:
                gate_missing = ["G6_PRODUCTION_SCOPE_EVIDENCE"]
            elif production_refs:
                valid_refs = sorted({ref for entry in production_refs for ref in [_entry_ref(entry)] if ref})

        if failed_refs:
            status = "FAILED"
        elif gate_conflicts or gate_stale or gate_missing:
            status = "BLOCKED"
        elif running_refs:
            status = "RUNNING"
        else:
            status = "PASS"

        evaluations.append({
            "gate": gate,
            "status": status,
            "required_refs": required_refs,
            "valid_refs": valid_refs,
            "running_refs": running_refs,
            "failed_refs": failed_refs,
            "missing_refs": gate_missing,
            "stale_refs": gate_stale,
            "conflicting_refs": gate_conflicts,
        })
        if first_unresolved is None and status != "PASS":
            first_unresolved = gate
            first_status = status
            first_missing = gate_missing
            first_stale = gate_stale
            first_conflicts = gate_conflicts
        if first_unresolved is None and status == "PASS":
            last_passed = gate

    later_valid = False
    if first_unresolved:
        start = GATE_ORDER.index(first_unresolved) + 1
        for evaluation in evaluations[start:]:
            if evaluation["status"] in {"PASS", "RUNNING"} and evaluation.get("valid_refs"):
                later_valid = True
                break

    return {
        "gate_evaluations": evaluations,
        "last_passed_gate": last_passed,
        "first_unresolved_gate": first_unresolved,
        "first_status": first_status,
        "first_missing": first_missing,
        "first_stale": first_stale,
        "first_conflicts": first_conflicts,
        "later_valid_evidence": later_valid,
        "canonical_evidence_refs": sorted(canonical_refs),
        "missing_evidence": sorted(missing | set(first_missing)),
        "stale_evidence": sorted(stale | set(first_stale)),
        "conflicting_evidence": sorted(conflicting | set(first_conflicts)),
    }


def _projection_warnings(
    task_projection: Mapping[str, Any] | None,
    *,
    task_id: str,
    repository: str,
    canonical_gate: str,
    canonical_status: str,
    transition_map: Mapping[str, Any],
) -> list[str]:
    if not task_projection:
        return []
    warnings: list[str] = []
    if task_projection.get("task_id") not in (None, task_id):
        warnings.append("TASK_ID_MISMATCH")
    if task_projection.get("repository") not in (None, repository):
        warnings.append("REPOSITORY_MISMATCH")
    projected_gate = task_projection.get("current_gate", task_projection.get("gate"))
    projected_status = task_projection.get("gate_status", task_projection.get("status"))
    if projected_gate is not None and projected_gate != canonical_gate:
        warnings.append("CURRENT_GATE_MISMATCH")
    if projected_status is not None and str(projected_status).upper() != canonical_status:
        warnings.append("GATE_STATUS_MISMATCH")
    projected_state = str(task_projection.get("state", ""))
    known_states = set(str(item) for item in transition_map.get("terminal_states", []))
    for rule in transition_map.get("rules", []):
        if isinstance(rule, Mapping):
            known_states.add(str(rule.get("from_state", "")))
            known_states.add(str(rule.get("expected_state", "")))
    if projected_state and projected_state not in known_states:
        warnings.append("PROJECTION_STATE_UNKNOWN")
    terminal = str(task_projection.get("terminal_state", projected_state)).lower()
    if terminal in {"cancelled", "canceled"}:
        warnings.append("CANCELLED_PROJECTION_WITHOUT_CANONICAL_EVIDENCE")
    return sorted(set(warnings))


def _next_action(reason_codes: Sequence[str], status: str, next_gate: str | None) -> str:
    code_set = set(reason_codes)
    if "GATE_STATE_INPUT_INVALID" in code_set:
        return "FIX_INPUT"
    if "GATE_STATE_REPLAY_CONFLICT" in code_set:
        return "STOP_REPLAY_CONFLICT"
    if "GATE_STATE_BINDING_MISMATCH" in code_set:
        return "REVALIDATE_BINDINGS"
    if "GATE_STATE_EVIDENCE_CONFLICT" in code_set:
        return "RECONCILE_EVIDENCE"
    if "GATE_STATE_DRIFT" in code_set:
        return "REVALIDATE_OR_REAPPROVE"
    if "GATE_STATE_EVIDENCE_STALE" in code_set:
        return "REFRESH_EVIDENCE"
    if "GATE_STATE_REQUIRED_EVIDENCE_MISSING" in code_set:
        return "MATERIALIZE_REQUIRED_EVIDENCE"
    if status == "RUNNING":
        return "WAIT_FOR_GATE_COMPLETION"
    if status == "FAILED":
        return "REPAIR_GATE_FAILURE"
    if next_gate is None:
        return "COMPLETE"
    return "ADVANCE_GATE"


def _base_output(
    *,
    task_id: str,
    repository: str,
    current_base_sha: str,
    scope_hash: str | None,
    event_id_or_idempotency_key: str,
    observed_at: str | None,
    resolution_digest: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
        "event_id_or_idempotency_key": event_id_or_idempotency_key,
        "replay_status": "FIRST_SEEN",
        "resolution_digest": resolution_digest,
        "observed_at": observed_at,
        "gate_evaluations": [],
    }
    payload.update({flag: False for flag in AUTHORITY_FLAGS})
    return payload


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
    """Resolve the current GWC gate without granting or executing authority."""
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
    output = _base_output(
        task_id=task_id if isinstance(task_id, str) else "",
        repository=repository if isinstance(repository, str) else "",
        current_base_sha=current_base_sha if isinstance(current_base_sha, str) else "",
        scope_hash=scope_hash if isinstance(scope_hash, str) else None,
        event_id_or_idempotency_key=(
            event_id_or_idempotency_key if isinstance(event_id_or_idempotency_key, str) else ""
        ),
        observed_at=observed_at,
        resolution_digest=resolution_digest,
    )

    input_invalid = any([
        not isinstance(task_id, str) or not task_id,
        not isinstance(repository, str) or not _REPO_RE.match(repository),
        not isinstance(current_base_sha, str) or not _SHA_RE.match(current_base_sha),
        not isinstance(scope_identity, Mapping),
        not isinstance(evidence_map, Mapping),
        not isinstance(transition_map, Mapping) or not _valid_transition_map(transition_map),
        not isinstance(event_id_or_idempotency_key, str) or not event_id_or_idempotency_key,
        prior_resolution is not None and not isinstance(prior_resolution, Mapping),
        scope_identity.get("outcome") != "READY" if isinstance(scope_identity, Mapping) else True,
        not isinstance(scope_hash, str) or not _SCOPE_HASH_RE.match(scope_hash),
    ])
    if input_invalid:
        return output

    binding_errors = _binding_errors(
        task_id=task_id,
        repository=repository,
        scope_identity=scope_identity,
        evidence_map=evidence_map,
        prior_resolution=prior_resolution,
    )

    production_scope = _production_scope(scope_identity)
    analysis = _evidence_analysis(evidence_map, production_scope)
    output["gate_evaluations"] = analysis["gate_evaluations"]
    output["canonical_evidence_refs"] = analysis["canonical_evidence_refs"]
    output["missing_evidence"] = analysis["missing_evidence"]
    output["stale_evidence"] = analysis["stale_evidence"]
    output["conflicting_evidence"] = analysis["conflicting_evidence"]
    output["last_passed_gate"] = analysis["last_passed_gate"]
    output["head_sha"] = scope_identity.get("head_sha")

    unresolved_gate = analysis["first_unresolved_gate"]
    if unresolved_gate is None:
        if not production_scope:
            current_gate = "G6_PRODUCTION_DATA"
            status = "NOT_APPLICABLE"
            next_gate = None
        else:
            current_gate = "G6_PRODUCTION_DATA"
            status = "PASS"
            next_gate = None
            output["last_passed_gate"] = "G6_PRODUCTION_DATA"
    else:
        current_gate = unresolved_gate
        status = str(analysis["first_status"] or "BLOCKED")
        next_gate = unresolved_gate

    replay_same_key = bool(
        prior_resolution
        and prior_resolution.get("event_id_or_idempotency_key") == event_id_or_idempotency_key
    )
    replay_conflict = bool(
        replay_same_key and prior_resolution.get("resolution_digest") != resolution_digest
    )
    replay_idempotent = bool(
        replay_same_key and prior_resolution.get("resolution_digest") == resolution_digest
    )

    drift_reasons = _drift_reasons(
        current_base_sha=current_base_sha,
        scope_identity=scope_identity,
        evidence_map=evidence_map,
    )
    reasons: list[str] = []
    if replay_conflict:
        reasons.append("GATE_STATE_REPLAY_CONFLICT")
    if binding_errors:
        reasons.append("GATE_STATE_BINDING_MISMATCH")
    if analysis["conflicting_evidence"]:
        reasons.append("GATE_STATE_EVIDENCE_CONFLICT")
    if drift_reasons:
        reasons.append("GATE_STATE_DRIFT")
    if analysis["stale_evidence"]:
        reasons.append("GATE_STATE_EVIDENCE_STALE")
    if analysis["missing_evidence"]:
        reasons.append("GATE_STATE_REQUIRED_EVIDENCE_MISSING")
    if analysis["later_valid_evidence"]:
        reasons.append("GATE_STATE_LATER_GATE_INHERITANCE_REJECTED")

    if not reasons:
        reasons.append("GATE_STATE_RESOLVED")
        if not production_scope:
            reasons.append("GATE_STATE_G6_NOT_APPLICABLE")

    blocking = set(reasons) & {
        "GATE_STATE_REPLAY_CONFLICT",
        "GATE_STATE_BINDING_MISMATCH",
        "GATE_STATE_EVIDENCE_CONFLICT",
        "GATE_STATE_DRIFT",
        "GATE_STATE_EVIDENCE_STALE",
        "GATE_STATE_REQUIRED_EVIDENCE_MISSING",
    }
    if blocking:
        status = "BLOCKED" if status != "FAILED" else "FAILED"
        if binding_errors:
            current_gate = "G0_CONTEXT"
            output["last_passed_gate"] = None
        elif drift_reasons:
            if any(reason in {"BASE_SHA_DRIFT", "EVIDENCE_BASE_SHA_DRIFT"} for reason in drift_reasons):
                current_gate = "G0_CONTEXT"
                output["last_passed_gate"] = None
            else:
                current_gate = "G2_EXECUTION"
                output["last_passed_gate"] = "G1_ALIGNMENT"
        elif current_gate == "G6_PRODUCTION_DATA" and output["last_passed_gate"]:
            current_gate = GATE_ORDER[min(GATE_ORDER.index(str(output["last_passed_gate"])) + 1, len(GATE_ORDER) - 1)]
        next_gate = current_gate

    projection_warnings = _projection_warnings(
        task_projection,
        task_id=task_id,
        repository=repository,
        canonical_gate=current_gate,
        canonical_status=status,
        transition_map=transition_map,
    )
    if projection_warnings:
        reasons.append("GATE_STATE_PROJECTION_MISMATCH")

    sorted_reasons = _reason_sort(reasons)
    output.update({
        "current_gate": current_gate,
        "gate_status": status if status in GATE_STATUSES else "BLOCKED",
        "next_gate": next_gate,
        "projection_warnings": projection_warnings,
        "drift_decision": {
            "status": "REAPPROVE" if drift_reasons else "NO_DRIFT",
            "reason_codes": drift_reasons,
        },
        "primary_reason_code": sorted_reasons[0],
        "reason_codes": sorted_reasons,
        "replay_status": (
            "REPLAY_CONFLICT" if replay_conflict
            else "IDEMPOTENT_REPLAY" if replay_idempotent
            else "FIRST_SEEN"
        ),
    })
    output["next_action_class"] = _next_action(
        output["reason_codes"], str(output["gate_status"]), output["next_gate"]
    )
    return output
