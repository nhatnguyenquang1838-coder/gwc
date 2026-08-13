#!/usr/bin/env python3
"""Deterministic closed-loop decisions for autonomous delivery to pre-prod.

Route invariant: AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN.
This module is deliberately side-effect free. Adapters perform tracker/GitHub/Slack/CI
writes only after consuming a decision bound to the same immutable inputs.

The autonomous agent boots as TaskController. Claimed work is delegated through the
existing Slack Controller–Executor MVP. Before a child can reach the standing G4 merge
evaluator, an independent exact-head G4 pre-prod audit receipt is mandatory.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

TERMINAL_COMPLETE = {"COMPLETED", "PREPROD_MERGED", "G5_VERIFIED"}
EXECUTABLE_STATUSES = {"TO_DO", "READY", "RETRYABLE"}
MAX_AUTONOMOUS_RISK = 2
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
AUTONOMOUS_ROUTE_ID = "AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN"


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _overlaps(path: str, protected: str) -> bool:
    left, right = path.rstrip("/"), protected.rstrip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def resolve_ready_nodes(tasks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return deterministic READY nodes from canonical DAG task snapshots."""
    by_id = {str(t.get("task_id")): t for t in tasks if t.get("task_id")}
    ready: list[str] = []
    blocked: dict[str, list[str]] = {}
    for task_id in sorted(by_id):
        task = by_id[task_id]
        if str(task.get("status", "")).upper() not in EXECUTABLE_STATUSES:
            continue
        deps = [str(x) for x in task.get("dependencies", [])]
        missing = [dep for dep in deps if dep not in by_id]
        incomplete = [dep for dep in deps if dep in by_id and str(by_id[dep].get("status", "")).upper() not in TERMINAL_COMPLETE]
        if missing or incomplete:
            blocked[task_id] = sorted(missing + incomplete)
        else:
            ready.append(task_id)
    return {
        "outcome": "PASS",
        "ready_task_ids": ready,
        "blocked_dependencies": blocked,
        "dag_digest": canonical_digest(list(tasks)),
    }


def resolve_authorized_ready_nodes(*, dag: Mapping[str, Any], manifest: Mapping[str, Any] | None,
                                   authority_valid: bool) -> dict[str, Any]:
    """Gate DAG-ready tasks through trusted parent authority before any claim intent."""
    ready = [str(x) for x in dag.get("ready_task_ids", [])]
    if not ready:
        return {"outcome": "IDLE", "reason_code": "AUTONOMOUS_NO_READY_TASK"}
    if not authority_valid or not isinstance(manifest, Mapping):
        return {
            "outcome": "PENDING",
            "reason_code": "AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED",
            "state": "READY_FOR_AUTHORITY",
            "ready_task_ids": ready,
        }
    allowed_tasks = manifest.get("allowed_tasks", [])
    allowlisted = {
        str(item.get("task_id"))
        for item in allowed_tasks
        if isinstance(item, Mapping) and item.get("task_id")
    }
    authorized = [task_id for task_id in ready if task_id in allowlisted]
    if not authorized:
        return {
            "outcome": "BLOCKED",
            "reason_code": "AUTONOMOUS_TASK_NOT_ALLOWLISTED",
            "state": "BLOCKED",
            "ready_task_ids": ready,
        }
    return {
        "outcome": "PASS",
        "reason_code": "AUTONOMOUS_AUTHORIZED_READY",
        "state": "AUTHORIZED_READY",
        "ready_task_ids": authorized,
    }


