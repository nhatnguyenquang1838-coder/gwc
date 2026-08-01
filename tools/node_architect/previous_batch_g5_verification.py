#!/usr/bin/env python3
"""Deterministic qualification of exact previous-batch G5 evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


SUCCESS_CONCLUSION = "success"
PENDING_CONCLUSIONS = {"queued", "pending", "in_progress", "waiting", "requested"}
HUMAN_SOURCE = "human_observed_github_ui"
CONNECTOR_SOURCE = "connector"


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


def decide_previous_batch_g5_verification(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    previous_batch_id: str,
    previous_pr_number: int,
    previous_pr_state: str,
    expected_merge_sha: str,
    evidence_source: str,
    evidence_event: str,
    evidence_branch: str,
    evidence_head_sha: str,
    workflow_run_id: int | None,
    conclusion: str,
    connector_status: str,
    required_workflow_names: list[str],
    observed_at_evidence: str,
    now_at: str,
    max_evidence_age_seconds: int,
    human_attestation_id: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Verify exact G5 evidence while preserving connector-observability labels."""
    outcome = "BLOCKED"
    reason_code = "G5_EVIDENCE_UNQUALIFIED"
    verification_passed = False
    evidence_age_seconds: int | None = None

    identity_invalid = not all(
        isinstance(value, str) and value.strip()
        for value in (task_id, repository, branch, previous_batch_id)
    )
    sha_invalid = not all(
        _valid_sha(value)
        for value in (base_sha, head_sha, expected_merge_sha, evidence_head_sha)
    )
    pr_invalid = not _valid_positive_int(previous_pr_number)
    workflows_invalid = not (
        isinstance(required_workflow_names, list)
        and all(isinstance(item, str) and item.strip() for item in required_workflow_names)
    )
    time_invalid = False
    try:
        evidence_time = parse_utc(observed_at_evidence)
        current = parse_utc(now_at)
        evidence_age_seconds = int((current - evidence_time).total_seconds())
        if evidence_age_seconds < 0:
            time_invalid = True
    except (TypeError, ValueError):
        time_invalid = True

    if identity_invalid or pr_invalid:
        reason_code = "REQUIRED_G5_IDENTITY_MISSING"
    elif sha_invalid:
        reason_code = "INVALID_OR_MISSING_SHA_BINDING"
    elif workflows_invalid or not required_workflow_names:
        reason_code = "REQUIRED_WORKFLOW_EVIDENCE_MISSING"
    elif time_invalid or not _valid_positive_int(max_evidence_age_seconds):
        reason_code = "INVALID_G5_OBSERVATION_TIME"
    elif previous_pr_state != "merged":
        reason_code = "PREVIOUS_PR_NOT_MERGED"
    elif evidence_head_sha != expected_merge_sha:
        reason_code = "G5_HEAD_SHA_MISMATCH"
    elif evidence_event != "push":
        reason_code = "PR_ONLY_EVIDENCE_NOT_QUALIFIED"
    elif evidence_branch != "main":
        reason_code = "G5_BRANCH_MISMATCH"
    elif evidence_age_seconds is None or evidence_age_seconds > max_evidence_age_seconds:
        reason_code = "G5_EVIDENCE_STALE"
    elif conclusion in PENDING_CONCLUSIONS:
        reason_code = "G5_EVIDENCE_PENDING"
    elif conclusion != SUCCESS_CONCLUSION:
        reason_code = "G5_EVIDENCE_NOT_SUCCESSFUL"
    elif evidence_source == CONNECTOR_SOURCE:
        if connector_status != "CONFIRMED" or not _valid_positive_int(workflow_run_id):
            reason_code = "CONNECTOR_EVIDENCE_INCOMPLETE"
        else:
            outcome = "VERIFIED_CONNECTOR"
            reason_code = "EXACT_POST_MERGE_G5_CONFIRMED"
            verification_passed = True
    elif evidence_source == HUMAN_SOURCE:
        if connector_status != "CONNECTOR_OBSERVABILITY_INCOMPLETE":
            reason_code = "HUMAN_OBSERVED_LABEL_MISMATCH"
        elif not isinstance(human_attestation_id, str) or not human_attestation_id.strip():
            reason_code = "HUMAN_ATTESTATION_MISSING"
        else:
            outcome = "VERIFIED_HUMAN_OBSERVED"
            reason_code = "QUALIFIED_HUMAN_OBSERVED_G5_SUCCESS"
            verification_passed = True
    else:
        reason_code = "UNSUPPORTED_G5_EVIDENCE_SOURCE"

    decision = {
        "schema_version": "1.0",
        "artifact_type": "previous-batch-g5-verification-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "previous_batch_id": previous_batch_id,
        "previous_pr_number": previous_pr_number,
        "previous_pr_state": previous_pr_state,
        "expected_merge_sha": expected_merge_sha,
        "evidence_source": evidence_source,
        "evidence_event": evidence_event,
        "evidence_branch": evidence_branch,
        "evidence_head_sha": evidence_head_sha,
        "workflow_run_id": workflow_run_id,
        "conclusion": conclusion,
        "connector_status": connector_status,
        "required_workflow_names": required_workflow_names,
        "observed_at_evidence": observed_at_evidence,
        "now_at": now_at,
        "max_evidence_age_seconds": max_evidence_age_seconds,
        "evidence_age_seconds": evidence_age_seconds,
        "human_attestation_id": human_attestation_id,
        "verification_passed": verification_passed,
        "connector_confirmed_pass": verification_passed and evidence_source == CONNECTOR_SOURCE,
        "human_observed_success": verification_passed and evidence_source == HUMAN_SOURCE,
        "pr_only_evidence_accepted": False,
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
