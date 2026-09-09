"""Validate G4 approval-subject vs evidence-container semantics.

This evaluator is pure/read-only. It validates that a committed G4 evidence
artifact may live on a descendant PR tip without becoming part of its own
approval subject. It never grants authority or performs a merge.
"""
from __future__ import annotations

import re
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

REASON_PASS = "G4_SUBJECT_CONTAINER_VALID"
REASON_INPUT = "G4_SUBJECT_INPUT_INVALID"
REASON_SELF = "G4_SUBJECT_SELF_REFERENCE"
REASON_ANCESTRY = "G4_SUBJECT_ANCESTRY_UNVERIFIED"
REASON_DELTA = "G4_CONTAINER_DELTA_NOT_EVIDENCE_ONLY"
REASON_RECEIPT_HEAD = "G4_RECEIPT_HEAD_MISMATCH"
REASON_RECEIPT_SCOPE = "G4_RECEIPT_SCOPE_MISMATCH"


def _g4_root(task_id: str) -> str:
    return f".gwc/tasks/{task_id}/g4"


def _is_g4_evidence_path(task_id: str, path: str) -> bool:
    root = _g4_root(task_id)
    return path == root or path.startswith(root + "/")


def validate_g4_subject_container(
    *,
    task_id: str,
    subject_head_sha: str,
    current_head_sha: str,
    subject_scope_hash: str,
    subject_approved_paths: list[str],
    subject_to_current_delta_paths: list[str],
    subject_ancestor_verified: bool,
    delta_complete_verified: bool,
    receipt_approved_head_sha: str,
    receipt_scope_hash_prefix: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    if (
        not isinstance(task_id, str) or not task_id.strip()
        or not isinstance(subject_head_sha, str) or not _SHA.fullmatch(subject_head_sha)
        or not isinstance(current_head_sha, str) or not _SHA.fullmatch(current_head_sha)
        or not isinstance(subject_scope_hash, str) or not _DIGEST.fullmatch(subject_scope_hash)
        or not isinstance(subject_approved_paths, list)
        or not isinstance(subject_to_current_delta_paths, list)
        or any(not isinstance(p, str) or not p for p in subject_approved_paths + subject_to_current_delta_paths)
        or len(subject_approved_paths) != len(set(subject_approved_paths))
        or len(subject_to_current_delta_paths) != len(set(subject_to_current_delta_paths))
        or not isinstance(subject_ancestor_verified, bool)
        or not isinstance(delta_complete_verified, bool)
        or not isinstance(receipt_approved_head_sha, str) or not _SHA.fullmatch(receipt_approved_head_sha)
        or not isinstance(receipt_scope_hash_prefix, str) or not re.fullmatch(r"[0-9a-f]{16}", receipt_scope_hash_prefix)
    ):
        reasons.append(REASON_INPUT)

    clean_task = task_id.strip() if isinstance(task_id, str) else ""
    if clean_task and any(_is_g4_evidence_path(clean_task, p) for p in subject_approved_paths if isinstance(p, str)):
        reasons.append(REASON_SELF)

    if subject_head_sha != current_head_sha:
        if subject_ancestor_verified is not True:
            reasons.append(REASON_ANCESTRY)
        if delta_complete_verified is not True:
            reasons.append(REASON_DELTA)
        elif clean_task and any(
            not _is_g4_evidence_path(clean_task, p)
            for p in subject_to_current_delta_paths
            if isinstance(p, str)
        ):
            reasons.append(REASON_DELTA)
    elif subject_to_current_delta_paths:
        reasons.append(REASON_DELTA)

    if receipt_approved_head_sha != current_head_sha:
        reasons.append(REASON_RECEIPT_HEAD)
    expected_prefix = subject_scope_hash.removeprefix("sha256:")[:16] if isinstance(subject_scope_hash, str) else ""
    if receipt_scope_hash_prefix != expected_prefix:
        reasons.append(REASON_RECEIPT_SCOPE)

    reasons = list(dict.fromkeys(reasons))
    return {
        "schema_version": "1.0",
        "artifact_type": "g4-subject-container-validation",
        "task_id": task_id,
        "subject_head_sha": subject_head_sha,
        "current_head_sha": current_head_sha,
        "subject_scope_hash": subject_scope_hash,
        "subject_scope_hash_prefix": expected_prefix,
        "outcome": "PASS" if not reasons else "BLOCKED",
        "reason_codes": [REASON_PASS] if not reasons else reasons,
        "authority_granted": False,
    }


__all__ = ["validate_g4_subject_container"]
