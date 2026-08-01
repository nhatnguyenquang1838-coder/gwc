"""Replay-safe repo_delivery.base-drift-check decision helper."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class BaseDriftDecision:
    node_id: str
    outcome: str
    reason_codes: list[str]
    repository: str
    approved_base_sha: str
    observed_base_sha: str
    scope_hash: str
    invalidates_approval: bool
    requires_reapproval: bool
    may_continue: bool
    pending_action: str | None
    decision_digest: str
    merge_authority_granted: bool
    deployment_authority_granted: bool
    production_authority_granted: bool


def _digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _bad_sha(value: Any) -> bool:
    return not isinstance(value, str) or _SHA_RE.fullmatch(value) is None


def decide_base_drift(observation: Mapping[str, Any]) -> dict[str, Any]:
    repository = observation.get("repository")
    approved_base_sha = observation.get("approved_base_sha")
    observed_base_sha = observation.get("observed_base_sha")
    scope_hash = observation.get("scope_hash")
    pending_action = observation.get("pending_action")
    connector_status = observation.get("connector_status", "observed")

    reasons: list[str] = []
    outcome = "BASE_CURRENT"
    invalidates = False
    reapproval = False
    may_continue = True

    if not isinstance(repository, str) or "/" not in repository:
        reasons.append("INVALID_REPOSITORY")
    if _bad_sha(approved_base_sha):
        reasons.append("INVALID_APPROVED_BASE_SHA")
    if _bad_sha(observed_base_sha):
        reasons.append("INVALID_OBSERVED_BASE_SHA")
    if not isinstance(scope_hash, str) or not scope_hash.startswith("sha256:"):
        reasons.append("INVALID_SCOPE_HASH")
    if connector_status not in {"observed", "unavailable", "ambiguous"}:
        reasons.append("INVALID_CONNECTOR_STATUS")
    if pending_action is not None and not isinstance(pending_action, str):
        reasons.append("INVALID_PENDING_ACTION")

    if reasons:
        outcome = "INVALID_INPUT"
        invalidates = True
        reapproval = True
        may_continue = False
    elif connector_status in {"unavailable", "ambiguous"}:
        outcome = "BASE_OBSERVABILITY_BLOCKED"
        reasons.append("BASE_READBACK_UNAVAILABLE")
        invalidates = True
        may_continue = False
    elif pending_action:
        outcome = "RECONCILE_PENDING_ACTION_FIRST"
        reasons.append("PENDING_ACTION_REQUIRES_RECONCILIATION")
        may_continue = False
    elif approved_base_sha != observed_base_sha:
        outcome = "BASE_DRIFT_REAPPROVAL_REQUIRED"
        reasons.append("APPROVED_BASE_DIFFERS_FROM_OBSERVED_BASE")
        invalidates = True
        reapproval = True
        may_continue = False
    else:
        reasons.append("APPROVED_BASE_MATCHES_OBSERVED_BASE")

    payload = {
        "node_id": "repo_delivery.base-drift-check",
        "outcome": outcome,
        "reason_codes": reasons,
        "repository": repository or "",
        "approved_base_sha": approved_base_sha or "",
        "observed_base_sha": observed_base_sha or "",
        "scope_hash": scope_hash or "",
        "invalidates_approval": invalidates,
        "requires_reapproval": reapproval,
        "may_continue": may_continue,
        "pending_action": pending_action if isinstance(pending_action, str) else None,
    }

    decision = BaseDriftDecision(
        **payload,
        decision_digest=_digest(payload),
        merge_authority_granted=False,
        deployment_authority_granted=False,
        production_authority_granted=False,
    )
    return asdict(decision)
