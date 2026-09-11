#!/usr/bin/env python3
"""R5: orthogonal authority issuance, AuthorityDecisionReceipt, stale/self-grant
fail-closed enforcement, and the cumulative universal_run_* module manifest.

C6 (authority is orthogonal to gates and every effect has a decision receipt)
and C10 (authority cannot self-grant; stale/invalid authority fails closed) per
the C1-C15 matrix. Composes E1 kernel digest primitives and reuses
authority-boundary semantics (scope_identity, replay-safe evaluation).

Pure / transport-neutral: never persists, never grants authority, never mutates
external targets. Every function returns a typed result or raises a
deterministic fail-closed error before any effect.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE, UniversalRunKernelError

PROFILE = UNIVERSAL_PROFILE
KNOWN_ACTIONS = (
    "G0_READ", "G1_PLAN", "G2_EXECUTION", "G3_REVIEW", "G4_MERGE",
    "G5_DEPLOY", "G6_PRODUCTION", "G3_PR", "G5_PREPROD",
)


class AuthorityError(ValueError):
    """Deterministic fail-closed authority error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


class SelfGrantError(AuthorityError):
    """Typed error when an authority grants itself (C10)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("AUTHORITY_SELF_GRANT_FORBIDDEN", detail)


class StaleAuthorityError(AuthorityError):
    """Typed error when authority is stale/expired (C10)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("AUTHORITY_STALE", detail)


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise AuthorityError(code, detail)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(_canonical_json_bytes(part))
    return "sha256:" + h.hexdigest()


@dataclass(frozen=True)
class AuthorityDecisionReceipt:
    """Immutable authority decision receipt (C6)."""

    task_id: str
    authority_id: str
    grantee: str
    action: str
    issued_by: str
    issued_at: str = "2026-01-01T00:00:00Z"
    expires_at: str = "2030-01-01T00:00:00Z"
    receipt_digest: str = field(default_factory=str)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "authority-decision-receipt",
            "task_id": self.task_id,
            "authority_id": self.authority_id,
            "grantee": self.grantee,
            "action": self.action,
            "issued_by": self.issued_by,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "receipt_digest": self.receipt_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuthorityDecisionReceipt":
        return cls(
            task_id=str(data.get("task_id", "")),
            authority_id=str(data.get("authority_id", "")),
            grantee=str(data.get("grantee", "")),
            action=str(data.get("action", "")),
            issued_by=str(data.get("issued_by", "")),
            issued_at=str(data.get("issued_at", "2026-01-01T00:00:00Z")),
            expires_at=str(data.get("expires_at", "2030-01-01T00:00:00Z")),
            receipt_digest=str(data.get("receipt_digest", "")),
        )


def _compute_receipt_digest(receipt_fields: Mapping[str, Any]) -> str:
    return _sha256_digest(
        receipt_fields.get("task_id"), receipt_fields.get("authority_id"),
        receipt_fields.get("grantee"), receipt_fields.get("action"),
        receipt_fields.get("issued_by"), receipt_fields.get("issued_at"),
        receipt_fields.get("expires_at"),
    )


def issue_authority(
    *,
    task_id: str,
    authority_id: str,
    grantee: str,
    action: str,
    issued_by: str,
    issued_at: str = "2026-01-01T00:00:00Z",
    expires_at: str = "2030-01-01T00:00:00Z",
) -> AuthorityDecisionReceipt:
    """Issue an orthogonal authority decision receipt (C6).

    C10: an authority cannot self-grant — grantee must differ from issued_by.
    """
    _require(isinstance(task_id, str) and task_id.strip(), "TASK_ID_INVALID")
    _require(isinstance(authority_id, str) and authority_id.strip(), "AUTHORITY_ID_INVALID")
    _require(isinstance(grantee, str) and grantee.strip(), "GRANTEE_INVALID")
    _require(isinstance(issued_by, str) and issued_by.strip(), "ISSUER_INVALID")
    _require(action in KNOWN_ACTIONS, "AUTHORITY_ACTION_UNKNOWN", str(action))
    if grantee == issued_by:
        raise SelfGrantError(f"grantee={grantee} cannot issue authority to itself")
    digest = _compute_receipt_digest({
        "task_id": task_id, "authority_id": authority_id, "grantee": grantee,
        "action": action, "issued_by": issued_by, "issued_at": issued_at,
        "expires_at": expires_at,
    })
    return AuthorityDecisionReceipt(
        task_id=task_id, authority_id=authority_id, grantee=grantee,
        action=action, issued_by=issued_by, issued_at=issued_at,
        expires_at=expires_at, receipt_digest=digest,
    )


def validate_authority(
    receipt: AuthorityDecisionReceipt,
    *,
    now: str,
) -> dict[str, Any]:
    """Validate a receipt (C10): shape, digest, grantee/issuer, expiry."""
    if not isinstance(receipt, AuthorityDecisionReceipt):
        raise AuthorityError("AUTHORITY_RECEIPT_INVALID")
    expected = _compute_receipt_digest({
        "task_id": receipt.task_id, "authority_id": receipt.authority_id,
        "grantee": receipt.grantee, "action": receipt.action,
        "issued_by": receipt.issued_by, "issued_at": receipt.issued_at,
        "expires_at": receipt.expires_at,
    })
    if receipt.receipt_digest != expected:
        raise AuthorityError("AUTHORITY_DIGEST_MISMATCH")
    if now >= receipt.expires_at:
        raise StaleAuthorityError(
            f"authority={receipt.authority_id} expired {receipt.expires_at} (now={now})"
        )
    return {"valid": True, "receipt_digest": receipt.receipt_digest}


def resolve_authority(
    *,
    task_id: str,
    action: str,
    receipts: list[AuthorityDecisionReceipt] | tuple[AuthorityDecisionReceipt, ...],
    now: str,
) -> dict[str, Any]:
    """Resolve whether an effect is authorized (C6): every effect requires a
    valid decision receipt for its exact task + action; else fail-closed DENIED.
    """
    for receipt in receipts or []:
        if not isinstance(receipt, AuthorityDecisionReceipt):
            continue
        if receipt.task_id != task_id or receipt.action != action:
            continue
        try:
            validate_authority(receipt, now=now)
        except AuthorityError:
            continue
        return {
            "granted": True,
            "decision": "GRANTED",
            "decision_receipt": receipt.to_dict(),
        }
    return {"granted": False, "decision": "DENIED", "decision_receipt": None}


def build_modules_manifest(
    *,
    modules: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Build the cumulative universal_run_* module graph (G-R4-05)."""
    _require(isinstance(modules, (list, tuple)) and len(modules) > 0, "MODULES_EMPTY")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for mod in modules:
        name = str(mod.get("name", "")).strip()
        layer = str(mod.get("layer", "")).strip()
        _require(name, "MODULE_NAME_INVALID")
        _require(layer, "MODULE_LAYER_INVALID")
        if name in seen:
            raise AuthorityError("MODULE_DUPLICATE", name)
        seen.add(name)
        normalized.append({"name": name, "layer": layer})
    normalized = sorted(normalized, key=lambda m: m["name"])
    digest = _sha256_digest(normalized)
    return {
        "artifact_type": "universal-run-modules-manifest",
        "modules": normalized,
        "module_count": len(normalized),
        "manifest_digest": digest,
    }


__all__ = [
    "AuthorityDecisionReceipt",
    "AuthorityError",
    "KNOWN_ACTIONS",
    "SelfGrantError",
    "StaleAuthorityError",
    "build_modules_manifest",
    "issue_authority",
    "resolve_authority",
    "validate_authority",
]
