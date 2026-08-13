#!/usr/bin/env python3
"""Deterministic, read-only independent audit guardrail for autonomous G4 pre-prod.

The receipt is self-contained integrity evidence for a separately trusted standing
G4 evaluator. It never grants merge authority and this module has no side effects.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

AUDIT_PASS = "PASS"
AUDIT_BLOCK = "BLOCK"
_SHA256_PREFIX = "sha256:"

_BINDING_FIELDS = (
    "task_id", "repository", "pr_number", "target_branch", "base_sha", "head_sha",
    "dag_digest", "parent_authority_ref", "g0_ref", "g1_ref", "g2_ref", "g3_ref",
    "ci_ref", "managed_evidence_digest", "standing_g4_ref", "auditor_id",
    "auditor_context_id", "auditor_trust_ref", "implementer_id", "implementer_context_id",
    "blockers",
)


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _SHA256_PREFIX + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_sha(value: object) -> bool:
    text = str(value or "")
    return len(text) == 40 and all(c in "0123456789abcdef" for c in text)


def _valid_digest(value: object) -> bool:
    text = str(value or "")
    return len(text) == 71 and text.startswith(_SHA256_PREFIX) and all(c in "0123456789abcdef" for c in text[7:])


def _binding_from(value: Mapping[str, Any]) -> dict[str, Any]:
    return {field: value.get(field) for field in _BINDING_FIELDS}


def _receipt_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical fields covered by receipt_digest; excludes receipt_digest itself."""
    return {
        "artifact_type": value.get("artifact_type"),
        "schema_version": value.get("schema_version"),
        "audit_outcome": value.get("audit_outcome"),
        **_binding_from(value),
        "independent": value.get("independent"),
        "write_actions": list(value.get("write_actions", [])),
        "merge_authority": value.get("merge_authority"),
        "evidence_digest": value.get("evidence_digest"),
    }


