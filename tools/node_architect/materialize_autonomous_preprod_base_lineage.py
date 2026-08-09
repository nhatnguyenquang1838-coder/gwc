#!/usr/bin/env python3
"""Validate trusted pre-prod descendant lineage for a parent autonomous run.

The parent manifest anchor remains immutable. A later pre-prod base is accepted
only when every advance is a trusted, exact-SHA, same-run merge/G5 step for an
allowlisted task. Arbitrary branch drift fails closed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_base_lineage(
    *,
    run_id: str,
    repository: str,
    anchor_base_sha: str,
    current_base_sha: str,
    allowed_task_ids: Sequence[str],
    steps: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reasons: list[str] = []
    allowed = set(allowed_task_ids)
    if not _sha(anchor_base_sha) or not _sha(current_base_sha):
        reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")
    cursor = anchor_base_sha
    seen_tasks: set[str] = set()
    normalized: list[dict[str, Any]] = []

    for step in steps:
        task_id = str(step.get("task_id") or "")
        previous = step.get("previous_base_sha")
        merge_sha = step.get("merge_commit_sha")
        merged_head = step.get("merged_head_sha")
        if task_id not in allowed:
            reasons.append("AUTONOMOUS_TASK_NOT_ALLOWLISTED")
        if task_id in seen_tasks:
            reasons.append("AUTONOMOUS_BASE_LINEAGE_REPLAY")
        seen_tasks.add(task_id)
        if previous != cursor:
            reasons.append("AUTONOMOUS_BASE_LINEAGE_BROKEN")
        if not _sha(str(merge_sha)) or not _sha(str(merged_head)):
            reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")
        if step.get("run_id") not in (None, run_id):
            reasons.append("AUTONOMOUS_BASE_LINEAGE_FOREIGN_RUN")
        if step.get("repository") not in (None, repository):
            reasons.append("AUTONOMOUS_BASE_LINEAGE_FOREIGN_REPOSITORY")
        if step.get("trusted_merge_proof") is not True:
            reasons.append("AUTONOMOUS_BASE_LINEAGE_UNTRUSTED")
        if step.get("trusted_g5_evidence") is not True or step.get("g5_classification") != "success":
            reasons.append("AUTONOMOUS_BASE_LINEAGE_G5_NOT_SUCCESS")
        normalized.append({
            "task_id": task_id,
            "previous_base_sha": previous,
            "merged_head_sha": merged_head,
            "merge_commit_sha": merge_sha,
            "g5_classification": step.get("g5_classification"),
            "trusted_merge_proof": step.get("trusted_merge_proof"),
            "trusted_g5_evidence": step.get("trusted_g5_evidence"),
        })
        cursor = str(merge_sha)

    if cursor != current_base_sha:
        reasons.append("AUTONOMOUS_BASE_LINEAGE_UNTRUSTED")

    proof_without_digest = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-base-lineage-proof",
        "run_id": run_id,
        "repository": repository,
        "anchor_base_sha": anchor_base_sha,
        "current_base_sha": current_base_sha,
        "steps": normalized,
    }
    proof = dict(proof_without_digest)
    proof["lineage_digest"] = canonical_digest(proof_without_digest)
    return {
        "outcome": "PASS" if not reasons else "BLOCKED",
        "state": "BASE_LINEAGE_TRUSTED" if not reasons else "READY_FOR_AUTHORITY",
        "reason_codes": sorted(set(reasons)) or ["AUTONOMOUS_BASE_LINEAGE_TRUSTED"],
        "proof": proof,
    }


def _sha(value: str) -> bool:
    return len(value) == 40 and all(ch in "0123456789abcdef" for ch in value)


__all__ = ["canonical_digest", "validate_base_lineage"]
