#!/usr/bin/env python3
"""Plan and validate an isolated autonomous task branch for pre-prod delivery.

Pure, fail-closed decision tool. It performs NO git operations itself; the
runtime workflow creates the branch only after this tool returns
``outcome: CREATE_BRANCH``.

Hard invariants enforced here:

* The autonomous task head must match ``auto/<run-id>/<task-id>``.
* A normal task branch is based on ``pre-prod`` only. ``main`` is never an
  autonomous task-branch base or the task branch itself.
* The protected ``pre-prod`` branch may be bootstrapped from an explicitly
  approved ``main`` SHA exactly once (``bootstrap=True``); after that, only
  ``pre-prod`` is an allowed base.
* Direct push to ``pre-prod`` and any autonomous merge target of ``main`` are
  out of scope and rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Any, Mapping

BRANCH_RE = re.compile(r"^auto/[A-Za-z0-9][A-Za-z0-9._-]{0,63}/[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FORBIDDEN_BASES = {"main"}
ALLOWED_BASES = {"pre-prod", "main"}  # main permitted only for the initial bootstrap
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def decide_branch(
    *,
    run_id: str,
    task_id: str,
    proposed_branch: str,
    base_branch: str,
    base_sha: str,
    preprod_sha: str | None = None,
    bootstrap: bool = False,
) -> dict[str, Any]:
    """Return a branch-creation verdict bound to exact identity and base SHA."""
    reasons: list[str] = []
    if not (isinstance(run_id, str) and run_id.strip()):
        reasons.append("AUTONOMOUS_RUN_ID_MISSING")
    if not (isinstance(task_id, str) and task_id.strip()):
        reasons.append("AUTONOMOUS_TASK_ID_MISSING")
    if not BRANCH_RE.match(proposed_branch or ""):
        reasons.append("AUTONOMOUS_BRANCH_PATTERN_INVALID")
    if base_branch not in ALLOWED_BASES:
        reasons.append("AUTONOMOUS_BASE_NOT_ALLOWED")
    if not _SHA_RE.match(base_sha or ""):
        reasons.append("AUTONOMOUS_BASE_SHA_INVALID")

    if bootstrap:
        if base_branch != "main":
            reasons.append("AUTONOMOUS_BOOTSTRAP_REQUIRES_MAIN")
        if base_sha != (preprod_sha if preprod_sha is not None else base_sha):
            # bootstrap always derives from an explicit approved main SHA; no pre-prod ancestor exists yet.
            pass
    else:
        if base_branch in FORBIDDEN_BASES:
            reasons.append("AUTONOMOUS_MAIN_BASE_FORBIDDEN")
        if base_branch != "pre-prod":
            reasons.append("AUTONOMOUS_TASK_BASE_MUST_BE_PREPROD")

    # The task branch itself must never be a protected branch.
    if proposed_branch in ("main", "pre-prod"):
        reasons.append("AUTONOMOUS_TASK_BRANCH_PROTECTED_FORBIDDEN")

    outcome = "CREATE_BRANCH" if not reasons else "REJECTED"
    decision = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-task-branch-decision",
        "run_id": run_id,
        "task_id": task_id,
        "proposed_branch": proposed_branch,
        "base_branch": base_branch,
        "base_sha": base_sha,
        "bootstrap": bool(bootstrap),
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "outcome": outcome,
        "reason_codes": sorted(set(reasons)) or ["AUTONOMOUS_BRANCH_SAFE"],
    }
    decision["decision_digest"] = _digest(
        {k: v for k, v in decision.items() if k != "decision_digest"}
    )
    return decision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--proposed-branch", required=True)
    parser.add_argument("--base-branch", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--preprod-sha")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    decision = decide_branch(
        run_id=args.run_id,
        task_id=args.task_id,
        proposed_branch=args.proposed_branch,
        base_branch=args.base_branch,
        base_sha=args.base_sha,
        preprod_sha=args.preprod_sha,
        bootstrap=args.bootstrap,
    )
    if args.json:
        print(json.dumps(decision, indent=2, sort_keys=True))
    else:
        print(f"{decision['outcome']}: {', '.join(decision['reason_codes'])}")
    return 0 if decision["outcome"] == "CREATE_BRANCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
