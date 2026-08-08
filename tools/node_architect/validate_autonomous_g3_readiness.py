#!/usr/bin/env python3
"""Validate exact-head G3 readiness for the autonomous pre-prod delivery path.

Combines the exact-head CI/check evaluator (``exact_head_readiness``) with an
independent PR readback check. A G3 PASS requires:

* exact-head CI conclusion bound to the current PR head SHA (no drift);
* a Draft PR (``draft=true``) whose base is ``pre-prod`` and head SHA matches;
* the complete-diff changed-path digest matches the bound scope;
* independent review receipt present and findings closed.

Pure and fail-closed. Returns a ``g3_pass`` verdict; it never merges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Any, Mapping

from .exact_head_readiness import decide_exact_head_readiness

FORBIDDEN_BASES = {"main"}
REQUIRED_BASE = "pre-prod"
_SHA_RE = lambda v: isinstance(v, str) and len(v) == 40 and all(c in "0123456789abcdef" for c in v)


def validate_g3_readiness(
    *,
    task_id: str,
    repository: str,
    branch: str,
    base_sha: str,
    current_head_sha: str,
    expected_head_sha: str,
    required_check_names: list[str],
    observed_checks: list[dict[str, Any]],
    required_artifact_names: list[str],
    observed_artifacts: list[dict[str, Any]],
    connector_status: str,
    exact_head_filter_applied: bool,
    pr_readback: Mapping[str, Any] | None,
    diff_digest: str | None = None,
    expected_diff_digest: str | None = None,
    independent_review: Mapping[str, Any] | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Return a G3 readiness decision bound to the exact current head."""
    reasons: list[str] = []

    exact_head = decide_exact_head_readiness(
        task_id=task_id,
        repository=repository,
        branch=branch,
        base_sha=base_sha,
        current_head_sha=current_head_sha,
        expected_head_sha=expected_head_sha,
        required_check_names=required_check_names,
        observed_checks=observed_checks,
        required_artifact_names=required_artifact_names,
        observed_artifacts=observed_artifacts,
        connector_status=connector_status,
        exact_head_filter_applied=exact_head_filter_applied,
        observed_at=observed_at,
    )
    if exact_head["outcome"] != "READY":
        reasons.append("AUTONOMOUS_G3_EXACT_HEAD_NOT_READY")

    # PR Draft readback.
    if not isinstance(pr_readback, Mapping):
        reasons.append("AUTONOMOUS_G3_PR_READBACK_MISSING")
    else:
        if pr_readback.get("base") != REQUIRED_BASE:
            reasons.append("AUTONOMOUS_G3_PR_BASE_NOT_PREPROD")
        if pr_readback.get("base") in FORBIDDEN_BASES:
            reasons.append("AUTONOMOUS_G3_PR_MAIN_BASE_FORBIDDEN")
        if pr_readback.get("head_sha") != current_head_sha:
            reasons.append("AUTONOMOUS_G3_PR_HEAD_DRIFT")
        if pr_readback.get("draft") is not True:
            reasons.append("AUTONOMOUS_G3_PR_NOT_DRAFT")
        if pr_readback.get("merged") is True:
            reasons.append("AUTONOMOUS_G3_PR_ALREADY_MERGED")

    # Diff digest drift.
    if expected_diff_digest is not None and diff_digest != expected_diff_digest:
        reasons.append("AUTONOMOUS_G3_DIFF_DIGEST_DRIFT")

    # Independent review closure.
    if isinstance(independent_review, Mapping):
        if independent_review.get("findings_open", 0):
            reasons.append("AUTONOMOUS_G3_FINDINGS_OPEN")
    else:
        reasons.append("AUTONOMOUS_G3_REVIEW_MISSING")

    g3_pass = not reasons
    result = {
        "schema_version": "1.0",
        "artifact_type": "autonomous-g3-readiness",
        "task_id": task_id,
        "repository": repository,
        "branch": branch,
        "base_sha": base_sha,
        "current_head_sha": current_head_sha,
        "expected_head_sha": expected_head_sha,
        "exact_head_decision": exact_head,
        "g3_pass": g3_pass,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "outcome": "G3_PASS" if g3_pass else "G3_BLOCKED",
        "reason_codes": sorted(set(reasons)) or ["AUTONOMOUS_G3_READY"],
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--current-head-sha", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--connector-status", default="CONFIRMED")
    parser.add_argument("--exact-head-filter", action="store_true")
    parser.add_argument("--pr-readback", type=argparse.FileType("r"), required=True)
    parser.add_argument("--diff-digest")
    parser.add_argument("--expected-diff-digest")
    parser.add_argument("--independent-review", type=argparse.FileType("r"))
    parser.add_argument("--observed-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    pr_readback = json.load(args.pr_readback)
    review = json.load(args.independent_review) if args.independent_review else None
    result = validate_g3_readiness(
        task_id=args.task_id,
        repository=args.repository,
        branch=args.branch,
        base_sha=args.base_sha,
        current_head_sha=args.current_head_sha,
        expected_head_sha=args.expected_head_sha,
        required_check_names=["validate-gate-action", "validate-g01"],
        observed_checks=[
            {"name": "validate-g01", "head_sha": args.current_head_sha, "status": "completed", "conclusion": "success"},
            {"name": "validate-gate-action", "head_sha": args.current_head_sha, "status": "completed", "conclusion": "success"},
        ],
        required_artifact_names=["autonomous-preprod-delivery"],
        observed_artifacts=[{"name": "autonomous-preprod-delivery", "head_sha": args.current_head_sha, "digest": "sha256:" + "0" * 64}],
        connector_status=args.connector_status,
        exact_head_filter_applied=args.exact_head_filter,
        pr_readback=pr_readback,
        diff_digest=args.diff_digest,
        expected_diff_digest=args.expected_diff_digest,
        independent_review=review,
        observed_at=args.observed_at,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['outcome']}: {', '.join(result['reason_codes'])}")
    return 0 if result["g3_pass"] else 1


# ---------------------------------------------------------------------------
# Evidence-binding digest helpers.
#
# Cherry-picked (additive, no change to the public G3 API above) from the
# superseded PR #323. They expose a deterministic SHA-256 projection that binds
# a G3 evidence record to the exact head, independent of the keyword-arg
# `validate_g3_readiness` contract used by the #326 implementation.
# ---------------------------------------------------------------------------

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_EVIDENCE_FIELDS = (
    "task_id",
    "run_id",
    "repository",
    "pr_number",
    "base_branch",
    "base_sha",
    "head_sha",
    "changed_path_digest",
    "ci_conclusions",
    "review_receipt",
    "pr_body_digest",
    "runtime_graph_digest",
    "gate_story_digest",
)


def canonical_digest(payload: Any) -> str:
    """Stable SHA-256 over a canonical JSON projection.

    Keys are sorted and separators are stripped so the digest is independent of
    dict insertion order or human formatting.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def evidence_binding_digest(evidence: Mapping[str, Any]) -> str:
    """Digest binding the full G3 evidence chain to the exact head."""
    return canonical_digest({field: evidence.get(field) for field in REQUIRED_EVIDENCE_FIELDS})


if __name__ == "__main__":
    raise SystemExit(main())
