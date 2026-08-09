#!/usr/bin/env python3
"""Validate and plan the governed squash-merge of an autonomous pre-prod PR.

Pure, fail-closed decision tool. It performs NO merge itself; the runtime
workflow executes the squash merge only after the standing-policy G4 receipt is
validated (see ``materialize_autonomous_g4_receipt``) and this tool returns
``outcome: MERGE_INTO_PREPROD``.

Hard invariants:

* The merge target must be ``pre-prod``; ``main`` is forbidden.
* The approved head SHA must equal the live PR head SHA (no drift).
* G3 must be PASS for the exact current head.
* Every required exact-head check must be terminal-success.
* The managed autonomous PR evidence must be current for the exact head.
* The standing-policy G4 receipt must be valid before a merge plan is emitted.
* A merge-proof binding the approved head and the resulting ``pre-prod`` merge
  SHA is produced for canonical evidence.
* No deploy, release, or production authority is inferred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any, Mapping

FORBIDDEN_TARGETS = {"main"}
REQUIRED_TARGET = "pre-prod"
ROUTE_ID = "AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN"
_SHA_RE = lambda v: isinstance(v, str) and len(v) == 40 and all(c in "0123456789abcdef" for c in v)


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def plan_merge(
    *,
    run_id: str,
    task_id: str,
    repository: str,
    pr_number: int,
    target_branch: str,
    approved_head_sha: str,
    live_head_sha: str,
    g3_pass: bool = False,
    required_checks_terminal_success: bool = False,
    managed_evidence_current: bool = False,
    standing_g4_valid: bool = False,
    preprod_merge_sha: str | None = None,
) -> dict[str, Any]:
    """Return a fail-closed merge plan bound to exact-head delivery evidence."""
    reasons: list[str] = []
    if target_branch != REQUIRED_TARGET:
        reasons.append("AUTONOMOUS_MERGE_TARGET_NOT_PREPROD")
    if target_branch in FORBIDDEN_TARGETS:
        reasons.append("AUTONOMOUS_MERGE_MAIN_TARGET_FORBIDDEN")
    if not _SHA_RE(approved_head_sha):
        reasons.append("AUTONOMOUS_MERGE_APPROVED_HEAD_INVALID")
    if not _SHA_RE(live_head_sha):
        reasons.append("AUTONOMOUS_MERGE_LIVE_HEAD_INVALID")
    if approved_head_sha != live_head_sha:
        reasons.append("AUTONOMOUS_MERGE_HEAD_DRIFT")
    if not g3_pass:
        reasons.append("AUTONOMOUS_MERGE_G3_NOT_PASS")
    if not required_checks_terminal_success:
        reasons.append("AUTONOMOUS_MERGE_REQUIRED_CHECKS_NOT_TERMINAL_SUCCESS")
    if not managed_evidence_current:
        reasons.append("AUTONOMOUS_MERGE_MANAGED_EVIDENCE_NOT_CURRENT")
    if not standing_g4_valid:
        reasons.append("AUTONOMOUS_MERGE_STANDING_G4_INVALID")

    merge_proof = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-merge-proof",
        "route_id": ROUTE_ID,
        "run_id": run_id,
        "task_id": task_id,
        "repository": repository,
        "pr_number": pr_number,
        "target_branch": target_branch,
        "approved_head_sha": approved_head_sha,
        "live_head_sha": live_head_sha,
        "g3_pass": bool(g3_pass),
        "required_checks_terminal_success": bool(required_checks_terminal_success),
        "managed_evidence_current": bool(managed_evidence_current),
        "standing_g4_valid": bool(standing_g4_valid),
        "preprod_merge_sha": preprod_merge_sha,
    }
    merge_proof["merge_proof_digest"] = _digest(
        {k: v for k, v in merge_proof.items() if k != "merge_proof_digest"}
    )

    outcome = "MERGE_INTO_PREPROD" if not reasons else "REJECTED"
    decision = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-preprod-merge-plan",
        "route_id": ROUTE_ID,
        "run_id": run_id,
        "task_id": task_id,
        "repository": repository,
        "pr_number": pr_number,
        "target_branch": target_branch,
        "approved_head_sha": approved_head_sha,
        "live_head_sha": live_head_sha,
        "merge_command": f"gh pr merge {pr_number} --squash --branch {target_branch}",
        "merge_proof": merge_proof,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "outcome": outcome,
        "reason_codes": sorted(set(reasons)) or ["AUTONOMOUS_MERGE_SAFE"],
    }
    decision["decision_digest"] = _digest(
        {k: v for k, v in decision.items() if k != "decision_digest"}
    )
    return decision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--target-branch", required=True)
    parser.add_argument("--approved-head-sha", required=True)
    parser.add_argument("--live-head-sha", required=True)
    parser.add_argument("--g3-pass", action="store_true")
    parser.add_argument("--required-checks-terminal-success", action="store_true")
    parser.add_argument("--managed-evidence-current", action="store_true")
    parser.add_argument("--standing-g4-valid", action="store_true")
    parser.add_argument("--preprod-merge-sha")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    decision = plan_merge(
        run_id=args.run_id,
        task_id=args.task_id,
        repository=args.repository,
        pr_number=args.pr_number,
        target_branch=args.target_branch,
        approved_head_sha=args.approved_head_sha,
        live_head_sha=args.live_head_sha,
        g3_pass=args.g3_pass,
        required_checks_terminal_success=args.required_checks_terminal_success,
        managed_evidence_current=args.managed_evidence_current,
        standing_g4_valid=args.standing_g4_valid,
        preprod_merge_sha=args.preprod_merge_sha,
    )
    if args.json:
        print(json.dumps(decision, indent=2, sort_keys=True))
    else:
        print(f"{decision['outcome']}: {', '.join(decision['reason_codes'])}")
    return 0 if decision["outcome"] == "MERGE_INTO_PREPROD" else 1


if __name__ == "__main__":
    raise SystemExit(main())
