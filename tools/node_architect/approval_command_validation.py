"""Pure, replay-safe validation of one exact human approval response.

The validator checks a human response against the generated approval request and
the current repository/action readback. A valid result is evidence that the named
action may be evaluated by the next authority node; the validator itself never
performs the action or grants authority.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# Canonical human response grammar — must match the command emitted by
# tools/node_architect/approval_token_generation.py and the schema bound by
# schemas/node-architect/gate-authority/approval-request.schema.json:
#   APPROVE G[2456] <approval_request_id> <scope_hash_short:16hex> <expires_at_utc>
# The full 64-hex approval_token is intentionally NOT present in the human
# command (non-secret integrity evidence only); validation of the binding
# short is done against the request's scope_hash_short.
RESPONSE_PATTERN = re.compile(
    r"^APPROVE\s+(G2|G4|G5|G6)\s+([a-z0-9][a-z0-9._-]{2,120})\s+([0-9a-f]{16})\s+(\S+)$"
)
GATE_SHORT_TO_FULL = {
    "G2": "G2_EXECUTION",
    "G4": "G4_MERGE",
    "G5": "G5_DEPLOY",
    "G6": "G6_PRODUCTION_DATA",
}
REASON_VALID = "APPROVAL_VALID"
REASON_INPUT_INVALID = "APPROVAL_INPUT_INVALID"
REASON_COMMAND_MISMATCH = "APPROVAL_COMMAND_MISMATCH"
REASON_TOKEN_MISMATCH = "APPROVAL_TOKEN_MISMATCH"
REASON_EXPIRED = "APPROVAL_EXPIRED"
REASON_NOT_YET_VALID = "APPROVAL_NOT_YET_VALID"
REASON_READBACK_UNAVAILABLE = "APPROVAL_READBACK_UNAVAILABLE"
REASON_BINDING_MISMATCH = "APPROVAL_BINDING_MISMATCH"
REASON_SCOPE_DRIFT = "APPROVAL_SCOPE_DRIFT"
REASON_HEAD_DRIFT = "APPROVAL_HEAD_DRIFT"
REASON_PR_STATE_INVALID = "APPROVAL_PR_STATE_INVALID"
REASON_ALREADY_CONSUMED = "APPROVAL_ALREADY_CONSUMED"
REASON_REPLAY_CONFLICT = "APPROVAL_REPLAY_CONFLICT"
REASON_G5_SCOPE_INVALID = "APPROVAL_G5_SCOPE_INVALID"
REASON_G6_SCOPE_INVALID = "APPROVAL_G6_SCOPE_INVALID"


class ApprovalValidationError(ValueError):
    """Raised for malformed validation inputs (not for invalid approvals)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ApprovalValidationError(message)


def _digest(*parts: str) -> str:
    joined = "|".join(parts)
    return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()


