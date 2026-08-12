#!/usr/bin/env python3
"""Immutable DAG-cut promotion decisions for autonomous pre-prod -> human main review."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def evaluate_promotion(*, promotion_id: str, required_nodes: Sequence[str], completed_nodes: Sequence[str],
                       base_main_sha: str, preprod_cut_sha: str, integration_conclusion: str,
                       existing_promotion: Mapping[str, Any] | None = None) -> dict[str, Any]:
    required = sorted(set(str(x) for x in required_nodes))
    completed = set(str(x) for x in completed_nodes)
    missing = [x for x in required if x not in completed]
    if missing:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_PROMOTION_DAG_INCOMPLETE", "missing_nodes": missing}
    if not _valid_sha(base_main_sha) or not _valid_sha(preprod_cut_sha):
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_PROMOTION_SHA_INVALID"}
    if integration_conclusion != "success":
        return {"outcome": "PENDING" if integration_conclusion in {"queued", "in_progress", "pending"} else "BLOCKED",
                "reason_code": "AUTONOMOUS_PROMOTION_INTEGRATION_NOT_GREEN"}

    identity = {
        "promotion_id": promotion_id,
        "required_nodes": required,
        "base_main_sha": base_main_sha,
        "preprod_cut_sha": preprod_cut_sha,
    }
    evidence_digest = _digest(identity)
    idempotency_key = _digest({"kind": "promotion-draft", **identity})
    promotion_branch = f"promotion/{promotion_id}/{preprod_cut_sha[:12]}"

    if existing_promotion:
        if existing_promotion.get("idempotency_key") == idempotency_key:
            return {
                "outcome": "ALLOW",
                "reason_code": "AUTONOMOUS_PROMOTION_REPLAY",
                "action": "READBACK_EXISTING_DRAFT_PR",
                "idempotency_key": idempotency_key,
                "evidence_digest": evidence_digest,
                "promotion_branch": promotion_branch,
                "main_merge_allowed": False,
            }
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_PROMOTION_CUT_DRIFT"}

    return {
        "outcome": "ALLOW",
        "reason_code": "AUTONOMOUS_PROMOTION_DRAFT_ALLOWED",
        "action": "CREATE_IMMUTABLE_PROMOTION_BRANCH_AND_DRAFT_PR",
        "promotion_id": promotion_id,
        "required_nodes": required,
        "base_branch": "main",
        "base_main_sha": base_main_sha,
        "source_branch": promotion_branch,
        "preprod_cut_sha": preprod_cut_sha,
        "draft": True,
        "mark_ready_allowed": False,
        "main_merge_allowed": False,
        "evidence_digest": evidence_digest,
        "idempotency_key": idempotency_key,
    }


def autonomous_main_action_allowed(action: str) -> bool:
    """Only immutable-cut Draft PR assembly is autonomous on the main boundary."""
    return action in {"create_promotion_branch", "create_draft_pr", "readback_draft_pr",
                      "mark_ready_for_review"}


def promote_to_ready_for_review(*, promotion_id: str, head_sha: str, reviewed_head_sha: str,
                                 g3_conclusion: str, required_ci_conclusion: str,
                                 blockers: Sequence[str], draft: bool, pr_open: bool,
                                 existing_ready: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Mark a Draft PR Ready for Review ONLY when every required proof binds the SAME exact head.

    Implements repo_delivery.ready-for-review-promotion (SCRUM-323 / NA81-F3-N08).
    Ready status grants NO merge authority. Fails closed for stale/missing/mixed-head/
    pending/failing/blocker evidence. Reconciles an already-Ready state idempotently.
    """
    if not _valid_sha(head_sha) or not _valid_sha(reviewed_head_sha):
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_READY_SHA_INVALID",
                "main_merge_allowed": False}
    if head_sha != reviewed_head_sha:
        # head moved under the reviewed evidence -> never promote; require fresh G3/CI
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_READY_MIXED_HEAD",
                "observed_head": head_sha, "reviewed_head": reviewed_head_sha,
                "main_merge_allowed": False}
    if not draft or not pr_open:
        # not a live Draft PR -> cannot promote
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_READY_NOT_DRAFT_PR",
                "draft": draft, "pr_open": pr_open, "main_merge_allowed": False}
    if blockers:
        return {"outcome": "BLOCKED", "reason_code": "AUTONOMOUS_READY_BLOCKER_PRESENT",
                "blockers": sorted(set(str(b) for b in blockers)), "main_merge_allowed": False}
    if g3_conclusion != "pass":
        return {"outcome": "PENDING" if g3_conclusion in {"queued", "in_progress", "pending", ""} else "BLOCKED",
                "reason_code": "AUTONOMOUS_READY_G3_NOT_PASS", "g3_conclusion": g3_conclusion,
                "main_merge_allowed": False}
    if required_ci_conclusion != "success":
        return {"outcome": "PENDING" if required_ci_conclusion in {"queued", "in_progress", "pending", ""} else "BLOCKED",
                "reason_code": "AUTONOMOUS_READY_CI_NOT_GREEN", "ci_conclusion": required_ci_conclusion,
                "main_merge_allowed": False}

    identity = {"promotion_id": promotion_id, "head_sha": head_sha,
                "g3_conclusion": g3_conclusion, "required_ci_conclusion": required_ci_conclusion}
    evidence_digest = _digest(identity)
    idempotency_key = _digest({"kind": "ready-for-review", **identity})

    if existing_ready and existing_ready.get("idempotency_key") == idempotency_key:
        # already Ready, same exact bindings -> idempotent readback, no no-op re-promotion
        return {"outcome": "READY", "reason_code": "AUTONOMOUS_READY_REPLAY",
                "action": "READBACK_READY_PR", "idempotency_key": idempotency_key,
                "evidence_digest": evidence_digest, "main_merge_allowed": False}

    return {"outcome": "READY", "reason_code": "AUTONOMOUS_READY_PROMOTED",
            "action": "MARK_READY_FOR_REVIEW", "idempotency_key": idempotency_key,
            "evidence_digest": evidence_digest, "main_merge_allowed": False}


__all__ = ["evaluate_promotion", "autonomous_main_action_allowed", "promote_to_ready_for_review"]
