"""Replay-safe repo_delivery.scoped-file-write decision helper."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ScopedFileWriteDecision:
    node_id: str
    outcome: str
    reason_codes: list[str]
    approved_paths: list[str]
    requested_paths: list[str]
    observed_diff_paths: list[str]
    idempotency_key: str
    pending_action: str | None
    may_write: bool
    requires_reconciliation: bool
    requires_human: bool
    decision_digest: str
    merge_authority_granted: bool
    deployment_authority_granted: bool
    production_authority_granted: bool


def _digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or item.startswith("/") or ".." in item.split("/"):
            return None
        items.append(item)
    return items


def decide_scoped_file_write(observation: Mapping[str, Any]) -> dict[str, Any]:
    approved_paths = _string_list(observation.get("approved_paths"))
    requested_paths = _string_list(observation.get("requested_paths"))
    observed_diff_paths = _string_list(observation.get("observed_diff_paths", []))
    idempotency_key = observation.get("idempotency_key")
    write_result = observation.get("write_result", "not_attempted")
    previous_pending_action = observation.get("previous_pending_action")

    reasons: list[str] = []
    outcome = "WRITE_ALLOWED"
    may_write = True
    requires_reconciliation = False
    requires_human = False
    pending_action: str | None = None

    if approved_paths is None or not approved_paths:
        reasons.append("INVALID_APPROVED_PATHS")
    if requested_paths is None or not requested_paths:
        reasons.append("INVALID_REQUESTED_PATHS")
    if observed_diff_paths is None:
        reasons.append("INVALID_OBSERVED_DIFF_PATHS")
    if not isinstance(idempotency_key, str) or len(idempotency_key) < 12:
        reasons.append("INVALID_IDEMPOTENCY_KEY")
    if write_result not in {"not_attempted", "success", "unknown", "failed"}:
        reasons.append("INVALID_WRITE_RESULT")
    if previous_pending_action is not None and not isinstance(previous_pending_action, str):
        reasons.append("INVALID_PREVIOUS_PENDING_ACTION")

    approved = set(approved_paths or [])
    requested = set(requested_paths or [])
    diff = set(observed_diff_paths or [])
    out_of_scope_requested = sorted(requested - approved)
    out_of_scope_diff = sorted(diff - approved)

    if reasons:
        outcome = "INVALID_INPUT"
        may_write = False
        requires_human = True
    elif out_of_scope_requested:
        outcome = "BLOCKED_OUT_OF_SCOPE_REQUEST"
        reasons.append("REQUESTED_PATH_OUTSIDE_APPROVED_SCOPE")
        reasons.extend(f"OUT_OF_SCOPE:{path}" for path in out_of_scope_requested)
        may_write = False
        requires_human = True
    elif out_of_scope_diff:
        outcome = "BLOCKED_OUT_OF_SCOPE_DIFF"
        reasons.append("OBSERVED_DIFF_OUTSIDE_APPROVED_SCOPE")
        reasons.extend(f"OUT_OF_SCOPE_DIFF:{path}" for path in out_of_scope_diff)
        may_write = False
        requires_human = True
        requires_reconciliation = True
    elif write_result == "unknown":
        outcome = "PENDING_READBACK_REQUIRED"
        reasons.append("UNKNOWN_EXTERNAL_WRITE_OUTCOME")
        may_write = False
        requires_reconciliation = True
        pending_action = previous_pending_action or f"scoped-write:{idempotency_key}"
    elif write_result == "failed":
        outcome = "BLOCKED_PROVIDER_FAILURE"
        reasons.append("PROVIDER_WRITE_FAILED")
        may_write = False
        requires_human = True
    elif write_result == "success" and diff == requested:
        outcome = "WRITE_RECONCILED"
        reasons.append("REQUESTED_PATHS_MATCH_OBSERVED_DIFF")
        may_write = False
    elif write_result == "success":
        outcome = "RECONCILE_DIFF_MISMATCH"
        reasons.append("WRITE_SUCCESS_DIFF_MISMATCH")
        may_write = False
        requires_reconciliation = True
    elif diff and diff == requested:
        outcome = "DUPLICATE_EFFECT_REPLAYED"
        reasons.append("REQUESTED_EFFECT_ALREADY_PRESENT")
        may_write = False
    else:
        reasons.append("REQUESTED_PATHS_WITHIN_APPROVED_SCOPE")

    payload = {
        "node_id": "repo_delivery.scoped-file-write",
        "outcome": outcome,
        "reason_codes": reasons,
        "approved_paths": sorted(approved_paths or []),
        "requested_paths": sorted(requested_paths or []),
        "observed_diff_paths": sorted(observed_diff_paths or []),
        "idempotency_key": idempotency_key or "",
        "pending_action": pending_action,
        "may_write": may_write,
        "requires_reconciliation": requires_reconciliation,
        "requires_human": requires_human,
    }

    decision = ScopedFileWriteDecision(
        **payload,
        decision_digest=_digest(payload),
        merge_authority_granted=False,
        deployment_authority_granted=False,
        production_authority_granted=False,
    )
    return asdict(decision)
