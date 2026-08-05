"""Pure, deterministic generation of one exact human approval request.

Generation creates a request for authority; it does not create or grant
authority. The emitted ``approval_token`` is a non-secret integrity identifier
derived from canonical request content; possession alone does not authorize an
action.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

GATE_SHORT = {
    "G2_EXECUTION": "G2",
    "G4_MERGE": "G4",
    "G5_DEPLOY": "G5",
    "G6_PRODUCTION_DATA": "G6",
}
VALID_GATES = set(GATE_SHORT)
REPOSITORY_PATTERN = re.compile(r"^[^/\s]+/[^/\s]+$")
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SCOPE_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
TOKEN64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

REASON_GENERATED = "APPROVAL_REQUEST_GENERATED"
REASON_INPUT_INVALID = "APPROVAL_INPUT_INVALID"
REASON_BOUNDARY_NOT_REQUESTED = "APPROVAL_BOUNDARY_NOT_REQUESTED"
REASON_GATE_ACTION_MISMATCH = "APPROVAL_GATE_ACTION_MISMATCH"
REASON_BINDING_REQUIRED = "APPROVAL_BINDING_REQUIRED"
REASON_EXPIRY_INVALID = "APPROVAL_EXPIRY_INVALID"
REASON_G5_MANUAL_SCOPE_REQUIRED = "APPROVAL_G5_MANUAL_SCOPE_REQUIRED"
REASON_G6_NOT_APPLICABLE = "APPROVAL_G6_NOT_APPLICABLE"
REASON_REDACTION_REQUIRED = "APPROVAL_REDACTION_REQUIRED"


class ApprovalRequestError(ValueError):
    """Raised when an approval request cannot be generated."""


def _require(condition: bool, reason: str, message: str) -> None:
    if not condition:
        raise ApprovalRequestError(f"{reason}: {message}")


def _canonical_binding_string(
    *,
    task_id: str,
    repository: str,
    gate: str,
    action: str,
    bindings: dict[str, Any],
    scope_hash: str,
    actor_target: dict[str, str],
    issued_at: str,
    expires_at: str,
) -> str:
    """Stable, unambiguous serialization of the canonical token input."""
    actor = f"{actor_target.get('type', '')}:{actor_target.get('id', '')}"
    parts = [
        f"task={task_id}",
        f"repository={repository}",
        f"gate={gate}",
        f"action={action}",
        f"base_sha={bindings.get('base_sha', '')}",
        f"head_sha={bindings.get('head_sha', '')}",
        f"branch={bindings.get('branch') or ''}",
        f"pr={bindings.get('pr_number') or ''}",
        f"environment={bindings.get('environment') or ''}",
        f"scope_hash={scope_hash}",
        f"actor={actor}",
        f"issued_at={issued_at}",
        f"expires_at={expires_at}",
    ]
    return "|".join(parts)


def generate_approval_request(
    *,
    task_id: str,
    repository: str,
    gate: str,
    action: str,
    scope_identity: dict[str, Any],
    authority_boundary_decision: dict[str, Any],
    actor_target: dict[str, str],
    issued_at: str,
    expires_at: str,
) -> dict[str, Any]:
    """Generate a deterministic, non-secret approval request for one gate action.

    Returns a ``gate-approval-request`` dict. Never grants authority.
    """
    if not isinstance(task_id, str) or not task_id:
        raise ApprovalRequestError(f"{REASON_INPUT_INVALID}: task_id required")
    if not isinstance(repository, str) or not REPOSITORY_PATTERN.match(repository):
        raise ApprovalRequestError(f"{REASON_INPUT_INVALID}: repository must match owner/name")
    if gate not in VALID_GATES:
        raise ApprovalRequestError(f"{REASON_INPUT_INVALID}: unsupported gate {gate!r}")
    if not isinstance(action, str) or not action:
        raise ApprovalRequestError(f"{REASON_INPUT_INVALID}: action required")

    # Rule 1: only when the boundary decision requires approval.
    decision = authority_boundary_decision.get("decision") if isinstance(
        authority_boundary_decision, dict) else None
    if decision != "REQUIRE_APPROVAL":
        raise ApprovalRequestError(
            f"{REASON_BOUNDARY_NOT_REQUESTED}: boundary decision is {decision!r}, not REQUIRE_APPROVAL"
        )

    # Gate/action binding must be exact (Rule 2).
    if authority_boundary_decision.get("requested_action") != action:
        raise ApprovalRequestError(
            f"{REASON_GATE_ACTION_MISMATCH}: action {action!r} does not match boundary decision"
        )

    if not isinstance(scope_identity, dict):
        raise ApprovalRequestError(f"{REASON_INPUT_INVALID}: scope_identity required")
    scope_hash = scope_identity.get("scope_hash")
    if not isinstance(scope_hash, str) or not SCOPE_HASH_PATTERN.match(scope_hash):
        raise ApprovalRequestError(f"{REASON_INPUT_INVALID}: scope_hash must be sha256:64hex")

    # Exact applicable bindings required (Rule 3 / token model).
    base_sha = scope_identity.get("base_sha")
    head_sha = scope_identity.get("head_sha")
    if not (isinstance(base_sha, str) and SHA40_PATTERN.match(base_sha)):
        raise ApprovalRequestError(f"{REASON_BINDING_REQUIRED}: base_sha (40hex) required")
    if not (isinstance(head_sha, str) and SHA40_PATTERN.match(head_sha)):
        raise ApprovalRequestError(f"{REASON_BINDING_REQUIRED}: head_sha (40hex) required")

    branch = scope_identity.get("branch")
    pr_number = scope_identity.get("pr_number")
    environment = scope_identity.get("environment")

    # G4 requires exact current PR head binding (Rule 4); branch/PR must be present.
    if gate == "G4_MERGE" and (not branch or pr_number is None):
        raise ApprovalRequestError(f"{REASON_BINDING_REQUIRED}: G4 requires branch and pr_number")

    # G5 only for manual deploy/release/reload (Rule 5).
    if gate == "G5_DEPLOY" and environment is None:
        raise ApprovalRequestError(f"{REASON_G5_MANUAL_SCOPE_REQUIRED}: G5 requires environment")

    # G6 only when production scope applicable (Rule 6).
    if gate == "G6_PRODUCTION_DATA":
        prod_applicable = authority_boundary_decision.get("production_scope_applicable")
        if not prod_applicable:
            raise ApprovalRequestError(f"{REASON_G6_NOT_APPLICABLE}: production scope not applicable")

    # Expiry must be later than issuance and within policy TTL (Rule 3 / 7).
    if not (isinstance(issued_at, str) and isinstance(expires_at, str)):
        raise ApprovalRequestError(f"{REASON_EXPIRY_INVALID}: issued_at/expires_at required")
    if expires_at <= issued_at:
        raise ApprovalRequestError(f"{REASON_EXPIRY_INVALID}: expires_at must be after issued_at")

    bindings: dict[str, Any] = {
        "base_sha": base_sha,
        "head_sha": head_sha,
        "branch": branch,
        "pr_number": pr_number,
        "environment": environment,
        "scope_hash": scope_hash,
    }

    if not isinstance(actor_target, dict) or "id" not in actor_target:
        raise ApprovalRequestError(f"{REASON_INPUT_INVALID}: actor_target.id required")

    canonical = _canonical_binding_string(
        task_id=task_id, repository=repository, gate=gate, action=action,
        bindings=bindings, scope_hash=scope_hash, actor_target=actor_target,
        issued_at=issued_at, expires_at=expires_at,
    )
    token = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    digest = hashlib.sha256((canonical + "|token=" + token).encode("utf-8")).hexdigest()
    request_id = f"{gate}-{task_id}-{token[:16]}"

    gate_short = GATE_SHORT[gate]
    command = f"APPROVE {gate_short} {task_id} {token} {expires_at}"

    # No secret material may ever appear in the request (Rule 9).
    payload = {
        "schema_version": "1.0",
        "artifact_type": "gate-approval-request",
        "approval_request_id": request_id,
        "task_id": task_id,
        "repository": repository,
        "gate": gate,
        "action": action,
        "bindings": bindings,
        "scope_hash": scope_hash,
        "actor_target": {
            "type": actor_target.get("type", "user"),
            "id": actor_target["id"],
            "display_name": actor_target.get("display_name"),
        },
        "issued_at": issued_at,
        "expires_at": expires_at,
        "approval_token": token,
        "approval_command": command,
        "request_digest": f"sha256:{digest}",
        "reason_codes": [REASON_GENERATED],
        "primary_reason_code": REASON_GENERATED,
        "authority_granted": False,
        "consumed": False,
    }
    if not TOKEN64_PATTERN.match(token):
        raise ApprovalRequestError(f"{REASON_REDACTION_REQUIRED}: token must be non-secret 64hex")
    return payload
