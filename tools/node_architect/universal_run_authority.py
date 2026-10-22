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
    claims: Mapping[str, Any] = field(default_factory=dict)

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
            "claims": copy.deepcopy(dict(self.claims)),
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
            claims=copy.deepcopy(data.get("claims", {})) if isinstance(data.get("claims", {}), Mapping) else {},
        )


def _compute_receipt_digest(receipt_fields: Mapping[str, Any]) -> str:
    return _sha256_digest(
        receipt_fields.get("task_id"), receipt_fields.get("authority_id"),
        receipt_fields.get("grantee"), receipt_fields.get("action"),
        receipt_fields.get("issued_by"), receipt_fields.get("issued_at"),
        receipt_fields.get("expires_at"), receipt_fields.get("claims", {}),
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
    claims: Mapping[str, Any] | None = None,
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
        "claims": dict(claims or {}),
    })
    return AuthorityDecisionReceipt(
        task_id=task_id, authority_id=authority_id, grantee=grantee,
        action=action, issued_by=issued_by, issued_at=issued_at,
        expires_at=expires_at, receipt_digest=digest,
        claims=copy.deepcopy(dict(claims or {})),
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
        "claims": dict(receipt.claims),
        "claims": dict(receipt.claims),
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
    derived_anchor_unavailable = False
    for receipt in receipts or []:
        if isinstance(receipt, Mapping) and receipt.get("schema") == "derived-child-authority/v1":
            if receipt.get("task_id") != task_id or action not in receipt.get("authorized_actions", ()):
                continue
            if receipt.get("g4_g5_g6_authority_granted") is not False:
                continue
            if now >= str(receipt.get("expires_at", "")):
                continue
            # Derived receipt hashes are content-integrity checks, not proof of
            # parent provenance. This resolver has no independently verified
            # parent authority source/verifier, so the derived claim must never
            # grant by matching a caller-computable self-hash.
            derived_anchor_unavailable = True
            continue
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
    if derived_anchor_unavailable:
        return {
            "granted": False,
            "decision": "DENIED",
            "reason_code": "AUTHORITY_TRUST_ANCHOR_UNAVAILABLE",
            "decision_receipt": None,
        }
    return {"granted": False, "decision": "DENIED", "decision_receipt": None}


def derive_child_authority(
    parent_grant: AuthorityDecisionReceipt,
    child_subject: Mapping[str, Any],
    *,
    root: Any,
    now: str,
) -> dict[str, Any]:
    """Deterministically derive a strict child receipt from a validated parent grant.

    This is a pure evaluator: replaying identical inputs returns the identical
    receipt; callers remain responsible for durable single-consumption tracking.
    """
    from tools.node_architect.derive_task_authority import evaluate_parent_child_authority

    validate_authority(parent_grant, now=now)
    if not isinstance(child_subject, Mapping):
        raise AuthorityError("AUTHORITY_CHILD_SUBJECT_INVALID")
    claims = dict(parent_grant.claims)
    if not claims:
        raise AuthorityError("AUTHORITY_PARENT_GRANT_INVALID")
    if claims.get("revoked") is not False:
        raise AuthorityError("AUTHORITY_REVOKED")
    if claims.get("expires_at") != parent_grant.expires_at:
        raise AuthorityError("AUTHORITY_PARENT_GRANT_INVALID")
    if claims.get("issuer") == child_subject.get("child_run_id") or claims.get("issued_by") == child_subject.get("child_run_id"):
        raise SelfGrantError("issuer is the child grantee")
    if claims.get("issuer", claims.get("issued_by")) != parent_grant.issued_by:
        raise AuthorityError("AUTHORITY_PROVENANCE_INVALID")
    if claims.get("actor") != parent_grant.grantee:
        raise AuthorityError("AUTHORITY_ACTOR_MISMATCH")
    evaluation = evaluate_parent_child_authority(claims, child_subject)
    if evaluation["decision"] != "ALLOW":
        code = evaluation["reason_code"]
        if code == "AUTHORITY_SELF_GRANT_FORBIDDEN":
            raise SelfGrantError(code)
        if code == "AUTHORITY_STALE":
            raise StaleAuthorityError(code)
        raise AuthorityError(code)
    fields = {
        "schema": "derived-child-authority/v1",
        "task_id": parent_grant.task_id,
        "authority_id": f"derived:{parent_grant.authority_id}:{child_subject['child_run_id']}",
        "parent_grant_digest": parent_grant.receipt_digest,
        "parent_run_id": claims["run_id"],
        "child_run_id": child_subject["child_run_id"],
        "grantee": parent_grant.grantee,
        "actor": child_subject["actor"],
        "repository": child_subject["repository"],
        "branch": child_subject["branch"],
        "head_sha": child_subject["head_sha"],
        "target": child_subject["target"],
        "scope": sorted(child_subject["scope"]),
        "scope_hash": _sha256_digest(sorted(child_subject["scope"])),
        "risk_ceiling": child_subject["risk_ceiling"],
        "authorized_actions": [child_subject["action"]],
        "expires_at": parent_grant.expires_at,
        "audit_trail": [{"event": "derived", "parent_grant_digest": parent_grant.receipt_digest}],
        "g4_g5_g6_authority_granted": False,
        "decision": "ALLOW",
    }
    fields["decision_digest"] = _sha256_digest(fields)
    fields["receipt_digest"] = _sha256_digest(fields)
    return fields


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
    "derive_child_authority",
    "issue_authority",
    "resolve_authority",
    "validate_authority",
]
