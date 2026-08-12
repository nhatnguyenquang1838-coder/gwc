#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def attach_digest(decision: dict[str, Any]) -> dict[str, Any]:
    decision["decision_digest"] = digest_payload(
        {key: value for key, value in decision.items() if key != "decision_digest"}
    )
    return decision


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(ch in "0123456789abcdef" for ch in value[7:])
    )


def _valid_non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unique_non_empty(items: object) -> bool:
    return (
        isinstance(items, list)
        and bool(items)
        and all(_valid_non_empty(item) for item in items)
        and len(items) == len(set(items))
    )


TERMINAL_SUCCESS = {"success"}
TERMINAL_FAILURES = {"failure", "cancelled", "timed_out", "action_required", "stale"}
PENDING_STATUSES = {"queued", "pending", "in_progress", "waiting", "requested"}
CONNECTOR_STATUSES = {"CONFIRMED", "EMPTY", "ERROR", "UNSUPPORTED"}
MIXED_HEAD_EVIDENCE_BLOCKED = "MIXED_HEAD_EVIDENCE_BLOCKED"
BLOCKER_FINDINGS_PRESENT = "BLOCKER_FINDINGS_PRESENT"
SCOPE_DRIFT_DETECTED = "SCOPE_DRIFT_DETECTED"


def _valid_check(check: object) -> bool:
    return (
        isinstance(check, dict)
        and _valid_non_empty(check.get("name"))
        and _valid_sha(check.get("head_sha"))
        and _valid_non_empty(check.get("status"))
        and (check.get("conclusion") is None or _valid_non_empty(check.get("conclusion")))
    )


def _valid_artifact(artifact: object) -> bool:
    return (
        isinstance(artifact, dict)
        and _valid_non_empty(artifact.get("name"))
        and _valid_sha(artifact.get("head_sha"))
        and _valid_digest(artifact.get("digest"))
    )


