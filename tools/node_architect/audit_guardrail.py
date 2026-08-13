#!/usr/bin/env python3
"""Deterministic, read-only independent audit guardrail for autonomous G4 pre-prod.

The audit result is evidence for the standing G4 evaluator. It never grants merge
authority and never performs repository/tracker/Slack writes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

AUDIT_PASS = "PASS"
AUDIT_BLOCK = "BLOCK"


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_sha(value: object) -> bool:
    text = str(value or "")
    return len(text) == 40 and all(c in "0123456789abcdef" for c in text)


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

    if not task_id:
        blockers.append("AUDIT_TASK_ID_MISSING")
    if "/" not in repository:
        blockers.append("AUDIT_REPOSITORY_INVALID")
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
    if auditor_context_id and implementer_context_id and auditor_context_id == implementer_context_id:
        blockers.append("AUDIT_CONTEXT_NOT_INDEPENDENT")
    if list(evidence.get("audit_write_actions", [])):
        blockers.append("AUDIT_WRITE_ACTION_FORBIDDEN")

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
        "blockers": sorted(set(blockers)),
    }
    audit_outcome = AUDIT_PASS if not blockers else AUDIT_BLOCK
    receipt_payload = {**binding, "audit_outcome": audit_outcome, "merge_authority": False}
    return {
        "artifact_type": "autonomous-g4-preprod-independent-audit",
        "schema_version": "1.0",
        "audit_outcome": audit_outcome,
        "blockers": sorted(set(blockers)),
        "task_id": task_id,
        "repository": repository,
        "pr_number": evidence.get("pr_number"),
        "target_branch": target_branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "auditor_id": auditor_id,
        "auditor_context_id": auditor_context_id,
        "independent": "AUDIT_NOT_INDEPENDENT" not in blockers and "AUDIT_CONTEXT_NOT_INDEPENDENT" not in blockers,
        "write_actions": [],
        "merge_authority": False,
        "evidence_digest": canonical_digest(binding),
        "receipt_digest": canonical_digest(receipt_payload),
    }


def validate_audit_receipt(receipt: Mapping[str, Any], *, expected_head_sha: str) -> dict[str, Any]:
    """Fail closed when a receipt is stale, malformed, write-capable, or grants merge authority."""
    if receipt.get("artifact_type") != "autonomous-g4-preprod-independent-audit":
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_TYPE_INVALID"}
    if receipt.get("audit_outcome") != AUDIT_PASS:
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_NOT_PASS"}
    if receipt.get("head_sha") != expected_head_sha:
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_STALE_HEAD"}
    if receipt.get("independent") is not True:
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_NOT_INDEPENDENT"}
    if receipt.get("merge_authority") is not False or list(receipt.get("write_actions", [])):
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_AUTHORITY_VIOLATION"}
    digest = str(receipt.get("receipt_digest", ""))
    if not digest.startswith("sha256:") or len(digest) != 71:
        return {"outcome": "BLOCK", "reason_code": "AUDIT_RECEIPT_DIGEST_INVALID"}
    return {"outcome": "PASS", "reason_code": "AUDIT_RECEIPT_VALID", "head_sha": expected_head_sha, "receipt_digest": digest}


__all__ = ["AUDIT_PASS", "AUDIT_BLOCK", "canonical_digest", "evaluate_g4_preprod_audit", "validate_audit_receipt"]