def evaluate_g4_preprod_audit(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate exact-head delivery evidence without creating execution authority."""
    blockers: list[str] = []
    task_id = str(evidence.get("task_id", ""))
    repository = str(evidence.get("repository", ""))
    target_branch = str(evidence.get("target_branch", ""))
    base_sha = str(evidence.get("base_sha", ""))
    head_sha = str(evidence.get("head_sha", ""))
    g3_head_sha = str(evidence.get("g3_head_sha", ""))
    auditor_id = str(evidence.get("auditor_id", ""))
    implementer_id = str(evidence.get("implementer_id", ""))
    auditor_context_id = str(evidence.get("auditor_context_id", ""))
    implementer_context_id = str(evidence.get("implementer_context_id", ""))
    auditor_trust_ref = str(evidence.get("auditor_trust_ref", ""))

    if not task_id:
        blockers.append("AUDIT_TASK_ID_MISSING")
    if "/" not in repository:
        blockers.append("AUDIT_REPOSITORY_INVALID")
    if not isinstance(evidence.get("pr_number"), int) or int(evidence.get("pr_number", 0)) < 1:
        blockers.append("AUDIT_PR_NUMBER_INVALID")
    if target_branch != "pre-prod":
        blockers.append("AUDIT_PREPROD_TARGET_REQUIRED")
    if not _valid_sha(base_sha):
        blockers.append("AUDIT_BASE_SHA_INVALID")
    if not _valid_sha(head_sha):
        blockers.append("AUDIT_HEAD_SHA_INVALID")
    if g3_head_sha != head_sha:
        blockers.append("AUDIT_G3_HEAD_STALE")

    required_truths = {
        "dag_authority_valid": "AUDIT_DAG_AUTHORITY_INVALID",
        "parent_authority_valid": "AUDIT_PARENT_AUTHORITY_INVALID",
        "g0_ready": "AUDIT_G0_NOT_READY",
        "g1_pass": "AUDIT_G1_NOT_PASS",
        "derived_g2_valid": "AUDIT_G2_INVALID",
        "managed_evidence_current": "AUDIT_MANAGED_EVIDENCE_STALE",
        "exact_head_ci_success": "AUDIT_EXACT_HEAD_CI_NOT_GREEN",
        "required_checks_terminal_success": "AUDIT_REQUIRED_CHECKS_NOT_TERMINAL_SUCCESS",
        "g3_independent": "AUDIT_G3_NOT_INDEPENDENT",
        "scope_valid": "AUDIT_SCOPE_INVALID",
        "risk_valid": "AUDIT_RISK_INVALID",
        "actions_valid": "AUDIT_ACTIONS_INVALID",
        "standing_g4_applicable": "AUDIT_STANDING_G4_NOT_APPLICABLE",
    }
    for field, reason in required_truths.items():
        if evidence.get(field) is not True:
            blockers.append(reason)
    if str(evidence.get("g3_conclusion", "")).lower() != "pass":
        blockers.append("AUDIT_G3_NOT_PASS")

    if not auditor_id or not implementer_id:
        blockers.append("AUDIT_IDENTITY_MISSING")
    elif auditor_id == implementer_id:
        blockers.append("AUDIT_NOT_INDEPENDENT")
    if not auditor_context_id or not implementer_context_id:
        blockers.append("AUDIT_CONTEXT_IDENTITY_MISSING")
    elif auditor_context_id == implementer_context_id:
        blockers.append("AUDIT_CONTEXT_NOT_INDEPENDENT")
    if not auditor_trust_ref:
        blockers.append("AUDIT_AUDITOR_TRUST_REF_MISSING")
    if list(evidence.get("audit_write_actions", [])):
        blockers.append("AUDIT_WRITE_ACTION_FORBIDDEN")

    if not _valid_digest(evidence.get("dag_digest")):
        blockers.append("AUDIT_DAG_DIGEST_INVALID")
    if not _valid_digest(evidence.get("managed_evidence_digest")):
        blockers.append("AUDIT_MANAGED_EVIDENCE_DIGEST_INVALID")
    for field, reason in {
        "parent_authority_ref": "AUDIT_PARENT_AUTHORITY_REF_MISSING",
        "g0_ref": "AUDIT_G0_REF_MISSING",
        "g1_ref": "AUDIT_G1_REF_MISSING",
        "g2_ref": "AUDIT_G2_REF_MISSING",
        "g3_ref": "AUDIT_G3_REF_MISSING",
        "ci_ref": "AUDIT_CI_REF_MISSING",
        "standing_g4_ref": "AUDIT_STANDING_G4_REF_MISSING",
    }.items():
        if not str(evidence.get(field, "")):
            blockers.append(reason)

    blockers = sorted(set(blockers))
    binding = {
        "task_id": task_id,
        "repository": repository,
        "pr_number": evidence.get("pr_number"),
        "target_branch": target_branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "dag_digest": evidence.get("dag_digest"),
        "parent_authority_ref": evidence.get("parent_authority_ref"),
        "g0_ref": evidence.get("g0_ref"),
        "g1_ref": evidence.get("g1_ref"),
        "g2_ref": evidence.get("g2_ref"),
        "g3_ref": evidence.get("g3_ref"),
        "ci_ref": evidence.get("ci_ref"),
        "managed_evidence_digest": evidence.get("managed_evidence_digest"),
        "standing_g4_ref": evidence.get("standing_g4_ref"),
        "auditor_id": auditor_id,
        "auditor_context_id": auditor_context_id,
        "auditor_trust_ref": auditor_trust_ref,
        "implementer_id": implementer_id,
        "implementer_context_id": implementer_context_id,
        "blockers": blockers,
    }
    independent = (
        bool(auditor_id and implementer_id and auditor_id != implementer_id)
        and bool(auditor_context_id and implementer_context_id and auditor_context_id != implementer_context_id)
    )
    receipt = {
        "artifact_type": "autonomous-g4-preprod-independent-audit",
        "schema_version": "1.1",
        "audit_outcome": AUDIT_PASS if not blockers else AUDIT_BLOCK,
        **binding,
        "independent": independent,
        "write_actions": [],
        "merge_authority": False,
        "evidence_digest": canonical_digest(binding),
    }
    return {**receipt, "receipt_digest": canonical_digest(_receipt_payload(receipt))}


def validate_audit_receipt(receipt: Mapping[str, Any], *, expected_head_sha: str) -> dict[str, Any]:
    """Recompute all receipt integrity bindings and fail closed on stale/malformed evidence."""
    if receipt.get("artifact_type") != "autonomous-g4-preprod-independent-audit":
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_TYPE_INVALID"}
    if receipt.get("schema_version") != "1.1":
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_SCHEMA_INVALID"}
    if receipt.get("audit_outcome") != AUDIT_PASS or list(receipt.get("blockers", [])):
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_NOT_PASS"}
    if receipt.get("target_branch") != "pre-prod":
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_TARGET_INVALID"}
    if not _valid_sha(expected_head_sha) or receipt.get("head_sha") != expected_head_sha:
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_STALE_HEAD"}
    if not _valid_sha(receipt.get("base_sha")):
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_BASE_INVALID"}
    if receipt.get("independent") is not True:
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_NOT_INDEPENDENT"}
    if not str(receipt.get("auditor_trust_ref", "")):
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_TRUST_REF_MISSING"}
    if receipt.get("merge_authority") is not False or list(receipt.get("write_actions", [])):
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_AUTHORITY_VIOLATION"}
    if not isinstance(receipt.get("pr_number"), int) or int(receipt.get("pr_number", 0)) < 1:
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_PR_INVALID"}
    if not _valid_digest(receipt.get("dag_digest")) or not _valid_digest(receipt.get("managed_evidence_digest")):
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_EVIDENCE_BINDING_INVALID"}
    for field in ("parent_authority_ref", "g0_ref", "g1_ref", "g2_ref", "g3_ref", "ci_ref", "standing_g4_ref", "auditor_id", "auditor_context_id", "implementer_id", "implementer_context_id"):
        if not str(receipt.get(field, "")):
            return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_EVIDENCE_BINDING_INVALID"}

    binding = _binding_from(receipt)
    expected_evidence_digest = canonical_digest(binding)
    if receipt.get("evidence_digest") != expected_evidence_digest:
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_EVIDENCE_DIGEST_MISMATCH"}
    expected_receipt_digest = canonical_digest(_receipt_payload(receipt))
    if receipt.get("receipt_digest") != expected_receipt_digest:
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_DIGEST_MISMATCH"}
    return {
        "outcome": "PASS",
        "reason_code": "AUDIT_RECEIPT_VALID",
        "head_sha": expected_head_sha,
        "receipt_digest": expected_receipt_digest,
        "auditor_trust_ref": receipt.get("auditor_trust_ref"),
    }


__all__ = ["AUDIT_PASS", "AUDIT_BLOCK", "canonical_digest", "evaluate_g4_preprod_audit", "validate_audit_receipt"]
