"""Replay-safe evidence quality decision for SCRUM-215.

The node is intentionally data-only. It validates an already captured evidence
package and never calls providers or grants later-gate authority.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, MutableMapping

NODE_ID = "validation_quality.evidence-quality-check"
PASS = "PASS"
BLOCKED = "BLOCKED"

REASON_ORDER = (
    "EVIDENCE_INCOMPLETE",
    "EVIDENCE_MALFORMED",
    "EVIDENCE_PROVENANCE_MISSING",
    "EVIDENCE_PROJECTION_ONLY",
    "EVIDENCE_HEAD_MISMATCH",
    "EVIDENCE_STALE",
    "EVIDENCE_CONTRADICTORY",
    "EVIDENCE_ACCEPTED",
)
REASON_CODES = frozenset(REASON_ORDER)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROJECTION_SOURCES = {"jira", "slack", "notion"}


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(payload.get("task_id", "")).strip(),
        "repository": str(payload.get("repository", "")).strip(),
        "branch": str(payload.get("branch", "")).strip(),
        "base_sha": str(payload.get("base_sha", "")).strip(),
        "head_sha": str(payload.get("head_sha", "")).strip(),
        "scope_hash": str(payload.get("scope_hash", "")).strip(),
        "graph_revision": str(payload.get("graph_revision", "")).strip(),
        "idempotency_key": str(payload.get("idempotency_key", "")).strip(),
        "pr_number": payload.get("pr_number"),
    }


def _ordered(reasons: set[str]) -> list[str]:
    unknown = reasons.difference(REASON_CODES)
    if unknown:
        raise AssertionError(f"reason code escaped closed set: {sorted(unknown)}")
    return [code for code in REASON_ORDER if code in reasons]


def _authority_boundary() -> dict[str, bool]:
    return {
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def check_evidence_quality(
    evidence: Mapping[str, Any],
    *,
    replay_cache: MutableMapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate exact-head delivery evidence and return a stable decision."""

    payload = deepcopy(dict(evidence))
    identity = _identity(payload)
    input_digest = _digest(payload)
    cache_key = identity["idempotency_key"]

    if replay_cache is not None and cache_key and cache_key in replay_cache:
        cached = replay_cache[cache_key]
        if cached.get("input_digest") == input_digest:
            replay = deepcopy(cached)
            replay["replayed"] = True
            return replay
        return {
            "schema_version": "1.0",
            "artifact_type": "evidence-quality-decision",
            "node_id": NODE_ID,
            **identity,
            "status": BLOCKED,
            "reason_codes": ["EVIDENCE_CONTRADICTORY"],
            "input_digest": input_digest,
            "quality_digest": _digest({"identity": identity, "reason_codes": ["EVIDENCE_CONTRADICTORY"]}),
            "replayed": False,
            **_authority_boundary(),
        }

    reasons: set[str] = set()
    required_text = ("task_id", "repository", "branch", "base_sha", "head_sha", "scope_hash", "graph_revision", "idempotency_key")
    if any(not identity[field] for field in required_text) or not isinstance(identity["pr_number"], int):
        reasons.add("EVIDENCE_INCOMPLETE")
    if identity["base_sha"] and not _SHA_RE.fullmatch(identity["base_sha"]):
        reasons.add("EVIDENCE_MALFORMED")
    if identity["head_sha"] and not _SHA_RE.fullmatch(identity["head_sha"]):
        reasons.add("EVIDENCE_MALFORMED")
    if identity["scope_hash"] and not _SCOPE_RE.fullmatch(identity["scope_hash"]):
        reasons.add("EVIDENCE_MALFORMED")

    ci = payload.get("ci_evidence")
    review = payload.get("review_receipt")
    if not isinstance(ci, Mapping) or not isinstance(review, Mapping):
        reasons.add("EVIDENCE_INCOMPLETE")
        ci = ci if isinstance(ci, Mapping) else {}
        review = review if isinstance(review, Mapping) else {}

    ci_status = str(ci.get("status", "")).upper()
    ci_reason = str(ci.get("reason_code", ""))
    if ci_status != PASS or ci_reason != "CI_SUCCESS":
        reasons.add("EVIDENCE_CONTRADICTORY" if ci_status == PASS else "EVIDENCE_INCOMPLETE")

    for field in ("task_id", "repository", "branch", "head_sha", "scope_hash"):
        value = str(ci.get(field, "")).strip()
        if not value:
            reasons.add("EVIDENCE_PROVENANCE_MISSING")
        elif value != str(identity[field]):
            reasons.add("EVIDENCE_HEAD_MISMATCH" if field == "head_sha" else "EVIDENCE_CONTRADICTORY")

    review_required = ("task_id", "repository", "pr_number", "head_sha", "scope_hash", "reviewer_identity", "reviewed_at", "source")
    if any(review.get(field) in (None, "") for field in review_required):
        reasons.add("EVIDENCE_PROVENANCE_MISSING")
    if review.get("schema_valid") is not True or str(review.get("outcome", "")).upper() != PASS:
        reasons.add("EVIDENCE_MALFORMED")
    if str(review.get("access_mode", "")).lower() != "read_only":
        reasons.add("EVIDENCE_CONTRADICTORY")
    if list(review.get("write_actions") or []):
        reasons.add("EVIDENCE_CONTRADICTORY")

    expected_review = {"task_id": identity["task_id"], "repository": identity["repository"], "pr_number": identity["pr_number"], "head_sha": identity["head_sha"], "scope_hash": identity["scope_hash"]}
    for field, expected in expected_review.items():
        actual = review.get(field)
        if actual in (None, ""):
            continue
        if actual != expected:
            reasons.add("EVIDENCE_HEAD_MISMATCH" if field == "head_sha" else "EVIDENCE_CONTRADICTORY")

    findings = list(review.get("findings") or [])
    if any(str(item.get("status", "OPEN")).upper() != "CLOSED" for item in findings if isinstance(item, Mapping)):
        reasons.add("EVIDENCE_CONTRADICTORY")
    if int(review.get("open_findings", 0) or 0) != 0:
        reasons.add("EVIDENCE_CONTRADICTORY")

    source = str(review.get("source", "")).strip().lower()
    evidence_sources = {str(item).strip().lower() for item in payload.get("evidence_sources", []) if str(item).strip()}
    if source in _PROJECTION_SOURCES or (evidence_sources and evidence_sources.issubset(_PROJECTION_SOURCES)):
        reasons.add("EVIDENCE_PROJECTION_ONLY")

    reviewed_at = _parse_time(review.get("reviewed_at"))
    evaluated_at = _parse_time(payload.get("evaluated_at"))
    max_age_seconds = payload.get("max_age_seconds", 86400)
    if reviewed_at is None or evaluated_at is None:
        reasons.add("EVIDENCE_MALFORMED")
    else:
        try:
            max_age = int(max_age_seconds)
        except (TypeError, ValueError):
            max_age = -1
        age = (evaluated_at - reviewed_at).total_seconds()
        if max_age < 0 or age < 0:
            reasons.add("EVIDENCE_MALFORMED")
        elif age > max_age:
            reasons.add("EVIDENCE_STALE")

    terminal_conclusions = {str(value).lower() for value in payload.get("terminal_ci_conclusions", []) if str(value).strip()}
    if len(terminal_conclusions) > 1 or payload.get("conflicting_evidence") is True:
        reasons.add("EVIDENCE_CONTRADICTORY")

    if not reasons:
        reasons.add("EVIDENCE_ACCEPTED")
    reason_codes = _ordered(reasons)
    status = PASS if reason_codes == ["EVIDENCE_ACCEPTED"] else BLOCKED
    quality_basis = {"identity": identity, "status": status, "reason_codes": reason_codes, "ci_evidence_digest": ci.get("evidence_digest"), "review_receipt_digest": review.get("receipt_digest") or _digest(dict(review))}
    result = {
        "schema_version": "1.0",
        "artifact_type": "evidence-quality-decision",
        "node_id": NODE_ID,
        **identity,
        "status": status,
        "reason_codes": reason_codes,
        "input_digest": input_digest,
        "quality_digest": _digest(quality_basis),
        "replayed": False,
        **_authority_boundary(),
    }
    if replay_cache is not None and cache_key:
        replay_cache[cache_key] = deepcopy(result)
    return result


__all__ = ["BLOCKED", "NODE_ID", "PASS", "REASON_CODES", "check_evidence_quality"]
