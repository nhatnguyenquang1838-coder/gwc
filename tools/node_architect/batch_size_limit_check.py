#!/usr/bin/env python3
"""Deterministic, fail-closed batch-size and concurrency control."""
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
    return isinstance(value, str) and len(value) == 40 and all(ch in "0123456789abcdef" for ch in value)


def _valid_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_string_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def decide_batch_size_limit(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    head_sha: str,
    batch_id: str,
    node_ids: list[str],
    node_batch_ids: list[str],
    active_implementation_batch_ids: list[str],
    max_batch_size: int = 9,
    max_concurrent_implementation_batches: int = 1,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Enforce cardinality and single-active-batch limits without partial admission."""
    outcome = "ALLOW"
    reason_code = "BATCH_LIMITS_SATISFIED"
    admission_allowed = True

    identity_invalid = not all(
        isinstance(value, str) and value.strip()
        for value in (task_id, repository, branch, batch_id)
    ) or not _valid_sha(base_sha) or not _valid_sha(head_sha)
    limits_invalid = not (
        _valid_positive_int(max_batch_size)
        and _valid_positive_int(max_concurrent_implementation_batches)
    )
    lists_invalid = not (
        _valid_string_list(node_ids)
        and _valid_string_list(node_batch_ids)
        and _valid_string_list(active_implementation_batch_ids)
    )
    node_count = len(node_ids) if isinstance(node_ids, list) else 0
    duplicate_node_ids = (
        isinstance(node_ids, list)
        and all(isinstance(item, str) for item in node_ids)
        and len(node_ids) != len(set(node_ids))
    )
    mapping_length_mismatch = (
        isinstance(node_ids, list)
        and isinstance(node_batch_ids, list)
        and len(node_ids) != len(node_batch_ids)
    )
    mixed_batch_identifiers = (
        isinstance(node_batch_ids, list)
        and any(item != batch_id for item in node_batch_ids if isinstance(item, str))
    )
    active_batches = (
        sorted(set(active_implementation_batch_ids))
        if _valid_string_list(active_implementation_batch_ids)
        else []
    )
    prospective_batches = sorted(set(active_batches + ([batch_id] if batch_id else [])))
    excess_concurrency = (
        _valid_positive_int(max_concurrent_implementation_batches)
        and len(prospective_batches) > max_concurrent_implementation_batches
    )

    if identity_invalid:
        outcome = "BLOCKED"
        reason_code = "INVALID_OR_MISSING_IDENTITY"
        admission_allowed = False
    elif limits_invalid:
        outcome = "BLOCKED"
        reason_code = "INVALID_LIMIT_CONFIGURATION"
        admission_allowed = False
    elif lists_invalid:
        outcome = "BLOCKED"
        reason_code = "INVALID_BATCH_LIST_INPUT"
        admission_allowed = False
    elif node_count == 0:
        outcome = "BLOCKED"
        reason_code = "EMPTY_BATCH_NOT_ADMITTED"
        admission_allowed = False
    elif mapping_length_mismatch:
        outcome = "BLOCKED"
        reason_code = "NODE_BATCH_MAPPING_LENGTH_MISMATCH"
        admission_allowed = False
    elif duplicate_node_ids:
        outcome = "BLOCKED"
        reason_code = "DUPLICATE_NODE_ID"
        admission_allowed = False
    elif mixed_batch_identifiers:
        outcome = "BLOCKED"
        reason_code = "MIXED_BATCH_IDENTIFIERS"
        admission_allowed = False
    elif node_count > max_batch_size:
        outcome = "BLOCKED"
        reason_code = "BATCH_SIZE_LIMIT_EXCEEDED"
        admission_allowed = False
    elif excess_concurrency:
        outcome = "BLOCKED"
        reason_code = "ACTIVE_BATCH_CONCURRENCY_LIMIT_EXCEEDED"
        admission_allowed = False

    decision = {
        "schema_version": "1.0",
        "artifact_type": "batch-size-limit-decision",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "batch_id": batch_id,
        "node_ids": node_ids,
        "node_batch_ids": node_batch_ids,
        "node_count": node_count,
        "active_implementation_batch_ids": active_implementation_batch_ids,
        "prospective_implementation_batch_ids": prospective_batches,
        "max_batch_size": max_batch_size,
        "max_concurrent_implementation_batches": max_concurrent_implementation_batches,
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
