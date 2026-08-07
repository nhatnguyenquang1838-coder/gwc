#!/usr/bin/env python3
"""Derive deterministic task-scoped G2 and standing G4 decisions from an approved run manifest.

Pure functions only: this module does not call GitHub/Jira, mutate branches, or
perform merge/deploy operations. Child G2 and standing G4 ALLOW outputs are
contract decisions and must be projected/attested by trusted repository CI before
any live gate can consume them.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from .validate_autonomous_preprod_policy import (
    RISK_ORDER,
    canonical_digest,
    parse_utc,
    validate_manifest,
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _decision_digest(value: Mapping[str, Any]) -> str:
    return canonical_digest(value, omit=("decision_digest",))


def _deny(gate: str, code: str, *, run_id: str | None = None, task_id: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-child-authority-decision",
        "decision": "DENY",
        "gate": gate,
        "reason_code": code,
        "run_id": run_id,
        "task_id": task_id,
        "g4_g5_g6_authority_granted": False,
    }
    value["decision_digest"] = _decision_digest(value)
    return value


def _task(manifest: Mapping[str, Any], task_id: str) -> Mapping[str, Any] | None:
    return next((item for item in manifest.get("allowed_tasks", []) if item.get("task_id") == task_id), None)


def _parent_provenance(manifest: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    receipt = manifest["authority_receipt"]
    return {
        "parent_approval_id": receipt["approval_id"],
        "parent_scope_hash_prefix": receipt["scope_hash_prefix"],
        "parent_authority_digest": validation["authority_receipt_digest"],
    }


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(item, str) or not item for item in value):
        return None
    if len(value) != len(set(value)):
        return None
    return list(value)


def derive_g2_authority(
    policy: Mapping[str, Any],
    manifest: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    validation = validate_manifest(policy, manifest, root=root, now=now)
    run_id = str(manifest.get("run_id", "")) or None
    if not isinstance(request, Mapping):
        return _deny("G2_EXECUTION", "AUTONOMOUS_SCOPE_DRIFT", run_id=run_id)
    task_id = str(request.get("task_id", "")) or None
    if validation["outcome"] != "PASS":
        return _deny("G2_EXECUTION", validation["reason_codes"][0], run_id=run_id, task_id=task_id)
    if not task_id:
        return _deny("G2_EXECUTION", "AUTONOMOUS_RUN_MANIFEST_INVALID", run_id=run_id)
    task = _task(manifest, task_id)
    if task is None:
        return _deny("G2_EXECUTION", "AUTONOMOUS_TASK_NOT_ALLOWLISTED", run_id=run_id, task_id=task_id)

    risk = str(request.get("risk_class", ""))
    approved_risk = str(task.get("risk_class", ""))
    if risk not in RISK_ORDER or approved_risk not in RISK_ORDER:
        return _deny("G2_EXECUTION", "AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING", run_id=run_id, task_id=task_id)
    if risk != approved_risk:
        return _deny("G2_EXECUTION", "AUTONOMOUS_SCOPE_DRIFT", run_id=run_id, task_id=task_id)
    if RISK_ORDER[risk] > RISK_ORDER[str(policy["max_child_risk"])]:
        return _deny("G2_EXECUTION", "AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING", run_id=run_id, task_id=task_id)
    if request.get("observed_base_sha") != manifest.get("approved_base_sha"):
        return _deny("G2_EXECUTION", "AUTONOMOUS_BASE_SHA_MISMATCH", run_id=run_id, task_id=task_id)
    if request.get("working_branch") != task.get("working_branch"):
        return _deny("G2_EXECUTION", "AUTONOMOUS_SCOPE_DRIFT", run_id=run_id, task_id=task_id)

    requested_paths = _string_list(request.get("requested_paths"))
    requested_actions = _string_list(request.get("requested_actions"))
    if requested_paths is None:
        return _deny("G2_EXECUTION", "AUTONOMOUS_SCOPE_DRIFT", run_id=run_id, task_id=task_id)
    if requested_actions is None:
        return _deny("G2_EXECUTION", "AUTONOMOUS_ACTION_FORBIDDEN", run_id=run_id, task_id=task_id)
    if not set(requested_paths).issubset(set(task.get("authorized_paths", []))):
        return _deny("G2_EXECUTION", "AUTONOMOUS_SCOPE_DRIFT", run_id=run_id, task_id=task_id)
    if not set(requested_actions).issubset(set(task.get("authorized_g2_actions", []))):
        return _deny("G2_EXECUTION", "AUTONOMOUS_ACTION_FORBIDDEN", run_id=run_id, task_id=task_id)

    child_scope = {
        "task_id": task_id,
        "risk_class": risk,
        "working_branch": request["working_branch"],
        "authorized_paths": requested_paths,
        "authorized_actions": requested_actions,
        "base_sha": manifest["approved_base_sha"],
    }
    value: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-child-g2-authority",
        "decision": "ALLOW",
        "gate": "G2_EXECUTION",
        "reason_code": "AUTONOMOUS_CHILD_G2_AUTHORIZED",
        "trust_state": "requires_trusted_repo_ci_projection",
        "policy_id": policy["policy_id"],
        "policy_revision": policy["policy_revision"],
        "policy_digest": validation["policy_digest"],
        "manifest_digest": validation["manifest_digest"],
        **_parent_provenance(manifest, validation),
        "run_id": manifest["run_id"],
        "task_id": task_id,
        "repository": manifest["repository"],
        "base_ref": manifest["approved_base_ref"],
        "base_sha": manifest["approved_base_sha"],
        "working_branch": request["working_branch"],
        "risk_class": risk,
        "authorized_paths": requested_paths,
        "authorized_actions": requested_actions,
        "parent_task_scope_hash": task["scope_hash"],
        "child_scope_hash": canonical_digest(child_scope),
        "expires_at": manifest["expires_at"],
        "g4_g5_g6_authority_granted": False,
    }
    value["decision_digest"] = _decision_digest(value)
    return value


def derive_g4_receipt(
    policy: Mapping[str, Any],
    manifest: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    validation = validate_manifest(policy, manifest, root=root, now=now)
    run_id = str(manifest.get("run_id", ""))
    if not isinstance(context, Mapping):
        return _deny("G4_MERGE", "AUTONOMOUS_STANDING_G4_RECEIPT_INVALID", run_id=run_id)
    task_id = str(context.get("task_id", ""))
    if validation["outcome"] != "PASS":
        return _deny("G4_MERGE", validation["reason_codes"][0], run_id=run_id, task_id=task_id or None)
    task = _task(manifest, task_id)
    if task is None:
        return _deny("G4_MERGE", "AUTONOMOUS_TASK_NOT_ALLOWLISTED", run_id=run_id, task_id=task_id or None)
    if context.get("repository") != manifest.get("repository"):
        return _deny("G4_MERGE", "AUTONOMOUS_SCOPE_DRIFT", run_id=run_id, task_id=task_id)
    if context.get("target_branch") == "main":
        return _deny("G4_MERGE", "AUTONOMOUS_MAIN_TARGET_FORBIDDEN", run_id=run_id, task_id=task_id)
    if context.get("target_branch") != "pre-prod" or context.get("target_branch") != manifest.get("target_branch"):
        return _deny("G4_MERGE", "AUTONOMOUS_PREPROD_TARGET_REQUIRED", run_id=run_id, task_id=task_id)
    if context.get("approved_base_ref") != manifest.get("approved_base_ref"):
        return _deny("G4_MERGE", "AUTONOMOUS_SCOPE_DRIFT", run_id=run_id, task_id=task_id)
    if context.get("approved_base_sha") != manifest.get("approved_base_sha"):
        return _deny("G4_MERGE", "AUTONOMOUS_BASE_SHA_MISMATCH", run_id=run_id, task_id=task_id)
    if context.get("authorized_action") != "merge_approved_pr":
        return _deny("G4_MERGE", "AUTONOMOUS_ACTION_FORBIDDEN", run_id=run_id, task_id=task_id)
    if context.get("task_scope_hash") != task.get("scope_hash"):
        return _deny("G4_MERGE", "AUTONOMOUS_SCOPE_DRIFT", run_id=run_id, task_id=task_id)
    head = str(context.get("approved_head_sha", ""))
    if not SHA_RE.fullmatch(head):
        return _deny("G4_MERGE", "AUTONOMOUS_HEAD_DRIFT", run_id=run_id, task_id=task_id)
    for field, code in (
        ("pr_body_digest", "AUTONOMOUS_PR_BODY_DRIFT"),
        ("managed_block_digest", "AUTONOMOUS_PR_BODY_DRIFT"),
        ("run_graph_digest", "AUTONOMOUS_GRAPH_DRIFT"),
        ("gate_story_digest", "AUTONOMOUS_STORY_DRIFT"),
        ("evidence_digest", "AUTONOMOUS_EVIDENCE_DRIFT"),
    ):
        if not DIGEST_RE.fullmatch(str(context.get(field, ""))):
            return _deny("G4_MERGE", code, run_id=run_id, task_id=task_id)
    pr_number = context.get("pr_number")
    if not isinstance(pr_number, int) or pr_number < 1:
        return _deny("G4_MERGE", "AUTONOMOUS_STANDING_G4_RECEIPT_INVALID", run_id=run_id, task_id=task_id)

    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-g4-receipt",
        "decision": "ALLOW",
        "source": "autonomous_preprod_standing_policy",
        "trust_state": "requires_trusted_repo_ci_projection",
        "policy_id": policy["policy_id"],
        "policy_revision": policy["policy_revision"],
        "policy_digest": validation["policy_digest"],
        "manifest_digest": validation["manifest_digest"],
        **_parent_provenance(manifest, validation),
        "run_id": manifest["run_id"],
        "task_id": task_id,
        "repository": manifest["repository"],
        "approved_base_ref": manifest["approved_base_ref"],
        "approved_base_sha": manifest["approved_base_sha"],
        "target_branch": "pre-prod",
        "pr_number": pr_number,
        "approved_head_sha": head,
        "task_scope_hash": task["scope_hash"],
        "pr_body_digest": context["pr_body_digest"],
        "managed_block_digest": context["managed_block_digest"],
        "run_graph_digest": context["run_graph_digest"],
        "gate_story_digest": context["gate_story_digest"],
        "evidence_digest": context["evidence_digest"],
        "authorized_action": "merge_approved_pr",
        "expires_at": manifest["expires_at"],
    }
    receipt["decision_digest"] = _decision_digest(receipt)
    schema = json.loads((root / "schemas/autonomous-preprod-g4-receipt.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt))
    if errors:
        return _deny("G4_MERGE", "AUTONOMOUS_STANDING_G4_RECEIPT_INVALID", run_id=run_id, task_id=task_id)
    return receipt


def validate_g4_receipt(
    receipt: Mapping[str, Any],
    policy: Mapping[str, Any],
    manifest: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    validation = validate_manifest(policy, manifest, root=root, now=now)
    reasons = list(validation["reason_codes"])
    details = list(validation["details"])
    if not isinstance(receipt, Mapping) or not isinstance(current, Mapping):
        reasons.append("AUTONOMOUS_STANDING_G4_RECEIPT_INVALID")
        details.append("receipt and current context must be objects")
        return {"outcome": "BLOCKED", "reason_codes": list(dict.fromkeys(reasons)), "details": details}
    schema = json.loads((root / "schemas/autonomous-preprod-g4-receipt.schema.json").read_text(encoding="utf-8"))
    schema_errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt))
    if schema_errors:
        reasons.append("AUTONOMOUS_STANDING_G4_RECEIPT_INVALID")
        details.extend(error.message for error in schema_errors)
    else:
        if receipt.get("decision_digest") != _decision_digest(receipt):
            reasons.append("AUTONOMOUS_STANDING_G4_RECEIPT_INVALID")
            details.append("decision_digest mismatch")
        expected_identity = {
            "policy_id": policy.get("policy_id"),
            "policy_revision": policy.get("policy_revision"),
            "policy_digest": validation.get("policy_digest"),
            "manifest_digest": validation.get("manifest_digest"),
            "parent_approval_id": manifest.get("authority_receipt", {}).get("approval_id"),
            "parent_scope_hash_prefix": manifest.get("authority_receipt", {}).get("scope_hash_prefix"),
            "parent_authority_digest": validation.get("authority_receipt_digest"),
            "run_id": manifest.get("run_id"),
            "repository": manifest.get("repository"),
            "approved_base_ref": manifest.get("approved_base_ref"),
            "approved_base_sha": manifest.get("approved_base_sha"),
            "target_branch": "pre-prod",
            "trust_state": "requires_trusted_repo_ci_projection",
            "authorized_action": "merge_approved_pr",
            "expires_at": manifest.get("expires_at"),
        }
        for field, expected in expected_identity.items():
            if receipt.get(field) != expected:
                reasons.append("AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED" if field.startswith("parent_") else "AUTONOMOUS_SCOPE_DRIFT")
                details.append(f"receipt {field} mismatch")
        task = _task(manifest, str(receipt.get("task_id", "")))
        if task is None:
            reasons.append("AUTONOMOUS_TASK_NOT_ALLOWLISTED")
        elif receipt.get("task_scope_hash") != task.get("scope_hash"):
            reasons.append("AUTONOMOUS_SCOPE_DRIFT")

        if current.get("target_branch") == "main":
            reasons.append("AUTONOMOUS_MAIN_TARGET_FORBIDDEN")
            details.append("current target branch must never be main")
        elif current.get("target_branch") != "pre-prod":
            reasons.append("AUTONOMOUS_PREPROD_TARGET_REQUIRED")
            details.append("current target branch must be pre-prod")
        if current.get("repository") != manifest.get("repository"):
            reasons.append("AUTONOMOUS_SCOPE_DRIFT")
            details.append("current repository does not match manifest")
        if current.get("approved_base_ref") != manifest.get("approved_base_ref"):
            reasons.append("AUTONOMOUS_SCOPE_DRIFT")
            details.append("current approved_base_ref does not match manifest")
        if current.get("approved_base_sha") != manifest.get("approved_base_sha"):
            reasons.append("AUTONOMOUS_BASE_SHA_MISMATCH")
            details.append("current approved_base_sha does not match manifest")
        if current.get("authorized_action") != "merge_approved_pr":
            reasons.append("AUTONOMOUS_ACTION_FORBIDDEN")
            details.append("current authorized_action must be merge_approved_pr")

        for field, code in (
            ("repository", "AUTONOMOUS_SCOPE_DRIFT"),
            ("approved_base_ref", "AUTONOMOUS_SCOPE_DRIFT"),
            ("approved_base_sha", "AUTONOMOUS_BASE_SHA_MISMATCH"),
            ("target_branch", "AUTONOMOUS_PREPROD_TARGET_REQUIRED"),
            ("authorized_action", "AUTONOMOUS_ACTION_FORBIDDEN"),
            ("approved_head_sha", "AUTONOMOUS_HEAD_DRIFT"),
            ("pr_body_digest", "AUTONOMOUS_PR_BODY_DRIFT"),
            ("managed_block_digest", "AUTONOMOUS_PR_BODY_DRIFT"),
            ("run_graph_digest", "AUTONOMOUS_GRAPH_DRIFT"),
            ("gate_story_digest", "AUTONOMOUS_STORY_DRIFT"),
            ("evidence_digest", "AUTONOMOUS_EVIDENCE_DRIFT"),
            ("pr_number", "AUTONOMOUS_SCOPE_DRIFT"),
            ("task_scope_hash", "AUTONOMOUS_SCOPE_DRIFT"),
            ("task_id", "AUTONOMOUS_SCOPE_DRIFT"),
        ):
            if receipt.get(field) != current.get(field):
                reasons.append(code)
                details.append(f"current {field} does not match receipt")
        try:
            if parse_utc(str(receipt["expires_at"]), "receipt.expires_at") <= now:
                reasons.append("AUTONOMOUS_RUN_MANIFEST_EXPIRED")
        except (KeyError, ValueError) as exc:
            reasons.append("AUTONOMOUS_STANDING_G4_RECEIPT_INVALID")
            details.append(str(exc))
    reasons = list(dict.fromkeys(reasons))
    return {"outcome": "PASS" if not reasons else "BLOCKED", "reason_codes": reasons, "details": details}


__all__ = ["derive_g2_authority", "derive_g4_receipt", "validate_g4_receipt"]