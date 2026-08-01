#!/usr/bin/env python3
"""Deterministic, fail-closed batch admission control for scale_control."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


ACCEPTED_G5_STATUSES = {"PASS", "HUMAN_OBSERVED_CI_SUCCESS"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def attach_digest(decision: dict[str, Any]) -> dict[str, Any]:
    decision["decision_digest"] = digest_payload(
        {key: value for key, value in decision.items() if key != "decision_digest"}
    )
    return decision


def _valid_sha(value: str) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(ch in "0123456789abcdef" for ch in value)


def _valid_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def decide_batch_admission(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    previous_batch_id: str,
    previous_merge_sha: str,
    g5_evidence_merge_sha: str,
    g5_status: str,
    g5_evidence_qualified: bool,
    g5_observed_at: str,
    now_at: str,
    max_evidence_age_seconds: int,
    blocker_status: str,
    requested_node_count: int,
    approved_node_budget: int,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Return an ADMIT or BLOCKED decision without granting scale authority."""
    outcome = "ADMIT"
    reason_code = "BATCH_ADMISSION_REQUIREMENTS_SATISFIED"
    admission_allowed = True

    identity_missing = not all(
        isinstance(value, str) and value.strip()
        for value in (task_id, repository, branch, previous_batch_id)
    )
    sha_invalid = not all(
        _valid_sha(value)
        for value in (base_sha, head_sha, previous_merge_sha, g5_evidence_merge_sha)
    )
    counts_invalid = not (
        _valid_positive_int(requested_node_count)
        and _valid_positive_int(approved_node_budget)
        and _valid_positive_int(max_evidence_age_seconds)
    )
    timestamp_invalid = False
    evidence_age_seconds: int | None = None
    try:
        observed_g5 = parse_utc(g5_observed_at)
        current = parse_utc(now_at)
        evidence_age_seconds = int((current - observed_g5).total_seconds())
        if evidence_age_seconds < 0:
            timestamp_invalid = True
    except (TypeError, ValueError):
        timestamp_invalid = True

    if identity_missing:
        outcome = "BLOCKED"
        reason_code = "REQUIRED_IDENTITY_MISSING"
        admission_allowed = False
    elif sha_invalid:
        outcome = "BLOCKED"
        reason_code = "INVALID_OR_MISSING_SHA_BINDING"
        admission_allowed = False
    elif counts_invalid:
        outcome = "BLOCKED"
        reason_code = "INVALID_BATCH_LIMIT_INPUT"
        admission_allowed = False
    elif timestamp_invalid:
        outcome = "BLOCKED"
        reason_code = "INVALID_G5_OBSERVATION_TIME"
        admission_allowed = False
    elif previous_merge_sha != g5_evidence_merge_sha:
        outcome = "BLOCKED"
        reason_code = "G5_MERGE_SHA_MISMATCH"
        admission_allowed = False
    elif g5_status not in ACCEPTED_G5_STATUSES:
        outcome = "BLOCKED"
        reason_code = "G5_NOT_SUCCESSFUL"
        admission_allowed = False
    elif not isinstance(g5_evidence_qualified, bool) or not g5_evidence_qualified:
        outcome = "BLOCKED"
        reason_code = "G5_EVIDENCE_UNQUALIFIED"
        admission_allowed = False
    elif evidence_age_seconds is None or evidence_age_seconds > max_evidence_age_seconds:
        outcome = "BLOCKED"
        reason_code = "G5_EVIDENCE_STALE"
        admission_allowed = False
    elif blocker_status != "CLEAR":
        outcome = "BLOCKED"
        reason_code = "ACTIVE_BLOCKER_PRESENT"
        admission_allowed = False
    elif requested_node_count > approved_node_budget:
        outcome = "BLOCKED"
        reason_code = "APPROVED_NODE_BUDGET_EXCEEDED"
        admission_allowed = False

    decision = {
        "schema_version": "1.0",
        "artifact_type": "batch-admission-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "previous_batch_id": previous_batch_id,
        "previous_merge_sha": previous_merge_sha,
        "g5_evidence_merge_sha": g5_evidence_merge_sha,
        "g5_status": g5_status,
        "g5_evidence_qualified": g5_evidence_qualified,
        "g5_observed_at": g5_observed_at,
        "now_at": now_at,
        "max_evidence_age_seconds": max_evidence_age_seconds,
        "evidence_age_seconds": evidence_age_seconds,
        "blocker_status": blocker_status,
        "requested_node_count": requested_node_count,
        "approved_node_budget": approved_node_budget,
        "admission_allowed": admission_allowed,
        "partial_admission_allowed": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "audit_authority_granted": False,
        "scale_authority_granted": False,
        "outcome": outcome,
        "reason_code": reason_code,
        "observed_at": observed_at or now_utc(),
    }
    return attach_digest(decision)
