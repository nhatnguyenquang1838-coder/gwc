#!/usr/bin/env python3
"""Validate repo_delivery catalog and host B3 replay-safe decisions."""
from __future__ import annotations
import argparse, hashlib, json, re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Mapping

EXPECTED_NODES = {
    "repo_delivery.branch-creation",
    "repo_delivery.base-drift-check",
    "repo_delivery.scoped-file-write",
    "repo_delivery.diff-readback",
    "repo_delivery.draft-pr-creation",
    "repo_delivery.ci-run-capture",
    "repo_delivery.ci-failure-repair",
    "repo_delivery.ready-for-review-promotion",
    "repo_delivery.pr-blocker-check",
}
ALLOWED_KEYS = {"node_id", "node_type", "title", "canonical", "authority_boundary", "gates", "description"}
ALLOWED_NODE_TYPES = {"actor", "workflow", "gate", "tool", "schema", "state", "projection", "connector"}
ALLOWED_CANONICAL = {"canonical", "delivery_evidence", "audit_projection", "resume_hint"}
ALLOWED_GATES = {"G2_EXECUTION", "G3_PR"}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SUCCESS = {"success", "passed"}
FAILURE = {"failure", "failed", "error", "cancelled", "timed_out", "action_required"}


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def _no_higher_authority() -> dict[str, bool]:
    return {"merge_authority_granted": False, "deployment_authority_granted": False, "production_authority_granted": False}


def _allowed(path: str, patterns: list[str]) -> bool:
    return any((pat.endswith("/**") and path.startswith(pat[:-3] + "/")) or ("*" in pat and fnmatch(path, pat)) or path == pat for pat in patterns)


