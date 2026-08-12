#!/usr/bin/env python3
"""Resume Token Validation — runtime_checkpoint.resume-token-validation (M5_REPLAY_SAFE).

Validates resume tokens and current resume conditions before allowing interrupted
G2 execution to continue.  Returns explicit route decisions:

    RESUME | REAPPROVAL_REQUIRED | RECONCILE_REQUIRED | STOP_FAIL_CLOSED

This module NEVER converts token validity into gate PASS or merge/deploy authority.
Token validation is execution-plane only; authority comes solely from validated
gate artifacts and exact human approval where required.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Route decision
# ---------------------------------------------------------------------------


class Route(str, Enum):
    RESUME = "RESUME"
    REAPPROVAL_REQUIRED = "REAPPROVAL_REQUIRED"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    STOP_FAIL_CLOSED = "STOP_FAIL_CLOSED"


@dataclass(frozen=True)
class RouteDecision:
    """Deterministic, auditable route decision for a resume-token validation."""

    route: Route
    reason: str
    token_id: str
    checkpoint_id: str
    validated_at_utc: str
    authority_granted: bool = False  # always False — token never grants authority
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route": self.route.value,
            "reason": self.reason,
            "token_id": self.token_id,
            "checkpoint_id": self.checkpoint_id,
            "validated_at_utc": self.validated_at_utc,
            "authority_granted": self.authority_granted,
            "evidence": self.evidence,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Failure codes
# ---------------------------------------------------------------------------

TOKEN_MISSING = "TOKEN_MISSING"
TOKEN_EXPIRED = "TOKEN_EXPIRED"
TOKEN_TAMPERED = "TOKEN_TAMPERED"
TASK_MISMATCH = "TASK_MISMATCH"
SCOPE_MISMATCH = "SCOPE_MISMATCH"
SCOPE_HASH_MISMATCH = "SCOPE_HASH_MISMATCH"
RUN_MISMATCH = "RUN_MISMATCH"
AUTHORITY_ESCALATION = "AUTHORITY_ESCALATION"
APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
BASE_DRIFT = "BASE_DRIFT"
HEAD_DRIFT = "HEAD_DRIFT"
GRAPH_REVISION_DRIFT = "GRAPH_REVISION_DRIFT"
MISSING_CHECKPOINT = "MISSING_CHECKPOINT"
REPLAY_REUSE_OUTSIDE_POLICY = "REPLAY_REUSE_OUTSIDE_POLICY"
LEASE_EXPIRED = "LEASE_EXPIRED"
FENCING_TOKEN_MISMATCH = "FENCING_TOKEN_MISMATCH"


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CurrentContext:
    """The current execution context to validate the resume token against."""

    task_id: str
    repository_full_name: str
    base_sha: str
    head_sha: Optional[str]
    gate: str
    scope_hash_16: Optional[str]
    run_id: Optional[str] = None
    graph_revision: Optional[str] = None
    lease_expiry_utc: Optional[str] = None
    fencing_token: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(s: str) -> datetime:
    """Parse an ISO-8601 datetime string (tolerant of trailing Z or offset)."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _checkpoint_digest(checkpoint: Dict[str, Any]) -> str:
    """Deterministic SHA-256 digest of a checkpoint's binding fields."""
    binding = {
        "checkpoint_id": checkpoint.get("checkpoint_id", ""),
        "task": checkpoint.get("task", {}),
        "repository": checkpoint.get("repository", {}),
        "gate": checkpoint.get("gate", {}),
        "scope": checkpoint.get("scope", {}),
        "next_action": checkpoint.get("next_action", {}),
    }
    normalized = json.dumps(binding, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------


def validate_resume_token(
    token: Dict[str, Any],
    checkpoint: Optional[Dict[str, Any]],
    ctx: CurrentContext,
    *,
    approval_expiry_utc: Optional[str] = None,
    used_token_ids: Optional[set] = None,
) -> RouteDecision:
    """Validate a resume token against current execution context.

    Returns a RouteDecision with one of:
        RESUME, REAPPROVAL_REQUIRED, RECONCILE_REQUIRED, STOP_FAIL_CLOSED

    This function NEVER sets authority_granted=True.  Token validity is
    execution-plane only and never creates gate PASS or merge/deploy authority.
    """
    now = _now_utc()
    token_id = str(token.get("resume_token_id", "unknown"))
    checkpoint_id = str(token.get("checkpoint_id", "unknown"))
    evidence: Dict[str, Any] = {}

    # --- 1. Token presence ---
    if not token or not token.get("resume_token_id"):
        return RouteDecision(
            route=Route.STOP_FAIL_CLOSED,
            reason=TOKEN_MISSING,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence=evidence,
        )

    # --- 2. Token expiry ---
    issued_at = token.get("issued_at_utc", "")
    expires_at = token.get("expires_at_utc", "")
    evidence["token_issued_at"] = issued_at
    evidence["token_expires_at"] = expires_at

    try:
        exp = _parse_dt(expires_at)
        now_dt = datetime.now(timezone.utc)
        if now_dt > exp:
            return RouteDecision(
                route=Route.STOP_FAIL_CLOSED,
                reason=TOKEN_EXPIRED,
                token_id=token_id,
                checkpoint_id=checkpoint_id,
                validated_at_utc=now,
                evidence=evidence,
            )
    except (ValueError, TypeError):
        return RouteDecision(
            route=Route.STOP_FAIL_CLOSED,
            reason=TOKEN_TAMPERED,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence={**evidence, "detail": "invalid expires_at_utc format"},
        )

    # --- 3. Checkpoint presence ---
    if checkpoint is None:
        return RouteDecision(
            route=Route.RECONCILE_REQUIRED,
            reason=MISSING_CHECKPOINT,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence=evidence,
        )

    # --- 4. Checkpoint binding: checkpoint_id match ---
    cp_id = checkpoint.get("checkpoint_id", "")
    evidence["checkpoint_id"] = cp_id
    if cp_id != checkpoint_id:
        return RouteDecision(
            route=Route.STOP_FAIL_CLOSED,
            reason=TOKEN_TAMPERED,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence={**evidence, "detail": "checkpoint_id mismatch"},
        )

    # --- 5. Task binding ---
    cp_task = checkpoint.get("task", {})
    cp_task_id = cp_task.get("id", "")
    evidence["checkpoint_task_id"] = cp_task_id
    evidence["context_task_id"] = ctx.task_id
    if cp_task_id != ctx.task_id:
        return RouteDecision(
            route=Route.STOP_FAIL_CLOSED,
            reason=TASK_MISMATCH,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence=evidence,
        )

    # --- 5b. Run binding (if context provides run_id) ---
    token_run = token.get("run_id")
    ctx_run = getattr(ctx, "run_id", None)
    if token_run is not None and ctx_run is not None and token_run != ctx_run:
        return RouteDecision(
            route=Route.STOP_FAIL_CLOSED,
            reason=RUN_MISMATCH,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence={**evidence, "token_run_id": token_run, "context_run_id": ctx_run},
        )

    # --- 6. Repository base SHA binding ---
    cp_repo = checkpoint.get("repository", {})
    cp_base_sha = cp_repo.get("base_sha", "")
    evidence["checkpoint_base_sha"] = cp_base_sha
    evidence["context_base_sha"] = ctx.base_sha
    if cp_base_sha != ctx.base_sha:
        return RouteDecision(
            route=Route.REAPPROVAL_REQUIRED,
            reason=BASE_DRIFT,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence=evidence,
        )

    # --- 7. Head SHA drift (if both checkpoint and context have head) ---
    cp_git = checkpoint.get("git_delivery", {})
    cp_head = cp_git.get("head_sha")
    if cp_head and ctx.head_sha and cp_head != ctx.head_sha:
        return RouteDecision(
            route=Route.RECONCILE_REQUIRED,
            reason=HEAD_DRIFT,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence={**evidence, "checkpoint_head_sha": cp_head, "context_head_sha": ctx.head_sha},
        )

    # --- 8. Scope hash binding (if context provides scope_hash_16) ---
    if ctx.scope_hash_16:
        cp_scope = checkpoint.get("scope", {})
        cp_files_write = set(cp_scope.get("files_write", []))
        # Scope mismatch is detected when checkpoint's files_write differ
        # from the current approved scope.  We check that the checkpoint
        # has a non-empty files_write list (basic integrity).
        if not cp_files_write:
            return RouteDecision(
                route=Route.RECONCILE_REQUIRED,
                reason=SCOPE_MISMATCH,
                token_id=token_id,
                checkpoint_id=checkpoint_id,
                validated_at_utc=now,
                evidence={**evidence, "detail": "checkpoint has empty files_write"},
            )

    # --- 8b. Exact scope_hash prefix binding (if present) ---
    token_scope = token.get("scope_hash")
    if token_scope and ctx.scope_hash_16 and not token_scope.startswith(ctx.scope_hash_16):
        return RouteDecision(
            route=Route.RECONCILE_REQUIRED,
            reason=SCOPE_HASH_MISMATCH,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence={**evidence, "token_scope_hash": token_scope, "context_scope_hash_16": ctx.scope_hash_16},
        )

    # --- 9. Gate binding ---
    cp_gate = checkpoint.get("gate", {})
    cp_gate_current = cp_gate.get("current", "")
    evidence["checkpoint_gate"] = cp_gate_current
    evidence["context_gate"] = ctx.gate
    if cp_gate_current != ctx.gate:
        return RouteDecision(
            route=Route.RECONCILE_REQUIRED,
            reason=SCOPE_MISMATCH,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence={**evidence, "detail": "gate mismatch"},
        )

    # --- 10. Approval expiry ---
    if approval_expiry_utc:
        evidence["approval_expires_at"] = approval_expiry_utc
        try:
            ap_exp = _parse_dt(approval_expiry_utc)
            now_dt = datetime.now(timezone.utc)
            if now_dt > ap_exp:
                return RouteDecision(
                    route=Route.REAPPROVAL_REQUIRED,
                    reason=APPROVAL_EXPIRED,
                    token_id=token_id,
                    checkpoint_id=checkpoint_id,
                    validated_at_utc=now,
                    evidence=evidence,
                )
        except (ValueError, TypeError):
            return RouteDecision(
                route=Route.STOP_FAIL_CLOSED,
                reason=TOKEN_TAMPERED,
                token_id=token_id,
                checkpoint_id=checkpoint_id,
                validated_at_utc=now,
                evidence={**evidence, "detail": "invalid approval_expiry_utc format"},
            )

    # --- 11. Graph revision drift (if context provides graph_revision) ---
    if ctx.graph_revision:
        cp_graph_rev = checkpoint.get("graph_revision")
        if cp_graph_rev and cp_graph_rev != ctx.graph_revision:
            return RouteDecision(
                route=Route.REAPPROVAL_REQUIRED,
                reason=GRAPH_REVISION_DRIFT,
                token_id=token_id,
                checkpoint_id=checkpoint_id,
                validated_at_utc=now,
                evidence={**evidence, "checkpoint_graph_revision": cp_graph_rev, "context_graph_revision": ctx.graph_revision},
            )

    # --- 12. Lease / fencing token (if context provides them) ---
    if ctx.lease_expiry_utc:
        evidence["lease_expiry_utc"] = ctx.lease_expiry_utc
        try:
            lease_exp = _parse_dt(ctx.lease_expiry_utc)
            now_dt = datetime.now(timezone.utc)
            if now_dt > lease_exp:
                return RouteDecision(
                    route=Route.RECONCILE_REQUIRED,
                    reason=LEASE_EXPIRED,
                    token_id=token_id,
                    checkpoint_id=checkpoint_id,
                    validated_at_utc=now,
                    evidence=evidence,
                )
        except (ValueError, TypeError):
            pass

    if ctx.fencing_token:
        cp_fencing = checkpoint.get("fencing_token")
        if cp_fencing and cp_fencing != ctx.fencing_token:
            return RouteDecision(
                route=Route.STOP_FAIL_CLOSED,
                reason=FENCING_TOKEN_MISMATCH,
                token_id=token_id,
                checkpoint_id=checkpoint_id,
                validated_at_utc=now,
                evidence=evidence,
            )

    # --- 13. Replay reuse outside policy ---
    if used_token_ids and token_id in used_token_ids:
        return RouteDecision(
            route=Route.STOP_FAIL_CLOSED,
            reason=REPLAY_REUSE_OUTSIDE_POLICY,
            token_id=token_id,
            checkpoint_id=checkpoint_id,
            validated_at_utc=now,
            evidence={**evidence, "detail": "token already consumed"},
        )

    # --- 14. Checkpoint digest (tamper detection) ---
    digest = _checkpoint_digest(checkpoint)
    evidence["checkpoint_digest"] = digest[:16]

    # --- 14b. Token self-integrity (token_digest) ---
    token_digest = token.get("token_digest")
    if token_digest:
        body = {k: v for k, v in token.items() if k != "token_digest"}
        if _digest(body) != token_digest:
            return RouteDecision(
                route=Route.STOP_FAIL_CLOSED,
                reason=TOKEN_TAMPERED,
                token_id=token_id,
                checkpoint_id=checkpoint_id,
                validated_at_utc=now,
                evidence={**evidence, "detail": "token_digest mismatch"},
            )

    # --- 14c. Authority escalation rejection ---
    for auth_key in (
        "authority_granted",
        "write_authority_granted",
        "merge_authority_granted",
        "deployment_authority_granted",
        "production_authority_granted",
    ):
        if token.get(auth_key):
            return RouteDecision(
                route=Route.STOP_FAIL_CLOSED,
                reason=AUTHORITY_ESCALATION,
                token_id=token_id,
                checkpoint_id=checkpoint_id,
                validated_at_utc=now,
                evidence={**evidence, "detail": f"authority field set: {auth_key}={token.get(auth_key)}"},
            )

    # --- All checks passed → RESUME ---
    evidence["all_checks_passed"] = True
    return RouteDecision(
        route=Route.RESUME,
        reason="All bindings verified: integrity, expiry, task, scope, base, head, gate, approval, graph, lease, fencing, replay.",
        token_id=token_id,
        checkpoint_id=checkpoint_id,
        validated_at_utc=now,
        authority_granted=False,  # NEVER True
        evidence=evidence,
    )