def decide_exact_head_readiness(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    current_head_sha: str,
    expected_head_sha: str,
    required_check_names: list[str],
    observed_checks: list[dict[str, Any]],
    required_artifact_names: list[str],
    observed_artifacts: list[dict[str, Any]],
    connector_status: str,
    exact_head_filter_applied: bool,
    blocker_findings: list[str] | None = None,
    scope_drift_detected: bool = False,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Determine whether readiness evidence is bound to the exact current head."""
    outcome = "BLOCKED"
    reason_code = "EXACT_HEAD_READINESS_NOT_SATISFIED"
    readiness_passed = False

    identity_invalid = not all(_valid_non_empty(value) for value in (task_id, repository, branch))
    sha_invalid = not all(_valid_sha(value) for value in (base_sha, current_head_sha, expected_head_sha))
    checks_invalid = not (
        _unique_non_empty(required_check_names)
        and isinstance(observed_checks, list)
        and all(_valid_check(check) for check in observed_checks)
    )
    artifacts_invalid = not (
        _unique_non_empty(required_artifact_names)
        and isinstance(observed_artifacts, list)
        and all(_valid_artifact(artifact) for artifact in observed_artifacts)
    )
    connector_invalid = connector_status not in CONNECTOR_STATUSES or not isinstance(exact_head_filter_applied, bool)
    blocker_findings_invalid = (
        blocker_findings is not None
        and (not isinstance(blocker_findings, list)
             or not all(isinstance(f, str) and f.strip() for f in blocker_findings))
    )
    scope_drift_invalid = not isinstance(scope_drift_detected, bool)

    exact_checks = [] if checks_invalid else [check for check in observed_checks if check["head_sha"] == current_head_sha]
    mismatched_check_count = 0 if checks_invalid else len(observed_checks) - len(exact_checks)
    check_by_name: dict[str, dict[str, Any]] = {}
    if not checks_invalid:
        for check in exact_checks:
            check_by_name[check["name"]] = check

    missing_check_names = [] if checks_invalid else sorted(set(required_check_names) - set(check_by_name))
    pending_check_names: list[str] = []
    failed_check_names: list[str] = []
    successful_check_names: list[str] = []
    if not checks_invalid:
        for name in sorted(set(required_check_names) & set(check_by_name)):
            check = check_by_name[name]
            status = check["status"]
            conclusion = check.get("conclusion")
            if status in PENDING_STATUSES or status != "completed":
                pending_check_names.append(name)
            elif conclusion in TERMINAL_SUCCESS:
                successful_check_names.append(name)
            elif conclusion in TERMINAL_FAILURES or conclusion:
                failed_check_names.append(name)
            else:
                failed_check_names.append(name)

    exact_artifacts = [] if artifacts_invalid else [artifact for artifact in observed_artifacts if artifact["head_sha"] == current_head_sha]
    mismatched_artifact_count = 0 if artifacts_invalid else len(observed_artifacts) - len(exact_artifacts)
    artifact_names = {artifact["name"] for artifact in exact_artifacts}
    missing_artifact_names = [] if artifacts_invalid else sorted(set(required_artifact_names) - artifact_names)

    if identity_invalid:
        reason_code = "REQUIRED_IDENTITY_MISSING"
    elif sha_invalid:
        reason_code = "INVALID_OR_MISSING_SHA_BINDING"
    elif current_head_sha != expected_head_sha:
        reason_code = "STALE_HEAD_REJECTED"
    elif connector_invalid:
        reason_code = "INVALID_CONNECTOR_STATUS"
    elif connector_status in {"ERROR", "UNSUPPORTED"}:
        reason_code = "CONNECTOR_OBSERVABILITY_INCOMPLETE"
    elif connector_status == "EMPTY" and not exact_head_filter_applied:
        reason_code = "EMPTY_UNFILTERED_CONNECTOR_RESULT"
    elif checks_invalid:
        reason_code = "INVALID_REQUIRED_CHECK_MAPPING"
    elif artifacts_invalid:
        reason_code = "INVALID_ARTIFACT_EVIDENCE"
    elif blocker_findings_invalid:
        reason_code = "INVALID_BLOCKER_FINDINGS"
    elif scope_drift_invalid:
        reason_code = "INVALID_SCOPE_DRIFT"
    elif missing_check_names:
        reason_code = "REQUIRED_CHECK_MISSING"
    elif pending_check_names:
        reason_code = "REQUIRED_CHECK_NON_TERMINAL"
    elif failed_check_names:
        reason_code = "REQUIRED_CHECK_FAILED"
    elif missing_artifact_names:
        reason_code = "REQUIRED_ARTIFACT_MISSING"
    elif mismatched_check_count or mismatched_artifact_count:
        reason_code = MIXED_HEAD_EVIDENCE_BLOCKED
    elif blocker_findings:
        reason_code = BLOCKER_FINDINGS_PRESENT
    elif scope_drift_detected:
        reason_code = SCOPE_DRIFT_DETECTED
    else:
        reason_code = "EXACT_HEAD_READY"
        outcome = "READY"
        readiness_passed = True

    decision = {
        "schema_version": "1.0",
        "artifact_type": "exact-head-readiness-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "current_head_sha": current_head_sha,
        "expected_head_sha": expected_head_sha,
        "connector_status": connector_status,
        "exact_head_filter_applied": exact_head_filter_applied,
        "required_check_names": sorted(required_check_names) if isinstance(required_check_names, list) else [],
        "successful_check_names": sorted(successful_check_names),
        "pending_check_names": sorted(pending_check_names),
        "failed_check_names": sorted(failed_check_names),
        "missing_check_names": missing_check_names,
        "required_artifact_names": sorted(required_artifact_names) if isinstance(required_artifact_names, list) else [],
        "missing_artifact_names": missing_artifact_names,
        "mismatched_check_count": mismatched_check_count,
        "mismatched_artifact_count": mismatched_artifact_count,
        "blocker_findings": blocker_findings or [],
        "scope_drift_detected": bool(scope_drift_detected),
        "readiness_passed": readiness_passed,
        "read_only_projection": True,
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