def claim_task(*, task_id: str, ready_task_ids: Sequence[str], claimant: str, lease_id: str,
               existing_claim: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Produce replay-safe atomic-claim intent; adapter must CAS this against trackers."""
    if task_id not in set(ready_task_ids):
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_TASK_NOT_READY", "task_id": task_id}
    desired = {"task_id": task_id, "claimant": claimant, "lease_id": lease_id}
    claim_key = canonical_digest(desired)
    if existing_claim:
        existing_key = existing_claim.get("claim_key")
        if existing_key == claim_key:
            return {"outcome": "ALLOW", "reason_code": "AUTONOMOUS_CLAIM_REPLAY", "claim_key": claim_key, **desired}
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_CLAIM_CONFLICT", "task_id": task_id}
    return {"outcome": "ALLOW", "reason_code": "AUTONOMOUS_CLAIM_READY", "claim_key": claim_key, **desired}


def validate_task_scope(*, task: Mapping[str, Any], manifest_task: Mapping[str, Any],
                        requested_paths: Sequence[str], immutable_authority_paths: Sequence[str]) -> dict[str, Any]:
    """Allow implementation when it cannot rewrite this run's active authority plane."""
    if task.get("task_id") != manifest_task.get("task_id"):
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_TASK_NOT_ALLOWLISTED"}
    risk = str(task.get("risk", manifest_task.get("risk", manifest_task.get("risk_class", "R3"))))
    if RISK_ORDER.get(risk, 99) > MAX_AUTONOMOUS_RISK:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING"}
    allowed = set(str(p) for p in manifest_task.get("allowed_paths", manifest_task.get("authorized_paths", [])))
    requested = [str(p) for p in requested_paths]
    if not requested or any(p not in allowed for p in requested):
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_SCOPE_DRIFT"}
    violations = sorted({p for p in requested for protected in immutable_authority_paths if _overlaps(p, str(protected))})
    if violations:
        return {
            "outcome": "BLOCKED",
            "reason_code": "AUTONOMOUS_ACTIVE_AUTHORITY_SELF_MODIFICATION_FORBIDDEN",
            "violations": violations,
        }
    return {
        "outcome": "ALLOW",
        "reason_code": "AUTONOMOUS_TASK_SCOPE_ALLOWED",
        "task_id": task.get("task_id"),
        "requested_paths": requested,
        "scope_digest": canonical_digest({"task": manifest_task, "requested_paths": requested}),
    }


def child_delivery_decision(*, task_id: str, target_branch: str, head_sha: str,
                            ci_conclusion: str, review_conclusion: str,
                            standing_g4_valid: bool,
                            managed_evidence_current: bool = False,
                            required_checks_terminal_success: bool = False,
                            audit_conclusion: str = "",
                            audit_head_sha: str = "",
                            audit_independent: bool = False,
                            audit_trust_valid: bool = False,
                            audit_receipt_valid: bool = False,
                            audit_receipt_digest: str = "") -> dict[str, Any]:
    """Decide whether normalized, trusted exact-head evidence permits pre-prod merge.

    The caller must obtain ``audit_receipt_valid`` from ``validate_audit_receipt``
    and ``audit_trust_valid`` from the trusted auditor-dispatch/readback adapter.
    Audit evidence never grants merge authority; standing G4 remains the evaluator.
    """
    if target_branch == "main":
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_CHILD_MAIN_TARGET_FORBIDDEN"}
    if target_branch != "pre-prod":
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_PREPROD_TARGET_REQUIRED"}
    if len(head_sha) != 40 or any(c not in "0123456789abcdef" for c in head_sha):
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_HEAD_INVALID"}
    if ci_conclusion != "success":
        return {"outcome": "PENDING" if ci_conclusion in {"queued", "in_progress", "pending"} else "BLOCKED",
                "reason_code": "AUTONOMOUS_EXACT_HEAD_CI_NOT_GREEN"}
    if not required_checks_terminal_success:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_REQUIRED_CHECKS_NOT_TERMINAL_SUCCESS"}
    if not managed_evidence_current:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_PR_MANAGED_EVIDENCE_NOT_CURRENT"}
    if review_conclusion != "pass":
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_G3_REVIEW_NOT_PASS"}
    if str(audit_conclusion).lower() != "pass":
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_G4_PREPROD_AUDIT_NOT_PASS"}
    if audit_head_sha != head_sha:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_G4_PREPROD_AUDIT_STALE"}
    if not audit_independent:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_G4_PREPROD_AUDIT_NOT_INDEPENDENT"}
    if not audit_trust_valid:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_G4_PREPROD_AUDITOR_TRUST_INVALID"}
    if not audit_receipt_valid:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_G4_PREPROD_AUDIT_RECEIPT_INVALID"}
    if not audit_receipt_digest.startswith("sha256:") or len(audit_receipt_digest) != 71:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_G4_PREPROD_AUDIT_DIGEST_INVALID"}
    if not standing_g4_valid:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_STANDING_G4_AUTHORITY_INVALID"}
    evidence = {
        "task_id": task_id,
        "target_branch": target_branch,
        "head_sha": head_sha,
        "route_id": AUTONOMOUS_ROUTE_ID,
        "required_checks_terminal_success": True,
        "managed_evidence_current": True,
        "g3_review": "pass",
        "independent_g4_audit": "pass",
        "audit_trust_valid": True,
        "audit_receipt_digest": audit_receipt_digest,
        "standing_g4_valid": True,
    }
    return {
        "outcome": "ALLOW",
        "reason_code": "AUTONOMOUS_PREPROD_MERGE_ALLOWED",
        "route_id": AUTONOMOUS_ROUTE_ID,
        "merge_allowed": True,
        "main_merge_allowed": False,
        "audit_required": True,
        "audit_merge_authority": False,
        "audit_receipt_digest": audit_receipt_digest,
        "evidence_digest": canonical_digest(evidence),
    }


def next_runtime_action(*, dag: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    claims = claims or {}
    for task_id in dag.get("ready_task_ids", []):
        if task_id not in claims:
            return {"outcome": "READY", "task_id": task_id, "action": "CLAIM_AND_EXECUTE"}
    return {"outcome": "IDLE", "reason_code": "AUTONOMOUS_NO_UNCLAIMED_READY_TASK"}


def _validate_runtime_audit_binding(observation: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the independently produced receipt to the current runtime observation."""
    expected = {
        "task_id": str(observation.get("task_id", "")),
        "repository": str(observation.get("repository", "")),
        "pr_number": observation.get("pr_number"),
        "target_branch": str(observation.get("target_branch", "")),
        "base_sha": str(observation.get("base_sha", "")),
        "head_sha": str(observation.get("head_sha", "")),
    }
    for field, expected_value in expected.items():
        if not expected_value or receipt.get(field) != expected_value:
            return {"outcome": "BLOCK", "reason_code": "AUTONOMOUS_G4_PREPROD_AUDIT_BINDING_MISMATCH", "field": field}
    from .audit_guardrail import validate_audit_receipt
    return validate_audit_receipt(receipt, expected_head_sha=expected["head_sha"])


def drive_closed_loop(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Map one observed autonomous state to exactly one next side-effect intent."""
    phase = str(observation.get("phase", "DISCOVER")).upper()
    if phase == "DISCOVER":
        dag = resolve_ready_nodes(observation.get("tasks", []))
        authority = resolve_authorized_ready_nodes(
            dag=dag,
            manifest=observation.get("manifest"),
            authority_valid=bool(observation.get("authority_valid")),
        )
        if authority.get("state") == "READY_FOR_AUTHORITY":
            return {**authority, "adapter_action": "RESOLVE_RUN_AUTHORITY", "dag": dag}
        if authority.get("outcome") != "PASS":
            return {**authority, "adapter_action": None, "dag": dag}
        authorized_dag = {**dag, "ready_task_ids": authority["ready_task_ids"]}
        nxt = next_runtime_action(dag=authorized_dag, claims=observation.get("claims", {}))
        if nxt.get("outcome") != "READY":
            return {**nxt, "adapter_action": None, "dag": dag, "authority": authority}
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_AUTHORIZED_READY_TASK_SELECTED",
            "state": "AUTHORIZED_READY",
            "task_id": nxt["task_id"],
            "controller_role": "TaskController",
            "adapter_action": "JIRA_GITHUB_CAS_CLAIM",
            "dag": dag,
            "authority": authority,
        }
    if phase == "CLAIMED":
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_TASK_CONTROLLER_EXECUTOR_DISPATCH_REQUIRED",
            "task_id": observation.get("task_id"),
            "controller_role": "TaskController",
            "executor_protocol": "agents/shared/slack-controller-executor-protocol.md",
            "controller_skill": "skills/task-controller/SKILL.md",
            "executor_skill": "skills/executor/SKILL.md",
            "slack_is_authority": False,
            "adapter_action": "TASK_CONTROLLER_DISPATCH_EXECUTOR_SLACK",
        }
    if phase == "EXECUTOR_WAIT_CONTROLLER":
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_TASK_CONTROLLER_REVIEW_REQUIRED",
            "task_id": observation.get("task_id"),
            "adapter_action": "TASK_CONTROLLER_REVIEW_EXECUTOR_REPORT",
        }
    if phase == "EXECUTOR_TERMINAL":
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_EXECUTOR_TERMINAL_EVIDENCE_RECHECK_REQUIRED",
            "task_id": observation.get("task_id"),
            "adapter_action": "VERIFY_EXECUTOR_TERMINAL_EVIDENCE",
        }
    if phase == "IMPLEMENTED":
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_PREPROD_PR_REQUIRED",
            "task_id": observation.get("task_id"),
            "target_branch": "pre-prod",
            "route_id": AUTONOMOUS_ROUTE_ID,
            "pr_contract_builder": "tools.node_architect.assemble_autonomous_preprod_pr",
            "managed_evidence_required": True,
            "adapter_action": "ASSEMBLE_AND_CREATE_OR_UPDATE_PREPROD_PR",
        }
    if phase == "G3_READY":
        receipt = observation.get("audit_receipt")
        if not isinstance(receipt, Mapping):
            return {
                "outcome": "PENDING",
                "reason_code": "AUTONOMOUS_G4_PREPROD_AUDIT_REQUIRED",
                "task_id": observation.get("task_id"),
                "target_branch": observation.get("target_branch"),
                "head_sha": observation.get("head_sha"),
                "audit_agent": "agent-audit",
                "audit_skill": "skills/audit-guardrail/SKILL.md",
                "audit_merge_authority": False,
                "adapter_action": "INVOKE_INDEPENDENT_G4_AUDIT",
            }
        receipt_validation = _validate_runtime_audit_binding(observation, receipt)
        if receipt_validation.get("outcome") != "PASS":
            return {**receipt_validation, "adapter_action": None}
        if observation.get("audit_trust_valid") is not True:
            return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_G4_PREPROD_AUDITOR_TRUST_INVALID", "adapter_action": None}
        decision = child_delivery_decision(
            task_id=str(observation.get("task_id", "")),
            target_branch=str(observation.get("target_branch", "")),
            head_sha=str(observation.get("head_sha", "")),
            ci_conclusion=str(observation.get("ci_conclusion", "")),
            review_conclusion=str(observation.get("review_conclusion", "")),
            standing_g4_valid=bool(observation.get("standing_g4_valid")),
            managed_evidence_current=bool(observation.get("managed_evidence_current")),
            required_checks_terminal_success=bool(observation.get("required_checks_terminal_success")),
            audit_conclusion=str(receipt.get("audit_outcome", "")),
            audit_head_sha=str(receipt.get("head_sha", "")),
            audit_independent=receipt.get("independent") is True,
            audit_trust_valid=True,
            audit_receipt_valid=True,
            audit_receipt_digest=str(receipt.get("receipt_digest", "")),
        )
        if decision.get("outcome") != "ALLOW":
            return {**decision, "adapter_action": None}
        return {**decision, "adapter_action": "MERGE_PREPROD_EXACT_HEAD"}
    if phase == "PREPROD_MERGED":
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_PREPROD_DELIVERY_COMPLETE",
            "state": "COMPLETED",
            "task_id": observation.get("task_id"),
            "merge_sha": observation.get("merge_sha"),
            "post_merge_g5_required": False,
            "adapter_action": "MARK_COMPLETE_REQUERY_DAG_AND_PROMOTIONS",
        }
    if phase == "G5_VERIFIED":
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_DAG_REFRESH_REQUIRED",
            "adapter_action": "MARK_COMPLETE_REQUERY_DAG_AND_PROMOTIONS",
        }
    if phase == "PROMOTION_READY":
        from .promotion_controller import evaluate_promotion
        decision = evaluate_promotion(
            promotion_id=str(observation.get("promotion_id", "")),
            required_nodes=observation.get("required_nodes", []),
            completed_nodes=observation.get("completed_nodes", []),
            base_main_sha=str(observation.get("base_main_sha", "")),
            preprod_cut_sha=str(observation.get("preprod_cut_sha", "")),
            integration_conclusion=str(observation.get("integration_conclusion", "")),
            existing_promotion=observation.get("existing_promotion"),
        )
        return {**decision, "adapter_action": decision.get("action") if decision.get("outcome") == "ALLOW" else None}
    return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_RUNTIME_PHASE_INVALID", "adapter_action": None}


__all__ = [
    "canonical_digest", "resolve_ready_nodes", "resolve_authorized_ready_nodes", "claim_task", "validate_task_scope",
    "child_delivery_decision", "next_runtime_action", "drive_closed_loop",
]