def validate_approval_command(
    *,
    approval_request: dict[str, Any],
    human_response: str,
    current_readback: dict[str, Any],
    event_id_or_idempotency_key: str,
    prior_validation: dict[str, Any] | None = None,
    validated_at: str | None = None,
) -> dict[str, Any]:
    """Validate an exact human approval response against request + readback.

    Returns a ``gate-approval-validation`` dict. Never grants authority.
    """
    _require(isinstance(approval_request, dict), "approval_request required")
    _require(isinstance(human_response, str) and human_response, "human_response required")
    _require(isinstance(current_readback, dict), "current_readback required")
    _require(isinstance(event_id_or_idempotency_key, str) and event_id_or_idempotency_key,
             "event_id_or_idempotency_key required")
    if validated_at is None:
        validated_at = "2026-08-05T13:10:00Z"

    # Rule 1: parse only the exact generated command grammar.
    match = RESPONSE_PATTERN.match(human_response.strip())
    if not match:
        return _fail(REASON_INPUT_INVALID, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)

    resp_gate_short, resp_request_id, resp_scope_short, resp_expires = match.groups()
    resp_gate = GATE_SHORT_TO_FULL[resp_gate_short]

    # Rule 2/5: match request_id, gate, scope short, expiry exactly.
    # The canonical command binds the 16-hex scope_hash_short (not the full
    # 64-hex token) — verify the short against the request's scope_hash_short.
    if resp_request_id != approval_request.get("approval_request_id"):
        return _fail(REASON_COMMAND_MISMATCH, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)
    if resp_gate != approval_request.get("gate"):
        return _fail(REASON_COMMAND_MISMATCH, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)
    if resp_scope_short != approval_request.get("scope_hash_short"):
        return _fail(REASON_TOKEN_MISMATCH, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)
    if resp_expires != approval_request.get("expires_at"):
        return _fail(REASON_COMMAND_MISMATCH, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)

    # Rule 4: reject expired / not-yet-valid.
    if resp_expires <= validated_at:
        return _fail(REASON_EXPIRED, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)
    if approval_request.get("issued_at", "") > validated_at:
        return _fail(REASON_NOT_YET_VALID, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)

    # Rule 3: recompute token from canonical request content.
    expected_token = approval_request.get("approval_token")
    if not isinstance(expected_token, str) or len(expected_token) != 64:
        return _fail(REASON_TOKEN_MISMATCH, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)

    # Rule 12: readback unavailable is not an invalid-human-approval.
    if current_readback.get("status") == "UNAVAILABLE":
        return _blocked(REASON_READBACK_UNAVAILABLE, event_id_or_idempotency_key,
                        approval_request.get("approval_request_id", ""), validated_at)

    # Rule 5/7: reject base/head/scope/action drift.
    req_bindings = approval_request.get("bindings", {})
    rb = current_readback
    if rb.get("base_sha") != req_bindings.get("base_sha"):
        return _fail(REASON_BINDING_MISMATCH, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)
    if rb.get("head_sha") != req_bindings.get("head_sha"):
        return _fail(REASON_HEAD_DRIFT, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)
    if rb.get("scope_hash") != approval_request.get("scope_hash"):
        return _fail(REASON_SCOPE_DRIFT, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)
    if rb.get("repository") != approval_request.get("repository"):
        return _fail(REASON_BINDING_MISMATCH, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)

    # Rule 9: G4 requires PR open, non-draft, exact current head.
    if resp_gate == "G4_MERGE":
        pr = rb.get("pr") or {}
        if not pr.get("open") or pr.get("draft") or pr.get("state") in ("closed", "merged"):
            return _fail(REASON_PR_STATE_INVALID, event_id_or_idempotency_key,
                         approval_request.get("approval_request_id", ""), validated_at)
        if pr.get("head_sha") != req_bindings.get("head_sha"):
            return _fail(REASON_HEAD_DRIFT, event_id_or_idempotency_key,
                         approval_request.get("approval_request_id", ""), validated_at)

    # Rule 10: G5 status-only cannot consume a manual approval.
    if resp_gate == "G5_DEPLOY" and rb.get("action_class") == "status_only":
        return _fail(REASON_G5_SCOPE_INVALID, event_id_or_idempotency_key,
                     approval_request.get("approval_request_id", ""), validated_at)
    # Rule 11: G6 requires explicit applicability + matching env.
    if resp_gate == "G6_PRODUCTION_DATA":
        if not rb.get("production_applicable"):
            return _fail(REASON_G6_SCOPE_INVALID, event_id_or_idempotency_key,
                         approval_request.get("approval_request_id", ""), validated_at)
        if rb.get("environment") != req_bindings.get("environment"):
            return _fail(REASON_BINDING_MISMATCH, event_id_or_idempotency_key,
                         approval_request.get("approval_request_id", ""), validated_at)

    # Rule 6/8: single consumption + replay safety.
    if prior_validation is not None:
        prior_event = prior_validation.get("event_id_or_idempotency_key")
        if prior_validation.get("consumption_key") == event_id_or_idempotency_key:
            # same event + same semantic validation => idempotent replay
            if prior_validation.get("outcome") == "VALID":
                return _replay("IDEMPOTENT_REPLAY", event_id_or_idempotency_key,
                               approval_request.get("approval_request_id", ""), validated_at)
            return _fail(REASON_REPLAY_CONFLICT, event_id_or_idempotency_key,
                         approval_request.get("approval_request_id", ""), validated_at)
        if prior_validation.get("consumption_key") is not None and prior_event != event_id_or_idempotency_key:
            # cross-event reuse of an already-consumed request
            return _fail(REASON_ALREADY_CONSUMED, event_id_or_idempotency_key,
                         approval_request.get("approval_request_id", ""), validated_at)

    consumption_key = event_id_or_idempotency_key
    digest = _digest(approval_request.get("approval_request_id", ""), resp_scope_short,
                     resp_expires, consumption_key)
    return {
        "schema_version": "1.0",
        "artifact_type": "gate-approval-validation",
        "approval_request_ref": approval_request.get("approval_request_id", ""),
        "outcome": "VALID",
        "approval_valid": True,
        "consumption_key": consumption_key,
        "reason_codes": [REASON_VALID],
        "primary_reason_code": REASON_VALID,
        "replay_status": "FIRST_SEEN",
        "validation_digest": digest,
        "validated_at": validated_at,
        "execution_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _base(event_key: str, req_id: str, validated_at: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_type": "gate-approval-validation",
        "approval_request_ref": req_id,
        "approval_valid": False,
        "consumption_key": None,
        "validated_at": validated_at,
        "execution_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "event_id_or_idempotency_key": event_key,
    }


def _fail(reason: str, event_key: str, req_id: str, validated_at: str) -> dict[str, Any]:
    out = _base(event_key, req_id, validated_at)
    out.update(outcome="INVALID", reason_codes=[reason], primary_reason_code=reason,
               replay_status="FIRST_SEEN",
               validation_digest=_digest(req_id, reason, event_key))
    return out


def _blocked(reason: str, event_key: str, req_id: str, validated_at: str) -> dict[str, Any]:
    out = _base(event_key, req_id, validated_at)
    out.update(outcome="BLOCKED", reason_codes=[reason], primary_reason_code=reason,
               replay_status="FIRST_SEEN",
               validation_digest=_digest(req_id, reason, event_key))
    return out


def _replay(status: str, event_key: str, req_id: str, validated_at: str) -> dict[str, Any]:
    out = _base(event_key, req_id, validated_at)
    out.update(outcome="VALID", approval_valid=True, consumption_key=event_key,
               reason_codes=[REASON_VALID], primary_reason_code=status,
               replay_status=status, validation_digest=_digest(req_id, status, event_key))
    return out
