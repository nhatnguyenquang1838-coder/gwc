"""Pure, deterministic gate/action to evidence-artifact mapping (SCRUM-312).

The evaluator describes the proof required for a current gate/action.  It does
not read or mutate external state, infer a gate PASS, or grant authority.  The
caller supplies materialization, schema, freshness, and identity readbacks;
this module validates those readbacks and emits typed gaps.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


EVIDENCE_CLASSES = frozenset(
    {
        "CANONICAL_AUTHORITY",
        "CANONICAL_GATE_EVIDENCE",
        "DELIVERY_EVIDENCE",
        "AUDIT_PROJECTION",
        "RESUME_HINT",
    }
)
PROJECTION_SOURCE_TYPES = frozenset(
    {"jira_comment", "slack_message", "notion_page", "dashboard", "chat_message"}
)
GATES = frozenset(
    {
        "G0_CONTEXT",
        "G1_ALIGNMENT",
        "G2_EXECUTION",
        "G3_PR",
        "G4_MERGE",
        "G5_DEPLOY",
        "G6_PRODUCTION_DATA",
    }
)
_HEAD_BOUND_GATES = frozenset(
    {"G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"}
)

# The action vocabulary is deliberately broader than this node's own use so a
# caller can resolve the same canonical map at every gate boundary.
ACTION_TO_GATE = {
    "capture_context": "G0_CONTEXT",
    "align_task": "G1_ALIGNMENT",
    "resolve_gate_state": "G1_ALIGNMENT",
    "resolve_evidence_map": "G2_EXECUTION",
    "create_guarded_branch_or_worktree": "G2_EXECUTION",
    "modify_approved_files": "G2_EXECUTION",
    "run_sandboxed_validation": "G2_EXECUTION",
    "stage": "G2_EXECUTION",
    "create_commit": "G2_EXECUTION",
    "push_working_branch": "G2_EXECUTION",
    "open_draft_pr": "G3_PR",
    "mark_pr_ready": "G3_PR",
    "merge_pre_prod": "G4_MERGE",
    "verify_post_merge_ci": "G5_DEPLOY",
    "deploy": "G5_DEPLOY",
    "production_data_change": "G6_PRODUCTION_DATA",
}

_GATE_REQUIREMENTS: tuple[dict[str, str], ...] = (
    {
        "gate": "G0_CONTEXT",
        "artifact_role": "context-snapshot",
        "target": ".gwc/tasks/<task-id>/g0/context-snapshot.yaml",
        "class_": "CANONICAL_GATE_EVIDENCE",
        "required": "true",
    },
    {
        "gate": "G1_ALIGNMENT",
        "artifact_role": "intake",
        "target": ".gwc/tasks/<task-id>/g1/intake/g1-intake-brief.yaml",
        "class_": "CANONICAL_GATE_EVIDENCE",
        "required": "true",
    },
    {
        "gate": "G1_ALIGNMENT",
        "artifact_role": "preflight",
        "target": ".gwc/tasks/<task-id>/g1/preflight/g1-preflight-report.yaml",
        "class_": "CANONICAL_GATE_EVIDENCE",
        "required": "true",
    },
    {
        "gate": "G1_ALIGNMENT",
        "artifact_role": "options",
        "target": ".gwc/tasks/<task-id>/g1/brainstorming/g1-options.yaml",
        "class_": "CANONICAL_GATE_EVIDENCE",
        "required": "true",
    },
    {
        "gate": "G1_ALIGNMENT",
        "artifact_role": "decision",
        "target": ".gwc/tasks/<task-id>/g1/decision/g1-decision-record.yaml",
        "class_": "CANONICAL_GATE_EVIDENCE",
        "required": "true",
    },
    {
        "gate": "G2_EXECUTION",
        "artifact_role": "execution-envelope",
        "target": ".gwc/tasks/<task-id>/g2/execution-envelope.yaml",
        "class_": "CANONICAL_AUTHORITY",
        "required": "true",
    },
    {
        "gate": "G3_PR",
        "artifact_role": "delivery-record",
        "target": ".gwc/tasks/<task-id>/g3/delivery-record.yaml",
        "class_": "DELIVERY_EVIDENCE",
        "required": "true",
    },
    {
        "gate": "G4_MERGE",
        "artifact_role": "merge-approval",
        "target": ".gwc/tasks/<task-id>/g4/merge-approval.yaml",
        "class_": "CANONICAL_AUTHORITY",
        "required": "true",
    },
    {
        "gate": "G5_DEPLOY",
        "artifact_role": "deployment-approval",
        "target": ".gwc/tasks/<task-id>/g5/deployment-approval.yaml",
        "class_": "CANONICAL_AUTHORITY",
        "required": "false",
    },
    {
        "gate": "G6_PRODUCTION_DATA",
        "artifact_role": "production-approval",
        "target": ".gwc/tasks/<task-id>/g6/production-approval.yaml",
        "class_": "CANONICAL_AUTHORITY",
        "required": "false",
    },
)

_REASON_PRECEDENCE = [
    "EVIDENCE_INPUT_INVALID",
    "EVIDENCE_BINDING_MISMATCH",
    "EVIDENCE_CONFLICT",
    "EVIDENCE_PROJECTION_ONLY",
    "EVIDENCE_STALE",
    "EVIDENCE_REQUIRED_MISSING",
    "EVIDENCE_OBSERVABILITY_INCOMPLETE",
    "EVIDENCE_CI_BINDING_MISMATCH",
    "EVIDENCE_G6_NOT_APPLICABLE",
]


def _canonical_json_bytes(model: Mapping[str, Any]) -> bytes:
    return json.dumps(
        model, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(char in "0123456789abcdef" for char in value)
    )


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _sort_reasons(reasons: set[str]) -> list[str]:
    return sorted(
        reasons,
        key=lambda reason: (
            _REASON_PRECEDENCE.index(reason)
            if reason in _REASON_PRECEDENCE
            else len(_REASON_PRECEDENCE),
            reason,
        ),
    )


def _requirements_for(
    *, task_id: str, current_gate: str | None, current_action: str | None
) -> tuple[list[dict[str, object]], bool]:
    """Return the exact current gate/action requirements and whether filtered."""
    filtered = current_gate is not None or current_action is not None
    if current_gate is not None and current_gate not in GATES:
        return [], filtered
    if current_action is not None and (
        not isinstance(current_action, str) or current_action not in ACTION_TO_GATE
    ):
        return [], filtered
    if current_action is not None and current_gate != ACTION_TO_GATE[current_action]:
        return [], filtered
    selected_gate = current_gate or (
        ACTION_TO_GATE[current_action] if current_action is not None else None
    )
    requirements: list[dict[str, object]] = []
    for requirement in _GATE_REQUIREMENTS:
        if selected_gate is not None and requirement["gate"] != selected_gate:
            continue
        target = requirement["target"].replace("<task-id>", task_id or "<task-id>")
        requirements.append(
            {
                "gate": requirement["gate"],
                "artifact_role": requirement["artifact_role"],
                "target": target,
                "required": requirement["required"] == "true",
            }
        )
    return requirements, filtered


def build_gate_evidence_artifact_map(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    evidence_candidates: list[dict[str, object]],
    policy_revision: str,
    head_sha: str | None = None,
    mapped_at: str | None = None,
    current_gate: str | None = None,
    current_action: str | None = None,
    scope_hash: str | None = None,
    scope_identity: Mapping[str, object] | None = None,
    observed_base_sha: str | None = None,
    observed_head_sha: str | None = None,
) -> dict[str, object]:
    """Build a deterministic map; no result from this function grants authority."""
    reasons: set[str] = set()

    if not isinstance(task_id, str) or not task_id.strip():
        reasons.add("EVIDENCE_INPUT_INVALID")
    if not isinstance(repository, str) or not repository.strip() or repository.count("/") != 1:
        reasons.add("EVIDENCE_INPUT_INVALID")
    if not _valid_sha(base_sha):
        reasons.add("EVIDENCE_INPUT_INVALID")
    if head_sha is not None and not _valid_sha(head_sha):
        reasons.add("EVIDENCE_INPUT_INVALID")
    if not isinstance(policy_revision, str) or not policy_revision.strip():
        reasons.add("EVIDENCE_INPUT_INVALID")
    if not isinstance(evidence_candidates, list):
        reasons.add("EVIDENCE_INPUT_INVALID")
    if scope_hash is not None and (not isinstance(scope_hash, str) or not _valid_digest(scope_hash)):
        reasons.add("EVIDENCE_INPUT_INVALID")
    if scope_identity is not None:
        if not isinstance(scope_identity, Mapping):
            reasons.add("EVIDENCE_INPUT_INVALID")
        elif scope_hash is None:
            scope_hash = scope_identity.get("scope_hash")  # type: ignore[assignment]
            if not _valid_digest(scope_hash):
                reasons.add("EVIDENCE_INPUT_INVALID")
    for observed in (observed_base_sha, observed_head_sha):
        if observed is not None and not _valid_sha(observed):
            reasons.add("EVIDENCE_INPUT_INVALID")
    if observed_base_sha is not None and observed_base_sha != base_sha:
        reasons.add("EVIDENCE_BINDING_MISMATCH")
    if observed_head_sha is not None and observed_head_sha != head_sha:
        reasons.add("EVIDENCE_BINDING_MISMATCH")

    requirements, filtered = _requirements_for(
        task_id=task_id, current_gate=current_gate, current_action=current_action
    )
    if (current_gate is not None and current_gate not in GATES) or (
        current_action is not None
        and (not isinstance(current_action, str) or current_action not in ACTION_TO_GATE)
    ) or (
        current_action is not None
        and current_gate != ACTION_TO_GATE.get(current_action)
    ):
        reasons.add("EVIDENCE_INPUT_INVALID")

    requirement_policy = {
        str(item["target"]): {
            **item,
            "classification": next(
                requirement["class_"]
                for requirement in _GATE_REQUIREMENTS
                if requirement["gate"] == item["gate"]
                and requirement["artifact_role"] == item["artifact_role"]
            ),
        }
        for item in requirements
    }

    norm_candidates: list[Mapping[str, object]] = []
    if isinstance(evidence_candidates, list):
        for candidate in evidence_candidates:
            if not isinstance(candidate, Mapping):
                reasons.add("EVIDENCE_INPUT_INVALID")
                continue
            norm_candidates.append(candidate)

    if not filtered and not any(
        candidate.get("gate") == "G6_PRODUCTION_DATA" for candidate in norm_candidates
    ):
        reasons.add("EVIDENCE_G6_NOT_APPLICABLE")

    seen_digests: dict[object, object] = {}
    for candidate in norm_candidates:
        key = candidate.get("evidence_key")
        digest = candidate.get("digest")
        if not isinstance(key, str) or not key:
            reasons.add("EVIDENCE_INPUT_INVALID")
            continue
        if key in seen_digests and seen_digests[key] != digest:
            reasons.add("EVIDENCE_CONFLICT")
        seen_digests[key] = digest

    entries: list[dict[str, object]] = []
    matched_targets: set[str] = set()
    for candidate in norm_candidates:
        gate = candidate.get("gate")
        classification = candidate.get("classification")
        source_type = candidate.get("source_type")
        target = candidate.get("target")
        reference = candidate.get("ref")
        evidence_key = candidate.get("evidence_key")
        revision = candidate.get("revision")
        digest = candidate.get("digest")
        artifact_role = candidate.get("artifact_role")
        artifact_type = candidate.get("artifact_type")
        required = candidate.get("required")
        materialization = candidate.get("materialization_status", "UNOBSERVED")
        freshness = candidate.get("freshness_status", "UNOBSERVED")
        binding = candidate.get("binding_status", "UNOBSERVED")
        raw_source_of_truth = candidate.get("source_of_truth")
        schema_valid = candidate.get("schema_valid", True)
        availability = candidate.get("availability_status", "AVAILABLE")

        source_of_truth = raw_source_of_truth if isinstance(raw_source_of_truth, bool) else False
        entry_reasons: set[str] = set()
        is_projection_source = source_type in PROJECTION_SOURCE_TYPES
        is_canonical_class = classification in {
            "CANONICAL_AUTHORITY",
            "CANONICAL_GATE_EVIDENCE",
            "DELIVERY_EVIDENCE",
        }
        required_strings = (
            evidence_key,
            gate,
            artifact_role,
            artifact_type,
            classification,
            source_type,
            target,
            reference,
            revision,
            digest,
        )
        structural_invalid = (
            any(not isinstance(value, str) or not value for value in required_strings)
            or not isinstance(required, bool)
            or not isinstance(raw_source_of_truth, bool)
            or classification not in EVIDENCE_CLASSES
            or not _valid_sha(revision)
            or not _valid_digest(digest)
            or binding not in {"BOUND", "MISMATCHED", "UNOBSERVED", "NOT_APPLICABLE"}
            or freshness not in {"FRESH", "STALE", "UNOBSERVED"}
            or materialization not in {"MATERIALIZED", "MISSING", "UNOBSERVED"}
            or not isinstance(schema_valid, bool)
            or availability not in {"AVAILABLE", "UNAVAILABLE"}
        )
        if structural_invalid or schema_valid is False:
            reasons.add("EVIDENCE_INPUT_INVALID")
            entry_reasons.add("EVIDENCE_INPUT_INVALID")
        if is_projection_source and is_canonical_class:
            entry_reasons.add("EVIDENCE_PROJECTION_ONLY")
        if binding == "MISMATCHED":
            entry_reasons.add("EVIDENCE_BINDING_MISMATCH")
        if freshness == "STALE":
            entry_reasons.add("EVIDENCE_STALE")
        if materialization == "MISSING":
            entry_reasons.add("EVIDENCE_REQUIRED_MISSING")
        if (
            materialization == "UNOBSERVED"
            or freshness == "UNOBSERVED"
            or binding == "UNOBSERVED"
            or availability == "UNAVAILABLE"
        ):
            entry_reasons.add("EVIDENCE_OBSERVABILITY_INCOMPLETE")

        if isinstance(gate, str) and gate in _HEAD_BOUND_GATES:
            expected_revision = head_sha or base_sha
        else:
            expected_revision = base_sha
        policy = requirement_policy.get(str(target)) if isinstance(target, str) else None
        if policy is not None:
            if (
                gate != policy["gate"]
                or artifact_role != policy["artifact_role"]
                or classification != policy["classification"]
                or required is not policy["required"]
                or evidence_key != target
                or reference != target
                or revision != expected_revision
            ):
                entry_reasons.add("EVIDENCE_BINDING_MISMATCH")
        else:
            is_g5_status = (
                gate == "G5_DEPLOY"
                and artifact_role == "status-verification"
                and classification == "DELIVERY_EVIDENCE"
                and required is False
                and source_type == "github_actions"
                and evidence_key == target == reference
                and revision == (head_sha or base_sha)
            )
            if not is_g5_status:
                entry_reasons.add("EVIDENCE_BINDING_MISMATCH")

        # Candidate identity is optional for M4 compatibility, but when
        # supplied every identity component is checked against this map.
        for field, expected in (
            ("task_id", task_id),
            ("repository", repository),
            ("base_sha", base_sha),
        ):
            if field in candidate and candidate.get(field) != expected:
                entry_reasons.add("EVIDENCE_BINDING_MISMATCH")
        if "head_sha" in candidate:
            expected_candidate_head = head_sha if gate in _HEAD_BOUND_GATES else None
            if candidate.get("head_sha") != expected_candidate_head:
                entry_reasons.add("EVIDENCE_BINDING_MISMATCH")
        if scope_hash is not None and "scope_hash" in candidate and candidate.get("scope_hash") != scope_hash:
            entry_reasons.add("EVIDENCE_BINDING_MISMATCH")

        if gate in {"G4_MERGE", "G5_DEPLOY"} and revision != (head_sha or base_sha):
            entry_reasons.add("EVIDENCE_CI_BINDING_MISMATCH")
        reasons.update(entry_reasons)
        entry = {
            "evidence_key": evidence_key,
            "gate": gate,
            "artifact_role": artifact_role,
            "artifact_type": artifact_type,
            "classification": classification,
            "required": required,
            "source_type": source_type,
            "target": target,
            "ref": reference,
            "revision": revision,
            "digest": digest,
            "binding_status": binding,
            "freshness_status": freshness,
            "materialization_status": materialization,
            "source_of_truth": source_of_truth and not is_projection_source,
            "reason_codes": _sort_reasons(entry_reasons),
        }
        entries.append(entry)
        if (
            policy is not None
            and materialization == "MATERIALIZED"
            and source_of_truth
            and not entry_reasons
        ):
            matched_targets.add(str(target))

    missing_required = sorted(
        {
            str(requirement["target"])
            for requirement in requirements
            if requirement["required"] and str(requirement["target"]) not in matched_targets
        }
    )
    stale_required = sorted(
        str(entry["target"])
        for entry in entries
        if entry.get("target") and entry.get("freshness_status") == "STALE"
    )
    projection_only = sorted(
        str(entry["target"])
        for entry in entries
        if entry.get("target") and "EVIDENCE_PROJECTION_ONLY" in entry["reason_codes"]
    )
    if missing_required:
        reasons.add("EVIDENCE_REQUIRED_MISSING")
    if stale_required:
        reasons.add("EVIDENCE_STALE")
    if projection_only:
        reasons.add("EVIDENCE_PROJECTION_ONLY")

    sorted_reasons = _sort_reasons(reasons)
    blocking = [reason for reason in sorted_reasons if reason != "EVIDENCE_G6_NOT_APPLICABLE"]
    outcome = "BLOCKED" if blocking else "READY"
    reported = blocking or ["EVIDENCE_MAP_READY"]
    if "EVIDENCE_G6_NOT_APPLICABLE" in sorted_reasons:
        reported.append("EVIDENCE_G6_NOT_APPLICABLE")
    sorted_entries = sorted(
        entries, key=lambda entry: (str(entry.get("gate")), str(entry.get("evidence_key")))
    )
    map_model = {
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "policy_revision": policy_revision,
        "requirements": requirements,
        "entries": sorted_entries,
        "missing_required": missing_required,
        "stale_required": stale_required,
        "projection_only": projection_only,
    }
    map_digest = "sha256:" + hashlib.sha256(_canonical_json_bytes(map_model)).hexdigest()
    return {
        "schema_version": "1.0",
        "artifact_type": "gate-evidence-artifact-map",
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "policy_revision": policy_revision,
        "mapped_at": mapped_at,
        "outcome": outcome,
        "reason_codes": reported,
        "entries": sorted_entries,
        "requirements": requirements,
        "missing_required": missing_required,
        "stale_required": stale_required,
        "projection_only": projection_only,
        "map_digest": map_digest,
        "authority_granted": False,
    }


__all__ = ["ACTION_TO_GATE", "EVIDENCE_CLASSES", "_GATE_REQUIREMENTS", "build_gate_evidence_artifact_map"]
