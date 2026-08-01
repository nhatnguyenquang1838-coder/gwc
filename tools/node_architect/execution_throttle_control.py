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


def _valid_sha(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _valid_non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_rate(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0.0 <= float(value) <= 1.0
    )


def decide_execution_throttle(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    batch_id: str,
    active_implementation_batch_ids: list[str],
    requested_parallelism: int,
    max_parallelism: int,
    capacity_units_available: int,
    capacity_units_per_worker: int,
    recent_failure_rate: float,
    failure_rate_threshold: float,
    cooldown_active: bool,
    previous_batch_terminal: bool,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Apply bounded execution rate from capacity and failure signals."""
    outcome = "BLOCKED"
    reason_code = "THROTTLE_INPUT_REJECTED"
    execution_allowed = False
    allowed_parallelism = 0

    identity_invalid = not all(
        _valid_non_empty(value) for value in (task_id, repository, branch, batch_id)
    )
    sha_invalid = not (_valid_sha(base_sha) and _valid_sha(head_sha))
    active_invalid = not (
        isinstance(active_implementation_batch_ids, list)
        and all(_valid_non_empty(item) for item in active_implementation_batch_ids)
    )
    capacity_invalid = not (
        _valid_positive_int(requested_parallelism)
        and _valid_positive_int(max_parallelism)
        and isinstance(capacity_units_available, int)
        and not isinstance(capacity_units_available, bool)
        and capacity_units_available >= 0
        and _valid_positive_int(capacity_units_per_worker)
    )
    rates_invalid = not (
        _valid_rate(recent_failure_rate)
        and _valid_rate(failure_rate_threshold)
        and float(failure_rate_threshold) > 0.0
    )
    booleans_invalid = not (
        isinstance(cooldown_active, bool)
        and isinstance(previous_batch_terminal, bool)
    )

    unique_active = sorted(set(active_implementation_batch_ids)) if not active_invalid else []
    available_parallelism = (
        capacity_units_available // capacity_units_per_worker
        if not capacity_invalid
        else 0
    )

    if identity_invalid:
        reason_code = "REQUIRED_IDENTITY_MISSING"
    elif sha_invalid:
        reason_code = "INVALID_OR_MISSING_SHA_BINDING"
    elif active_invalid:
        reason_code = "INVALID_ACTIVE_BATCH_INPUT"
    elif capacity_invalid:
        reason_code = "INVALID_CAPACITY_INPUT"
    elif rates_invalid:
        reason_code = "INVALID_FAILURE_RATE_INPUT"
    elif booleans_invalid:
        reason_code = "INVALID_BOOLEAN_SIGNAL"
    elif len(unique_active) > 1:
        reason_code = "ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED"
    elif unique_active and unique_active[0] != batch_id:
        reason_code = "OTHER_BATCH_ALREADY_ACTIVE"
    elif not previous_batch_terminal:
        reason_code = "PREVIOUS_BATCH_NOT_TERMINAL"
    elif cooldown_active or float(recent_failure_rate) >= float(failure_rate_threshold):
        outcome = "THROTTLE"
        reason_code = "FAILURE_SIGNAL_COOLDOWN"
    elif available_parallelism <= 0:
        outcome = "THROTTLE"
        reason_code = "INSUFFICIENT_CAPACITY"
    else:
        allowed_parallelism = min(
            requested_parallelism,
            max_parallelism,
            available_parallelism,
        )
        execution_allowed = allowed_parallelism > 0
        if allowed_parallelism < requested_parallelism:
            outcome = "THROTTLE"
            reason_code = "CAPACITY_BOUNDED_THROTTLE"
        else:
            outcome = "ALLOW"
            reason_code = "REQUESTED_RATE_WITHIN_BOUNDS"

    decision = {
        "schema_version": "1.0",
        "artifact_type": "execution-throttle-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "batch_id": batch_id,
        "active_implementation_batch_ids": unique_active,
        "requested_parallelism": requested_parallelism,
        "max_parallelism": max_parallelism,
        "capacity_units_available": capacity_units_available,
        "capacity_units_per_worker": capacity_units_per_worker,
        "available_parallelism": available_parallelism,
        "recent_failure_rate": recent_failure_rate,
        "failure_rate_threshold": failure_rate_threshold,
        "cooldown_active": cooldown_active,
        "previous_batch_terminal": previous_batch_terminal,
        "allowed_parallelism": allowed_parallelism,
        "execution_allowed": execution_allowed,
        "partial_execution_allowed": execution_allowed and allowed_parallelism < requested_parallelism,
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
