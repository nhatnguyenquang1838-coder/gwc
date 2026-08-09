#!/usr/bin/env python3
"""Validate trusted parent-run authority for autonomous pre-prod child execution.

This module is pure and fail-closed. It does not grant authority and does not
perform GitHub/Jira writes. Live adapters must read the authority projection
from trusted GitHub evidence and pass the observed bot identity explicitly.

The parent manifest binds an immutable anchor base. Later pre-prod bases are
accepted only through a trusted same-run descendant lineage proven by exact-SHA
merge/G5 evidence for allowlisted tasks.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from tools.node_architect.materialize_autonomous_preprod_base_lineage import validate_base_lineage

TRUSTED_BOT = "github-actions[bot]"
RECEIPT_MARKER = "gwc:autonomous-preprod-run-authority-receipt"
POLICY_ID = "AUTONOMOUS_PREPROD_INTEGRATION_POLICY"


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None


def validate_parent_run_authority(
    *,
    manifest: Mapping[str, Any] | None,
    receipt: Mapping[str, Any] | None,
    observed_comment_login: str,
    expected_repository: str,
    expected_task_id: str,
    expected_base_sha: str,
    base_lineage_steps: Sequence[Mapping[str, Any]] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return AUTHORIZED_READY only for current parent authority and trusted base lineage."""
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    if not isinstance(manifest, Mapping):
        reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
    if not isinstance(receipt, Mapping):
        reasons.append("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED")
    if reasons:
        return _result(reasons)

    assert manifest is not None and receipt is not None
    if observed_comment_login != TRUSTED_BOT:
        reasons.append("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED")
    if receipt.get("bot_login") != TRUSTED_BOT or receipt.get("marker") != RECEIPT_MARKER:
        reasons.append("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED")
    if receipt.get("status") != "present" or receipt.get("source") != "github_actions_bot_comment":
        reasons.append("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED")
    if manifest.get("repository") != expected_repository:
        reasons.append("AUTONOMOUS_RUN_MANIFEST_INVALID")
    if manifest.get("target_branch") != "pre-prod" or manifest.get("approved_base_ref") != "pre-prod":
        reasons.append("AUTONOMOUS_PREPROD_TARGET_REQUIRED")
    if manifest.get("policy_id") != POLICY_ID or receipt.get("approved_policy_id") != POLICY_ID:
        reasons.append("AUTONOMOUS_POLICY_INVALID")
    if receipt.get("approved_run_id") != manifest.get("run_id"):
        reasons.append("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED")
    if receipt.get("approved_policy_revision") != manifest.get("policy_revision"):
        reasons.append("AUTONOMOUS_POLICY_REVISION_DRIFT")
    if receipt.get("approved_policy_digest") != manifest.get("policy_digest"):
        reasons.append("AUTONOMOUS_POLICY_DIGEST_DRIFT")

    scope_manifest = dict(manifest)
    scope_manifest.pop("authority_receipt", None)
    scope_digest = canonical_digest(scope_manifest)
    if receipt.get("manifest_scope_digest") != scope_digest:
        reasons.append("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED")
    if receipt.get("scope_hash_prefix") != scope_digest.removeprefix("sha256:")[:16]:
        reasons.append("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED")

    source_comment_id = receipt.get("source_comment_id")
    receipt_comment_id = receipt.get("receipt_comment_id")
    if not isinstance(source_comment_id, int) or not isinstance(receipt_comment_id, int) or source_comment_id == receipt_comment_id:
        reasons.append("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED")

    expiry = _parse_utc(receipt.get("expires_at"))
    issued = _parse_utc(receipt.get("issued_at"))
    manifest_expiry = _parse_utc(manifest.get("expires_at"))
    if not expiry or not issued or not manifest_expiry or issued > now or expiry <= now or manifest_expiry <= now:
        reasons.append("AUTONOMOUS_RUN_MANIFEST_EXPIRED")

    allowed = {
        str(item.get("task_id"))
        for item in manifest.get("allowed_tasks", [])
        if isinstance(item, Mapping) and item.get("task_id")
    }
    if expected_task_id not in allowed:
        reasons.append("AUTONOMOUS_TASK_NOT_ALLOWLISTED")

    anchor = str(manifest.get("approved_base_sha") or "")
    lineage = validate_base_lineage(
        run_id=str(manifest.get("run_id") or ""),
        repository=expected_repository,
        anchor_base_sha=anchor,
        current_base_sha=expected_base_sha,
        allowed_task_ids=sorted(allowed),
        steps=base_lineage_steps,
    )
    if lineage["outcome"] != "PASS":
        reasons.extend(lineage["reason_codes"])

    return _result(
        reasons,
        manifest=manifest,
        receipt=receipt,
        task_id=expected_task_id,
        base_lineage_proof=lineage["proof"],
    )


def _result(
    reasons: list[str], *, manifest: Mapping[str, Any] | None = None,
    receipt: Mapping[str, Any] | None = None, task_id: str | None = None,
    base_lineage_proof: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if reasons:
        return {
            "outcome": "BLOCKED",
            "state": "READY_FOR_AUTHORITY",
            "reason_codes": sorted(set(reasons)),
            "standing_g4_valid": False,
        }
    assert manifest is not None and receipt is not None and task_id is not None
    authority_digest = canonical_digest(receipt)
    return {
        "outcome": "PASS",
        "state": "AUTHORIZED_READY",
        "reason_codes": ["AUTONOMOUS_RUN_AUTHORITY_CURRENT", "AUTONOMOUS_BASE_LINEAGE_TRUSTED"],
        "task_id": task_id,
        "run_id": manifest.get("run_id"),
        "parent_authority_digest": authority_digest,
        "base_lineage_proof": dict(base_lineage_proof or {}),
        "standing_g4_valid": True,
    }


__all__ = ["canonical_digest", "validate_parent_run_authority"]
