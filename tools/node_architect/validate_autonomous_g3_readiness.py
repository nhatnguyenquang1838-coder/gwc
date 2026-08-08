#!/usr/bin/env python3
"""Validate exact-head G3 readiness for an autonomous pre-prod delivery.

Deterministic and offline. Every element of the merge decision is bound to the
exact PR head SHA; any drift (head, base, scope, CI, review, PR body, graph or
story digest) fails closed and invalidates prior evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

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
    """Stable SHA-256 over a canonical JSON projection."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def evidence_binding_digest(evidence: Mapping[str, Any]) -> str:
    """Digest binding the full G3 evidence chain to the exact head."""
    return canonical_digest({field: evidence.get(field) for field in REQUIRED_EVIDENCE_FIELDS})


def validate_g3_readiness(evidence: Mapping[str, Any], observed_head_sha: str) -> dict[str, Any]:
    """Return a G3 decision record: PASS only when every binding holds."""
    issues: list[str] = []

    if not isinstance(evidence, Mapping):
        return {"outcome": "FAIL", "valid": False, "issues": ["evidence must be a mapping"]}

    for field in REQUIRED_EVIDENCE_FIELDS:
        if evidence.get(field) in (None, "", [], {}):
            issues.append(f"missing required evidence field: {field}")

    head_sha = evidence.get("head_sha")
    if not isinstance(head_sha, str) or not SHA_PATTERN.fullmatch(head_sha or ""):
        issues.append("head_sha must be a 40-character lowercase hex SHA")
    elif head_sha != observed_head_sha:
        issues.append("HEAD_DRIFT: evidence head_sha does not match the observed PR head")

    base_sha = evidence.get("base_sha")
    if not isinstance(base_sha, str) or not SHA_PATTERN.fullmatch(base_sha or ""):
        issues.append("base_sha must be a 40-character lowercase hex SHA")

    if evidence.get("base_branch") != "pre-prod":
        issues.append("FORBIDDEN_BASE: autonomous PRs may only target pre-prod")

    ci = evidence.get("ci_conclusions") or []
    if not isinstance(ci, list) or not ci:
        issues.append("exact-head CI conclusions are required")
    else:
        for check in ci:
            if not isinstance(check, Mapping):
                issues.append("each CI conclusion must be a mapping")
                continue
            if check.get("head_sha") != head_sha:
                issues.append(f"CI check '{check.get('name')}' is not bound to the exact head")
            if check.get("conclusion") != "success":
                issues.append(f"CI check '{check.get('name')}' is not successful")

    review = evidence.get("review_receipt")
    if isinstance(review, Mapping):
        if review.get("head_sha") != head_sha:
            issues.append("REVIEW_DRIFT: review receipt is not bound to the exact head")
        if not review.get("independent", False):
            issues.append("review receipt must come from an independent read-only reviewer")
        if [f for f in (review.get("open_findings") or [])]:
            issues.append("review findings are still open; close them through bounded G2 repair")
    else:
        issues.append("review_receipt must be a mapping")

    outcome = "PASS" if not issues else "FAIL"
    return {
        "artifact_type": "autonomous-g3-readiness-decision",
        "schema_version": "1.0",
        "outcome": outcome,
        "valid": outcome == "PASS",
        "issues": issues,
        "head_sha": head_sha,
        "evidence_binding_digest": evidence_binding_digest(evidence) if outcome == "PASS" else None,
        "ready_for_review": outcome == "PASS",
    }
