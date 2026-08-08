#!/usr/bin/env python3
"""Exact pre-prod merge-SHA G5 verification for the autonomous runtime (SCRUM-276)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .exact_head_readiness import decide_exact_head_readiness, digest_payload


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(ch in "0123456789abcdef" for ch in value)


def verify_preprod_merge_sha(
    *,
    task_id: str,
    repository: str,
    base_sha: str,
    merge_sha: str,
    required_check_names: list[str],
    observed_checks: list[dict[str, Any]],
    required_artifact_names: list[str],
    observed_artifacts: list[dict[str, Any]],
    connector_status: str,
    exact_head_filter_applied: bool,
    observed_at: str | None = None,
) -> dict[str, Any]:
    if not _valid_sha(merge_sha):
        raise ValueError("merge_sha must be a 40-char lowercase hex SHA")
    if not _valid_sha(base_sha):
        raise ValueError("base_sha must be a 40-char lowercase hex SHA")

    readiness = decide_exact_head_readiness(
        task_id=task_id,
        repository=repository,
        branch="main",
        base_sha=base_sha,
        current_head_sha=merge_sha,
        expected_head_sha=merge_sha,
        required_check_names=required_check_names,
        observed_checks=observed_checks,
        required_artifact_names=required_artifact_names,
        observed_artifacts=observed_artifacts,
        connector_status="CONFIRMED" if connector_status == "available" else ("ERROR" if connector_status == "unavailable" else connector_status),
        exact_head_filter_applied=exact_head_filter_applied,
        observed_at=observed_at,
    )

    reason_code = readiness["reason_code"]
    if connector_status == "UNSUPPORTED" or reason_code == "CONNECTOR_OBSERVABILITY_INCOMPLETE":
        g5_status = "CONNECTOR_OBSERVABILITY_INCOMPLETE"
        limitations = [
            "connector could not filter by push/main; exact merge SHA evidence not observable",
            "fall back to known run_id and jobs/artifacts before declaring success",
        ]
    elif reason_code == "EXACT_HEAD_READY":
        g5_status = "PASS"
        limitations = []
    elif reason_code in ("REQUIRED_CHECK_NON_TERMINAL", "PENDING_CHECKS"):
        g5_status = "CI_PENDING"
        limitations = ["one or more required checks still pending for the exact merge SHA"]
    else:
        g5_status = "FAIL"
        limitations = [reason_code]

    return {
        "schema_version": "1.0",
        "artifact_type": "autonomous-g5-verification",
        "task_id": task_id,
        "repository": repository,
        "base_sha": base_sha,
        "merge_sha": merge_sha,
        "g5_status": g5_status,
        "exact_head_bound": all(
            (isinstance(check, dict) and str(check.get("head_sha", "")) == merge_sha)
            for check in (observed_checks or [])
        ),
        "readiness_outcome": readiness["outcome"],
        "readiness_reason": readiness["reason_code"],
        "required_checks": required_check_names,
        "successful_checks": readiness.get("successful_check_names", []),
        "failed_checks": readiness.get("failed_check_names", []),
        "pending_checks": readiness.get("pending_check_names", []),
        "missing_checks": readiness.get("missing_check_names", []),
        "authority_granted": False,
        "limitations": limitations,
        "observed_at": observed_at or now_utc(),
        "result_digest": digest_payload(
            {
                "task_id": task_id,
                "repository": repository,
                "merge_sha": merge_sha,
                "g5_status": g5_status,
                "readiness_outcome": readiness["outcome"],
                "readiness_reason": readiness["reason_code"],
            }
        ),
    }
