#!/usr/bin/env python3
"""Plan one isolated autonomous task branch off the verified pre-prod SHA.

Data-only and deterministic: this module never calls git, GitHub or Jira. It
produces (or refuses) a branch plan that downstream bounded G2 execution may
apply. All guardrails from SCRUM-275 are enforced here so that an invalid plan
can never reach an executor.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

ALLOWED_BASE_BRANCH = "pre-prod"
FORBIDDEN_BASE_BRANCHES = {"main", "master", "release", "prod", "production"}
HEAD_PATTERN = re.compile(r"^auto/[0-9a-zA-Z][0-9a-zA-Z._-]{0,63}/[0-9a-zA-Z][0-9a-zA-Z._-]{0,63}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class BranchPlanError(ValueError):
    """Raised when a requested autonomous branch plan violates the guardrails."""


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value):
        raise BranchPlanError(f"{field} must be a 40-character lowercase hex SHA")
    return value


def expected_head_ref(run_id: str, task_id: str) -> str:
    """Return the only head ref shape an autonomous run may create."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise BranchPlanError("run_id is required")
    if not isinstance(task_id, str) or not task_id.strip():
        raise BranchPlanError("task_id is required")
    ref = f"auto/{run_id.strip()}/{task_id.strip()}"
    if not HEAD_PATTERN.fullmatch(ref):
        raise BranchPlanError(f"derived head ref is not guardrail-conformant: {ref}")
    return ref


def create_task_branch_plan(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a branch request and return the canonical branch plan.

    Raises BranchPlanError on any guardrail violation (forbidden base, wrong
    head shape, missing verified pre-prod SHA, force push or branch deletion).
    """
    if not isinstance(request, Mapping):
        raise BranchPlanError("request must be a mapping")

    base_branch = request.get("base_branch")
    if base_branch in FORBIDDEN_BASE_BRANCHES:
        raise BranchPlanError(f"autonomous runtime may not branch or target '{base_branch}'")
    if base_branch != ALLOWED_BASE_BRANCH:
        raise BranchPlanError(f"base_branch must be '{ALLOWED_BASE_BRANCH}'")

    base_sha = _require_sha(request.get("base_sha"), "base_sha")
    if not request.get("base_sha_verified", False):
        raise BranchPlanError("base_sha must be verified against the protected pre-prod branch")
    if request.get("force_push"):
        raise BranchPlanError("force push is forbidden for autonomous runs")
    if request.get("delete_branch"):
        raise BranchPlanError("branch deletion by the autonomous runtime is forbidden in MVP")

    head_ref = expected_head_ref(str(request.get("run_id", "")), str(request.get("task_id", "")))
    requested_head = request.get("head_ref")
    if requested_head is not None and requested_head != head_ref:
        raise BranchPlanError(f"head_ref must be '{head_ref}', got '{requested_head}'")

    worktree = request.get("worktree_path")
    if not isinstance(worktree, str) or not worktree.strip():
        raise BranchPlanError("worktree_path is required (one task = one worktree = one branch)")

    return {
        "artifact_type": "autonomous-task-branch-plan",
        "schema_version": "1.0",
        "repository": request.get("repository"),
        "run_id": str(request["run_id"]).strip(),
        "task_id": str(request["task_id"]).strip(),
        "base_branch": ALLOWED_BASE_BRANCH,
        "base_sha": base_sha,
        "head_ref": head_ref,
        "worktree_path": worktree,
        "push_allowed_refs": [head_ref],
        "prohibited": sorted(
            {"direct_write_to_pre_prod", "direct_write_to_main", "force_push", "branch_deletion", "pr_base_change"}
        ),
    }
