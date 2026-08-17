"""Replay-safe repo_delivery.branch-creation decision helper.

This module is intentionally pure: it does not call GitHub or mutate refs.
The caller supplies connector readback and write result observations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_BRANCH_RE = re.compile(r"^(auto|codex|feat|fix|chore|docs|test|refactor|hotfix)/[A-Za-z0-9._/-]+$")


@dataclass(frozen=True)
class BranchCreationDecision:
    node_id: str
    outcome: str
    reason_codes: list[str]
    repository: str
    branch_name: str
    base_sha: str
    observed_ref_sha: str | None
    idempotency_key: str
    pending_action: str | None
    decision_digest: str
    may_create_branch: bool
    requires_reapproval: bool
    requires_human: bool
    merge_authority_granted: bool
    deployment_authority_granted: bool
    production_authority_granted: bool


def _digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _bad_sha(value: Any) -> bool:
    return not isinstance(value, str) or _SHA_RE.fullmatch(value) is None


def decide_branch_creation(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a guarded branch-creation attempt without mutating refs."""

    repository = observation.get("repository")
    branch_name = observation.get("branch_name")
    approved_base_sha = observation.get("approved_base_sha")
    observed_base_sha = observation.get("observed_current_base_sha")
    existing_branch_sha = observation.get("existing_branch_sha")
    create_result = observation.get("create_result", "not_attempted")
    idempotency_key = observation.get("idempotency_key")
    previous_pending_action = observation.get("previous_pending_action")

    reasons: list[str] = []
    outcome = "READY_TO_CREATE"
    may_create = True
    requires_reapproval = False
    requires_human = False
    pending_action: str | None = None
    observed_ref_sha = existing_branch_sha if isinstance(existing_branch_sha, str) else None

    if not isinstance(repository, str) or "/" not in repository:
        reasons.append("INVALID_REPOSITORY")
    if not isinstance(branch_name, str) or not _SAFE_BRANCH_RE.fullmatch(branch_name):
        reasons.append("INVALID_BRANCH_NAME")
    if _bad_sha(approved_base_sha):
        reasons.append("INVALID_APPROVED_BASE_SHA")
    if _bad_sha(observed_base_sha):
        reasons.append("INVALID_OBSERVED_BASE_SHA")
    if not isinstance(idempotency_key, str) or len(idempotency_key) < 12:
        reasons.append("INVALID_IDEMPOTENCY_KEY")
    if existing_branch_sha is not None and _bad_sha(existing_branch_sha):
        reasons.append("INVALID_EXISTING_BRANCH_SHA")
    if create_result not in {"success", "already_exists", "unknown", "failed", "not_attempted"}:
        reasons.append("INVALID_CREATE_RESULT")

    if reasons:
        outcome = "INVALID_INPUT"
        may_create = False
        requires_human = True
    elif approved_base_sha != observed_base_sha:
        outcome = "BLOCKED_BASE_DRIFT"
        reasons.append("BASE_SHA_DRIFT")
        may_create = False
        requires_reapproval = True
        requires_human = True
    elif existing_branch_sha and existing_branch_sha != approved_base_sha:
        outcome = "BLOCKED_BRANCH_COLLISION"
        reasons.append("EXISTING_BRANCH_NOT_AT_APPROVED_BASE")
        may_create = False
        requires_human = True
    elif existing_branch_sha == approved_base_sha:
        outcome = "RECONCILED_EXISTING"
        reasons.append("BRANCH_ALREADY_AT_APPROVED_BASE")
        may_create = False
    elif create_result == "unknown":
        outcome = "PENDING_READBACK_REQUIRED"
        reasons.append("UNKNOWN_EXTERNAL_WRITE_OUTCOME")
        may_create = False
        pending_action = previous_pending_action or f"branch-create:{idempotency_key}"
    elif create_result == "failed":
        outcome = "BLOCKED_PROVIDER_FAILURE"
        reasons.append("PROVIDER_CREATE_FAILED")
        may_create = False
        requires_human = True
    elif create_result == "success":
        outcome = "CREATED"
        reasons.append("CREATE_REPORTED_SUCCESS")
        may_create = False
        observed_ref_sha = approved_base_sha
    else:
        reasons.append("NO_EXISTING_BRANCH_AT_APPROVED_BASE")

    payload = {
        "node_id": "repo_delivery.branch-creation",
        "outcome": outcome,
        "reason_codes": reasons,
        "repository": repository or "",
        "branch_name": branch_name or "",
        "base_sha": approved_base_sha or "",
        "observed_ref_sha": observed_ref_sha,
        "idempotency_key": idempotency_key or "",
        "pending_action": pending_action,
        "may_create_branch": may_create,
        "requires_reapproval": requires_reapproval,
        "requires_human": requires_human,
    }

    decision = BranchCreationDecision(
        **payload,
        decision_digest=_digest(payload),
        merge_authority_granted=False,
        deployment_authority_granted=False,
        production_authority_granted=False,
    )
    return asdict(decision)
