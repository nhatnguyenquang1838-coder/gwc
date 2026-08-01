"""Replay-safe Draft PR creation decision helper for repo_delivery.draft-pr-creation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class DraftPrDecision:
    outcome: str
    reason_codes: list[str]
    repository: str
    base_branch: str
    branch: str
    base_sha: str
    head_sha: str
    pr_number: int | None
    idempotency_key: str
    decision_digest: str
    merge_authority_granted: bool = False
    deployment_authority_granted: bool = False
    production_authority_granted: bool = False


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def decide_draft_pr_creation(evidence: Mapping[str, Any]) -> dict[str, Any]:
    repository = str(evidence.get("repository", ""))
    base_branch = str(evidence.get("base_branch", "main"))
    branch = str(evidence.get("branch", ""))
    base_sha = str(evidence.get("base_sha", ""))
    head_sha = str(evidence.get("head_sha", ""))
    connector_status = evidence.get("connector_status", "available")
    last_action_state = evidence.get("last_action_state", "none")
    pr = evidence.get("pr")
    reasons: list[str] = []

    if not repository:
        reasons.append("REPOSITORY_MISSING")
    if not branch:
        reasons.append("BRANCH_MISSING")
    if not base_branch:
        reasons.append("BASE_BRANCH_MISSING")
    if not _is_sha(base_sha):
        reasons.append("INVALID_BASE_SHA")
    if not _is_sha(head_sha):
        reasons.append("INVALID_HEAD_SHA")
    if connector_status != "available":
        reasons.append("PR_READBACK_UNAVAILABLE")
    if last_action_state == "unknown":
        reasons.append("UNKNOWN_CREATE_OUTCOME_REQUIRES_READBACK")

    pr_number = None
    outcome = "CREATE_DRAFT_PR"
    if isinstance(pr, Mapping):
        pr_number = pr.get("number")
        if pr.get("state") != "open":
            reasons.append("PR_NOT_OPEN")
        if pr.get("base") != base_branch:
            reasons.append("PR_BASE_MISMATCH")
        if pr.get("head") != branch:
            reasons.append("PR_HEAD_BRANCH_MISMATCH")
        if pr.get("head_sha") != head_sha:
            reasons.append("PR_HEAD_SHA_MISMATCH")
        if pr.get("merged") is True:
            reasons.append("PR_ALREADY_MERGED")
        if pr.get("draft") is True and not reasons:
            outcome = "DRAFT_PR_BOUND"
        elif pr.get("draft") is False:
            reasons.append("PR_NOT_DRAFT")
            outcome = "BLOCKED"
    elif pr is not None:
        reasons.append("INVALID_PR_READBACK")

    if "PR_READBACK_UNAVAILABLE" in reasons or "UNKNOWN_CREATE_OUTCOME_REQUIRES_READBACK" in reasons:
        outcome = "PENDING_READBACK"
    elif reasons and outcome != "BLOCKED":
        outcome = "BLOCKED"

    idem = _digest({"repository": repository, "base_branch": base_branch, "branch": branch, "base_sha": base_sha, "head_sha": head_sha})
    return asdict(DraftPrDecision(
        outcome=outcome,
        reason_codes=sorted(set(reasons)) or ["DRAFT_PR_ACTION_SAFE"],
        repository=repository,
        base_branch=base_branch,
        branch=branch,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_number=pr_number,
        idempotency_key=idem,
        decision_digest=_digest({"outcome": outcome, "reasons": sorted(set(reasons)), "idempotency_key": idem}),
    ))
