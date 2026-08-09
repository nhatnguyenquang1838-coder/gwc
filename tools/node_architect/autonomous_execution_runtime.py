#!/usr/bin/env python3
"""Deterministic closed-loop decisions for autonomous delivery to pre-prod.

SCRUM-379 hotfix invariant: AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN.
This module is deliberately side-effect free. Adapters perform Jira/GitHub/CI writes
only after consuming an ALLOW decision bound to the same immutable inputs.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

TERMINAL_COMPLETE = {"COMPLETED", "G5_VERIFIED"}
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


def claim_task(*, task_id: str, ready_task_ids: Sequence[str], claimant: str, lease_id: str,
               existing_claim: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Produce replay-safe atomic-claim intent; adapter must CAS this against Jira/GitHub."""
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
    """Allow control-plane implementation only when it cannot rewrite this run's authority plane."""
    if task.get("task_id") != manifest_task.get("task_id"):
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_TASK_NOT_ALLOWLISTED"}
    risk = str(task.get("risk", manifest_task.get("risk", "R3")))
    if RISK_ORDER.get(risk, 99) > MAX_AUTONOMOUS_RISK:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING"}
    allowed = set(str(p) for p in manifest_task.get("allowed_paths", []))
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
                            required_checks_terminal_success: bool = False) -> dict[str, Any]:
    """Decide whether an exact-head child PR may merge autonomously to pre-prod.

    A coarse CI summary is not sufficient. The adapter must separately prove that
    all required checks are terminal-success and that the managed PR evidence is
    current for the exact head. This prevents a connector-side merge from racing
    or bypassing a failing G4/CI check.
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
    if not standing_g4_valid:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_STANDING_G4_AUTHORITY_INVALID"}
    evidence = {
        "task_id": task_id,
        "target_branch": target_branch,
        "head_sha": head_sha,
        "route_id": AUTONOMOUS_ROUTE_ID,
        "required_checks_terminal_success": True,
        "managed_evidence_current": True,
        "standing_g4_valid": True,
    }
    return {
        "outcome": "ALLOW",
        "reason_code": "AUTONOMOUS_PREPROD_MERGE_ALLOWED",
        "route_id": AUTONOMOUS_ROUTE_ID,
        "merge_allowed": True,
        "main_merge_allowed": False,
        "evidence_digest": canonical_digest(evidence),
    }


def next_runtime_action(*, dag: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Select the next unclaimed READY node deterministically; parallel adapters may shard externally."""
    claims = claims or {}
    for task_id in dag.get("ready_task_ids", []):
        if task_id not in claims:
            return {"outcome": "READY", "task_id": task_id, "action": "CLAIM_AND_EXECUTE"}
    return {"outcome": "IDLE", "reason_code": "AUTONOMOUS_NO_UNCLAIMED_READY_TASK"}


def drive_closed_loop(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Map one observed autonomous state to exactly one next side-effect intent.

    This is the scheduler/adapter boundary: the function never performs external writes.
    The caller must execute the returned adapter_action, read back authoritative state,
    and invoke the runtime again with the new exact evidence.
    """
    phase = str(observation.get("phase", "DISCOVER")).upper()
    if phase == "DISCOVER":
        dag = resolve_ready_nodes(observation.get("tasks", []))
        nxt = next_runtime_action(dag=dag, claims=observation.get("claims", {}))
        if nxt.get("outcome") != "READY":
            return {**nxt, "adapter_action": None, "dag": dag}
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_READY_TASK_SELECTED",
            "task_id": nxt["task_id"],
            "adapter_action": "JIRA_GITHUB_CAS_CLAIM",
            "dag": dag,
        }
    if phase == "CLAIMED":
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_AGENT_EXECUTION_REQUIRED",
            "task_id": observation.get("task_id"),
            "adapter_action": "INVOKE_AGENT_E2E",
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
        decision = child_delivery_decision(
            task_id=str(observation.get("task_id", "")),
            target_branch=str(observation.get("target_branch", "")),
            head_sha=str(observation.get("head_sha", "")),
            ci_conclusion=str(observation.get("ci_conclusion", "")),
            review_conclusion=str(observation.get("review_conclusion", "")),
            standing_g4_valid=bool(observation.get("standing_g4_valid")),
            managed_evidence_current=bool(observation.get("managed_evidence_current")),
            required_checks_terminal_success=bool(observation.get("required_checks_terminal_success")),
        )
        if decision.get("outcome") != "ALLOW":
            return {**decision, "adapter_action": None}
        return {**decision, "adapter_action": "MERGE_PREPROD_EXACT_HEAD"}
    if phase == "PREPROD_MERGED":
        return {
            "outcome": "ALLOW",
            "reason_code": "AUTONOMOUS_G5_EXACT_SHA_REQUIRED",
            "task_id": observation.get("task_id"),
            "merge_sha": observation.get("merge_sha"),
            "adapter_action": "VERIFY_PREPROD_G5_EXACT_SHA",
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
    "canonical_digest", "resolve_ready_nodes", "claim_task", "validate_task_scope",
    "child_delivery_decision", "next_runtime_action", "drive_closed_loop",
]