def decide_ci_failure_repair(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic repair decision for exact-head CI failures."""
    repo = str(evidence.get("repository", ""))
    branch = str(evidence.get("branch", ""))
    base_sha = str(evidence.get("base_sha", ""))
    head_sha = str(evidence.get("head_sha", ""))
    scope_hash = str(evidence.get("scope_hash", ""))
    approved = list(evidence.get("approved_paths") or [])
    repair_paths = [str(p) for p in list(evidence.get("repair_paths") or [])]
    failure = evidence.get("failure") if isinstance(evidence.get("failure"), Mapping) else {}
    reasons: list[str] = []
    if not repo: reasons.append("REPOSITORY_MISSING")
    if not branch: reasons.append("BRANCH_MISSING")
    if not _is_sha(base_sha): reasons.append("INVALID_BASE_SHA")
    if not _is_sha(head_sha): reasons.append("INVALID_HEAD_SHA")
    if not scope_hash.startswith("sha256:"): reasons.append("INVALID_SCOPE_HASH")
    if evidence.get("connector_status", "available") != "available": reasons.append("CI_READBACK_UNAVAILABLE")
    if failure.get("head_sha") != head_sha: reasons.append("STALE_HEAD_FAILURE")
    if failure.get("status") != "completed": reasons.append("CI_NOT_TERMINAL")
    if str(failure.get("conclusion") or "").lower() not in FAILURE: reasons.append("CI_FAILURE_NOT_CONFIRMED")
    if failure.get("repository_fixable") is not True: reasons.append("FAILURE_NOT_REPOSITORY_FIXABLE")
    if evidence.get("unknown_external_outcome"): reasons.append("UNKNOWN_EXTERNAL_OUTCOME_REQUIRES_READBACK")
    if int(evidence.get("prior_attempts", 0) or 0) >= int(evidence.get("max_attempts", 1) or 1): reasons.append("REPAIR_ATTEMPT_LIMIT_REACHED")
    if not repair_paths: reasons.append("REPAIR_PATHS_MISSING")
    out_of_scope = sorted(p for p in repair_paths if not _allowed(p, approved))
    if out_of_scope: reasons.append("OUT_OF_SCOPE_REPAIR_PATH")
    if "CI_READBACK_UNAVAILABLE" in reasons or "UNKNOWN_EXTERNAL_OUTCOME_REQUIRES_READBACK" in reasons:
        outcome = "PENDING_READBACK"
    elif reasons:
        outcome = "BLOCKED"
    else:
        outcome = "REPAIR_ALLOWED"
    payload = {"repository": repo, "branch": branch, "base_sha": base_sha, "head_sha": head_sha, "repair_paths": sorted(repair_paths), "outcome": outcome, "reasons": sorted(set(reasons))}
    return {"outcome": outcome, "reason_codes": sorted(set(reasons)) or ["CI_FAILURE_REPAIR_ALLOWED"], "repository": repo, "branch": branch, "base_sha": base_sha, "head_sha": head_sha, "scope_hash": scope_hash, "repair_paths": sorted(repair_paths), "out_of_scope_paths": out_of_scope, "decision_digest": _digest(payload), **_no_higher_authority()}


def decide_ready_for_review_promotion(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic Draft-to-Ready metadata decision."""
    repo = str(evidence.get("repository", ""))
    pr_number = evidence.get("pr_number")
    branch = str(evidence.get("branch", ""))
    head_sha = str(evidence.get("head_sha", ""))
    pr = evidence.get("pr") if isinstance(evidence.get("pr"), Mapping) else {}
    ci = evidence.get("ci") if isinstance(evidence.get("ci"), Mapping) else {}
    review = evidence.get("review") if isinstance(evidence.get("review"), Mapping) else {}
    reasons: list[str] = []
    if not repo: reasons.append("REPOSITORY_MISSING")
    if not isinstance(pr_number, int): reasons.append("PR_NUMBER_MISSING")
    if not branch: reasons.append("BRANCH_MISSING")
    if not _is_sha(head_sha): reasons.append("INVALID_HEAD_SHA")
    if pr.get("state") != "open": reasons.append("PR_NOT_OPEN")
    if pr.get("draft") is not True: reasons.append("PR_NOT_DRAFT")
    if pr.get("head") != branch: reasons.append("PR_HEAD_BRANCH_MISMATCH")
    if pr.get("head_sha") != head_sha: reasons.append("PR_HEAD_SHA_MISMATCH")
    if pr.get("merged") is True: reasons.append("PR_ALREADY_MERGED")
    if ci.get("outcome") not in {"PASSED", "PASS", "success"}: reasons.append("G3_CI_NOT_PASSED")
    if ci.get("head_sha") != head_sha: reasons.append("CI_HEAD_SHA_MISMATCH")
    if review.get("outcome") not in {"PASS", "PASSED"}: reasons.append("G3_REVIEW_NOT_PASSED")
    if review.get("head_sha") != head_sha: reasons.append("REVIEW_HEAD_SHA_MISMATCH")
    if review.get("unresolved_threads", 0): reasons.append("UNRESOLVED_REVIEW_THREADS")
    if review.get("scope_drift") not in {False, "NONE", "none", None}: reasons.append("SCOPE_DRIFT_DETECTED")
    outcome = "PROMOTE_READY_FOR_REVIEW" if not reasons else "BLOCKED"
    return {"outcome": outcome, "reason_codes": sorted(set(reasons)) or ["READY_FOR_REVIEW_PROMOTION_SAFE"], "repository": repo, "pr_number": pr_number, "branch": branch, "head_sha": head_sha, "decision_digest": _digest({"repo": repo, "pr": pr_number, "head": head_sha, "outcome": outcome, "reasons": sorted(set(reasons))}), **_no_higher_authority()}


def decide_pr_blocker_check(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify current-head PR blockers without granting merge authority."""
    repo = str(evidence.get("repository", ""))
    pr_number = evidence.get("pr_number")
    head_sha = str(evidence.get("head_sha", ""))
    pr = evidence.get("pr") if isinstance(evidence.get("pr"), Mapping) else {}
    blockers: list[dict[str, str]] = []
    def block(code: str, severity: str, source: str) -> None:
        blockers.append({"code": code, "severity": severity, "source": source})
    if not repo: block("REPOSITORY_MISSING", "high", "input")
    if not isinstance(pr_number, int): block("PR_NUMBER_MISSING", "high", "input")
    if not _is_sha(head_sha): block("INVALID_HEAD_SHA", "high", "input")
    if pr.get("state") != "open": block("PR_NOT_OPEN", "high", "pr")
    if pr.get("head_sha") != head_sha: block("PR_HEAD_SHA_MISMATCH", "high", "pr")
    if pr.get("mergeable") is False: block("PR_NOT_MERGEABLE", "medium", "pr")
    if pr.get("draft") is True: block("PR_STILL_DRAFT", "medium", "pr")
    if pr.get("merged") is True: block("PR_ALREADY_MERGED", "high", "pr")
    checks = list(evidence.get("required_checks") or [])
    if not checks: block("REQUIRED_CHECKS_MISSING", "medium", "checks")
    for check in checks:
        if not isinstance(check, Mapping):
            block("INVALID_CHECK_READBACK", "medium", "checks"); continue
        if check.get("head_sha") != head_sha:
            block("STALE_CHECK_IGNORED", "medium", "checks"); continue
        if check.get("status") != "completed": block("CHECK_NON_TERMINAL", "medium", "checks")
        elif str(check.get("conclusion") or "").lower() not in SUCCESS: block("CHECK_NOT_SUCCESSFUL", "high", "checks")
    for thread in list(evidence.get("review_threads") or []):
        if isinstance(thread, Mapping) and thread.get("resolved") is False: block("UNRESOLVED_REVIEW_THREAD", "medium", "review_threads")
    latest: dict[str, str] = {}
    for review in list(evidence.get("reviews") or []):
        if not isinstance(review, Mapping): continue
        if review.get("head_sha") != head_sha:
            block("STALE_REVIEW_IGNORED", "low", "reviews"); continue
        latest[str(review.get("author") or review.get("user") or "unknown")] = str(review.get("state") or "").upper()
    if any(state == "CHANGES_REQUESTED" for state in latest.values()): block("CHANGES_REQUESTED", "high", "reviews")
    outcome = "CLEAR" if not blockers else "BLOCKED"
    reasons = sorted({b["code"] for b in blockers}) or ["NO_PR_BLOCKERS_DETECTED"]
    return {"outcome": outcome, "reason_codes": reasons, "repository": repo, "pr_number": pr_number, "head_sha": head_sha, "blockers": blockers, "decision_digest": _digest({"repo": repo, "pr": pr_number, "head": head_sha, "blockers": blockers, "outcome": outcome}), **_no_higher_authority()}


def validate_family(family_dir: Path) -> list[str]:
    errors: list[str] = []
    files = sorted(family_dir.glob("*.node.json"))
    if len(files) != 9:
        errors.append(f"expected 9 node files, found {len(files)}")
    seen: set[str] = set()
    for file_path in files:
        try:
            node = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{file_path}: invalid json: {exc}"); continue
        extra = set(node) - ALLOWED_KEYS
        if extra: errors.append(f"{file_path}: unexpected keys {sorted(extra)}")
        node_id = node.get("node_id")
        if node_id in seen: errors.append(f"{file_path}: duplicate node_id {node_id}")
        seen.add(node_id)
        if node_id not in EXPECTED_NODES: errors.append(f"{file_path}: unexpected node_id {node_id}")
        if not str(node_id).startswith("repo_delivery."): errors.append(f"{file_path}: node_id must start with repo_delivery.")
        if node.get("authority_boundary") != "g2_required": errors.append(f"{file_path}: authority_boundary must be g2_required")
        if node.get("node_type") not in ALLOWED_NODE_TYPES: errors.append(f"{file_path}: invalid node_type {node.get('node_type')}")
        if node.get("canonical") not in ALLOWED_CANONICAL: errors.append(f"{file_path}: invalid canonical {node.get('canonical')}")
        gates = node.get("gates")
        if not isinstance(gates, list) or not gates: errors.append(f"{file_path}: gates must be a non-empty list")
        else:
            invalid = set(gates) - ALLOWED_GATES
            if invalid: errors.append(f"{file_path}: gates outside repo-delivery boundary {sorted(invalid)}")
            if "G2_EXECUTION" not in gates: errors.append(f"{file_path}: gates must include G2_EXECUTION")
            if len(gates) != len(set(gates)): errors.append(f"{file_path}: gates must be unique")
    missing = EXPECTED_NODES - seen
    if missing: errors.append(f"missing expected nodes: {sorted(missing)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-dir", type=Path, default=Path("core/node-architect/node-catalog/repo_delivery"))
    args = parser.parse_args()
    errors = validate_family(args.family_dir)
    if errors:
        for error in errors: print(error)
        return 1
    print("REPO_DELIVERY_NODE_CATALOG_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
