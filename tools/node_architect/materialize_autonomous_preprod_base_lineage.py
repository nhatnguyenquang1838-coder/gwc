#!/usr/bin/env python3
"""Validate trusted pre-prod descendant lineage for a parent autonomous run.

The Human-approved parent anchor remains immutable. A later ``pre-prod`` SHA is
accepted from a trusted repository ancestry readback when:
- the current SHA is identical to or ahead of the authority anchor;
- the merge base is exactly the authority anchor; and
- the machine authority-policy bytes are unchanged at anchor and current SHA.

Optional task-merge steps are audit detail only. They may explain selected
autonomous merges, but they are not required to enumerate every descendant
commit because compatible governance/runtime hotfixes may legitimately advance
``pre-prod`` between autonomous task merges.

Post-merge G5 is observational for
``AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`` and is never lineage authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

TRUSTED_READBACK_SOURCES = {"github_compare", "repo_ci", "trusted_local_git"}
DESCENDANT_STATUSES = {"ahead", "identical"}


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(ch in "0123456789abcdef" for ch in value[7:])
    )


def _sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _validate_repository_readback(
    *,
    anchor_base_sha: str,
    current_base_sha: str,
    repository_readback: Mapping[str, Any] | None,
) -> tuple[list[str], dict[str, Any] | None]:
    """Validate deterministic ancestry/policy evidence.

    ``trusted_repository_readback`` is a transport/runtime attestation bit.
    This pure function cannot establish that trust by itself; live callers must
    derive it from GitHub API/CI or a verified local Git checkout.
    """
    if current_base_sha == anchor_base_sha and repository_readback is None:
        return [], None
    if not isinstance(repository_readback, Mapping):
        return ["AUTONOMOUS_BASE_LINEAGE_UNTRUSTED"], None

    reasons: list[str] = []
    source = repository_readback.get("source")
    status = repository_readback.get("comparison_status")
    merge_base_sha = repository_readback.get("merge_base_sha")
    anchor_policy = repository_readback.get("authority_policy_anchor_digest")
    current_policy = repository_readback.get("authority_policy_current_digest")
    trusted = repository_readback.get("trusted_repository_readback")

    if source not in TRUSTED_READBACK_SOURCES:
        reasons.append("AUTONOMOUS_BASE_LINEAGE_UNTRUSTED")
    if status not in DESCENDANT_STATUSES:
        reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")
    if merge_base_sha != anchor_base_sha:
        reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")
    if trusted is not True:
        reasons.append("AUTONOMOUS_BASE_LINEAGE_UNTRUSTED")
    if not _digest(anchor_policy) or not _digest(current_policy):
        reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")
    elif anchor_policy != current_policy:
        reasons.append("AUTONOMOUS_AUTHORITY_POLICY_DRIFT")

    normalized = {
        "source": source,
        "comparison_status": status,
        "merge_base_sha": merge_base_sha,
        "authority_policy_anchor_digest": anchor_policy,
        "authority_policy_current_digest": current_policy,
        "trusted_repository_readback": trusted,
    }
    return reasons, normalized


def _validate_audit_steps(
    *,
    run_id: str,
    repository: str,
    allowed_task_ids: Sequence[str],
    steps: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    reasons: list[str] = []
    allowed = set(allowed_task_ids)
    seen_tasks: set[str] = set()
    normalized: list[dict[str, Any]] = []

    for step in steps:
        if not isinstance(step, Mapping):
            reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")
            continue
        task_id = str(step.get("task_id") or "")
        previous = step.get("previous_base_sha")
        merge_sha = step.get("merge_commit_sha")
        merged_head = step.get("merged_head_sha")

        if task_id not in allowed:
            reasons.append("AUTONOMOUS_TASK_NOT_ALLOWLISTED")
        if task_id in seen_tasks:
            reasons.append("AUTONOMOUS_BASE_LINEAGE_REPLAY")
        seen_tasks.add(task_id)
        if not _sha(previous) or not _sha(merge_sha) or not _sha(merged_head):
            reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")
        if step.get("run_id") not in (None, run_id):
            reasons.append("AUTONOMOUS_BASE_LINEAGE_FOREIGN_RUN")
        if step.get("repository") not in (None, repository):
            reasons.append("AUTONOMOUS_BASE_LINEAGE_FOREIGN_REPOSITORY")
        if step.get("trusted_merge_proof") is not True:
            reasons.append("AUTONOMOUS_BASE_LINEAGE_UNTRUSTED")

        g5_classification = step.get("g5_classification")
        if g5_classification is not None and not isinstance(g5_classification, str):
            reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")
        trusted_g5_evidence = step.get("trusted_g5_evidence")
        if trusted_g5_evidence is not None and type(trusted_g5_evidence) is not bool:
            reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")

        normalized.append({
            "task_id": task_id,
            "previous_base_sha": previous,
            "merged_head_sha": merged_head,
            "merge_commit_sha": merge_sha,
            "g5_classification": g5_classification,
            "trusted_merge_proof": step.get("trusted_merge_proof"),
            "trusted_g5_evidence": trusted_g5_evidence,
        })
    return reasons, normalized


def validate_base_lineage(
    *,
    run_id: str,
    repository: str,
    anchor_base_sha: str,
    current_base_sha: str,
    allowed_task_ids: Sequence[str],
    steps: Sequence[Mapping[str, Any]] = (),
    repository_readback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic base-lineage proof from trusted repository readback."""
    reasons: list[str] = []
    if not _sha(anchor_base_sha) or not _sha(current_base_sha):
        reasons.append("AUTONOMOUS_BASE_LINEAGE_INVALID")

    readback_reasons, normalized_readback = _validate_repository_readback(
        anchor_base_sha=anchor_base_sha,
        current_base_sha=current_base_sha,
        repository_readback=repository_readback,
    )
    reasons.extend(readback_reasons)

    step_reasons, normalized_steps = _validate_audit_steps(
        run_id=run_id,
        repository=repository,
        allowed_task_ids=allowed_task_ids,
        steps=steps,
    )
    reasons.extend(step_reasons)

    proof_without_digest = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-base-lineage-proof",
        "run_id": run_id,
        "repository": repository,
        "anchor_base_sha": anchor_base_sha,
        "current_base_sha": current_base_sha,
        "repository_readback": normalized_readback,
        "steps": normalized_steps,
    }
    proof = dict(proof_without_digest)
    proof["lineage_digest"] = canonical_digest(proof_without_digest)
    return {
        "outcome": "PASS" if not reasons else "BLOCKED",
        "state": "BASE_LINEAGE_TRUSTED" if not reasons else "READY_FOR_AUTHORITY",
        "reason_codes": sorted(set(reasons)) or ["AUTONOMOUS_BASE_LINEAGE_TRUSTED"],
        "proof": proof,
    }


__all__ = [
    "DESCENDANT_STATUSES",
    "TRUSTED_READBACK_SOURCES",
    "canonical_digest",
    "validate_base_lineage",
]
