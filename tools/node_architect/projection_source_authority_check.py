#!/usr/bin/env python3
"""Pure, deterministic source-authority decision for sync_projection outputs."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "projection-source-authority-decision"

SOURCE_TYPES = {"REPOSITORY", "GATE_ARTIFACT", "TASK_RECORD", "PULL_REQUEST", "CI_RUN", "AUDIT_EVENT"}
AUTHORITY_CLASSES = {"CANONICAL", "PROJECTION", "ADVISORY"}
SOURCE_STATUSES = {"VERIFIED", "STALE", "MISSING", "AMBIGUOUS", "CONFLICT"}
DERIVATIONS = {"DIRECT", "DETERMINISTIC_DERIVATION"}
KNOWN_DERIVATION_RULE_IDS = {
    "canonical-boolean-v1",
    "canonical-enum-v1",
    "canonical-json-pointer-v1",
    "canonical-scalar-v1",
    "stable-status-code-v1",
}

REASON_PRECEDENCE = [
    "PROJECTION_SOURCE_INPUT_INVALID",
    "PROJECTION_SOURCE_FIELDS_EMPTY",
    "PROJECTION_SOURCE_CANONICAL_MISSING",
    "PROJECTION_SOURCE_CONFLICT",
    "PROJECTION_SOURCE_AUTHORITY_INVALID",
    "PROJECTION_SOURCE_INFERRED_STATUS_REJECTED",
    "PROJECTION_SOURCE_FIELD_UNBOUND",
    "PROJECTION_SOURCE_DIGEST_MISMATCH",
    "PROJECTION_SOURCE_REVISION_DRIFT",
    "PROJECTION_SOURCE_STALE",
    "PROJECTION_SOURCE_DERIVATION_UNVERIFIED",
    "PROJECTION_SOURCE_AUTHORITY_CONFIRMED",
]

_TASK_RE = re.compile(r"^[A-Z][A-Z0-9]+-[1-9][0-9]*$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TARGET_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[A-Za-z0-9._:/@+\-]{7,200}$")
_FIELD_RE = re.compile(r"^(?:/[A-Za-z0-9_.~\-/]+|[a-z][a-z0-9_.-]{0,255})$")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_field(value: str) -> str:
    if value.startswith("/"):
        parts = value.split("/")
        return "/" + "/".join(part for part in parts[1:] if part != "")
    return value.strip().lower()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(payload: dict[str, Any]) -> str:
    digest_input = {key: value for key, value in payload.items() if key not in {"observed_at", "decision_digest"}}
    return "sha256:" + hashlib.sha256(_canonical_json(digest_input).encode("utf-8")).hexdigest()


def _sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def _primary_reason(reasons: set[str]) -> str:
    for reason in REASON_PRECEDENCE:
        if reason in reasons:
            return reason
    return "PROJECTION_SOURCE_INPUT_INVALID"


def _base_decision(
    *, task_id: str, repository: str, projection_target: str, observed_at: str,
    source_bindings: list[dict[str, Any]], field_authority: list[dict[str, Any]], reasons: set[str]
) -> dict[str, Any]:
    primary = _primary_reason(reasons)
    ready = primary == "PROJECTION_SOURCE_AUTHORITY_CONFIRMED" and reasons == {primary}
    decision: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "task_id": task_id if isinstance(task_id, str) and _TASK_RE.fullmatch(task_id) else "INVALID-1",
        "repository": repository if isinstance(repository, str) and _REPOSITORY_RE.fullmatch(repository) else "invalid/repository",
        "projection_target": projection_target if isinstance(projection_target, str) and _TARGET_RE.fullmatch(projection_target) else "invalid-target",
        "source_bindings": source_bindings,
        "field_authority": field_authority,
        "outcome": "READY" if ready else "BLOCKED",
        "authority_status": "CONFIRMED" if ready else "REJECTED",
        "reason_code": primary,
        "reason_codes": _sorted_unique(reasons),
        "observed_at": observed_at,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }
    decision["decision_digest"] = _digest(decision)
    return decision


def decide_projection_source_authority(
    *,
    task_id: str,
    repository: str,
    projection_target: str,
    requested_fields: list[str],
    source_bindings: list[dict[str, object]],
    field_evidence: list[dict[str, object]],
    current_revisions: list[dict[str, str]],
    freshness_policy: dict[str, int],
    observed_at: str | None = None,
) -> dict[str, object]:
    """Return a schema-valid decision without I/O, mutation, or authority escalation."""

    reasons: set[str] = set()
    normalized_bindings: list[dict[str, Any]] = []
    normalized_fields: list[dict[str, Any]] = []

    # Derive a deterministic evaluation clock when the caller omits one.
    timestamps: list[datetime] = []
    for item in [*source_bindings, *current_revisions]:
        if isinstance(item, dict) and isinstance(item.get("observed_at"), str):
            try:
                timestamps.append(_parse_timestamp(item["observed_at"]))
            except Exception:
                pass
    try:
        evaluation_time = _parse_timestamp(observed_at) if observed_at is not None else max(timestamps)
    except Exception:
        evaluation_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
        reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
    observed_text = _timestamp_text(evaluation_time)

    if not isinstance(task_id, str) or not _TASK_RE.fullmatch(task_id):
        reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
    if not isinstance(repository, str) or not _REPOSITORY_RE.fullmatch(repository):
        reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
    if not isinstance(projection_target, str) or not _TARGET_RE.fullmatch(projection_target):
        reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
    if not isinstance(requested_fields, list) or not isinstance(source_bindings, list) or not isinstance(field_evidence, list):
        reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
        requested_fields = requested_fields if isinstance(requested_fields, list) else []
        source_bindings = source_bindings if isinstance(source_bindings, list) else []
        field_evidence = field_evidence if isinstance(field_evidence, list) else []
    if not isinstance(current_revisions, list) or not isinstance(freshness_policy, dict):
        reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
        current_revisions = current_revisions if isinstance(current_revisions, list) else []
        freshness_policy = freshness_policy if isinstance(freshness_policy, dict) else {}

    normalized_requested: list[str] = []
    for field in requested_fields:
        if not isinstance(field, str) or not _FIELD_RE.fullmatch(field):
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        normalized_requested.append(_normalize_field(field))
    normalized_requested = sorted(set(normalized_requested))
    if not normalized_requested:
        reasons.add("PROJECTION_SOURCE_FIELDS_EMPTY")

    max_source_age = freshness_policy.get("max_source_age_seconds")
    max_readback_age = freshness_policy.get("max_readback_age_seconds")
    if (
        set(freshness_policy) != {"max_source_age_seconds", "max_readback_age_seconds"}
        or not isinstance(max_source_age, int) or isinstance(max_source_age, bool) or max_source_age < 0
        or not isinstance(max_readback_age, int) or isinstance(max_readback_age, bool) or max_readback_age < 0
    ):
        reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
        max_source_age = 0
        max_readback_age = 0

    binding_by_ref: dict[str, dict[str, Any]] = {}
    duplicate_refs: set[str] = set()
    for raw in source_bindings:
        if not isinstance(raw, dict):
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        required = {"source_type", "authority_class", "ref", "revision", "content_digest", "observed_at", "status"}
        if set(raw) != required:
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        source_type = raw.get("source_type")
        authority_class = raw.get("authority_class")
        ref = raw.get("ref")
        revision = raw.get("revision")
        content_digest = raw.get("content_digest")
        status = raw.get("status")
        try:
            source_time = _parse_timestamp(raw.get("observed_at"))
        except Exception:
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        if (
            source_type not in SOURCE_TYPES or authority_class not in AUTHORITY_CLASSES or status not in SOURCE_STATUSES
            or not isinstance(ref, str) or not ref or len(ref) > 512
            or not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision)
            or not isinstance(content_digest, str) or not _DIGEST_RE.fullmatch(content_digest)
            or source_time > evaluation_time
        ):
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        normalized = {
            "source_type": source_type,
            "authority_class": authority_class,
            "ref": ref,
            "revision": revision,
            "content_digest": content_digest,
            "observed_at": _timestamp_text(source_time),
            "status": status,
        }
        normalized_bindings.append(normalized)
        if ref in binding_by_ref and binding_by_ref[ref] != normalized:
            duplicate_refs.add(ref)
        binding_by_ref[ref] = normalized
        if status in {"AMBIGUOUS", "CONFLICT"}:
            reasons.add("PROJECTION_SOURCE_CONFLICT")
        if status == "MISSING":
            reasons.add("PROJECTION_SOURCE_CANONICAL_MISSING" if authority_class == "CANONICAL" else "PROJECTION_SOURCE_AUTHORITY_INVALID")
        if status == "STALE" or (evaluation_time - source_time).total_seconds() > max_source_age:
            reasons.add("PROJECTION_SOURCE_STALE")
    if duplicate_refs:
        reasons.add("PROJECTION_SOURCE_CONFLICT")

    normalized_bindings.sort(key=lambda item: (
        item["ref"], item["revision"], item["source_type"], item["authority_class"], item["content_digest"]
    ))
    canonical_bindings = [item for item in normalized_bindings if item["authority_class"] == "CANONICAL"]
    if not canonical_bindings:
        reasons.add("PROJECTION_SOURCE_CANONICAL_MISSING")

    current_by_ref: dict[str, dict[str, Any]] = {}
    for raw in current_revisions:
        if not isinstance(raw, dict) or set(raw) != {"ref", "revision", "observed_at"}:
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        ref, revision = raw.get("ref"), raw.get("revision")
        try:
            readback_time = _parse_timestamp(raw.get("observed_at"))
        except Exception:
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        if (
            not isinstance(ref, str) or not ref
            or not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision)
            or readback_time > evaluation_time
        ):
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        normalized = {"ref": ref, "revision": revision, "observed_at": _timestamp_text(readback_time)}
        if ref in current_by_ref and current_by_ref[ref] != normalized:
            reasons.add("PROJECTION_SOURCE_CONFLICT")
        current_by_ref[ref] = normalized
        if (evaluation_time - readback_time).total_seconds() > max_readback_age:
            reasons.add("PROJECTION_SOURCE_STALE")

    evidence_by_field: dict[str, list[dict[str, Any]]] = {}
    inference_detected = False
    for raw in field_evidence:
        if not isinstance(raw, dict):
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        allowed = {"field_path", "source_ref", "source_revision", "evidence_digest", "derivation", "derivation_rule_id"}
        required = {"field_path", "source_ref", "source_revision", "evidence_digest", "derivation"}
        if not required.issubset(raw) or set(raw) - allowed:
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        derivation = raw.get("derivation")
        if isinstance(derivation, str) and derivation.upper() in {"INFERRED", "INFERENCE", "PROBABILISTIC"}:
            inference_detected = True
            continue
        field_path = raw.get("field_path")
        source_ref = raw.get("source_ref")
        source_revision = raw.get("source_revision")
        evidence_digest = raw.get("evidence_digest")
        rule_id = raw.get("derivation_rule_id")
        if (
            not isinstance(field_path, str) or not _FIELD_RE.fullmatch(field_path)
            or not isinstance(source_ref, str) or not source_ref
            or not isinstance(source_revision, str) or not _REVISION_RE.fullmatch(source_revision)
            or not isinstance(evidence_digest, str) or not _DIGEST_RE.fullmatch(evidence_digest)
            or derivation not in DERIVATIONS
            or (rule_id is not None and (not isinstance(rule_id, str) or not rule_id))
        ):
            reasons.add("PROJECTION_SOURCE_INPUT_INVALID")
            continue
        normalized_field = {
            "field_path": _normalize_field(field_path),
            "source_ref": source_ref,
            "source_revision": source_revision,
            "evidence_digest": evidence_digest,
            "derivation": derivation,
        }
        if rule_id is not None:
            normalized_field["derivation_rule_id"] = rule_id
        evidence_by_field.setdefault(normalized_field["field_path"], []).append(normalized_field)

    if inference_detected:
        reasons.add("PROJECTION_SOURCE_INFERRED_STATUS_REJECTED")

    for field_path in normalized_requested:
        candidates = evidence_by_field.get(field_path, [])
        if not candidates:
            reasons.add("PROJECTION_SOURCE_FIELD_UNBOUND")
            continue
        canonical_candidates: list[dict[str, Any]] = []
        for candidate in candidates:
            binding = binding_by_ref.get(candidate["source_ref"])
            if binding is None:
                reasons.add("PROJECTION_SOURCE_FIELD_UNBOUND")
                continue
            if binding["authority_class"] != "CANONICAL":
                reasons.add("PROJECTION_SOURCE_AUTHORITY_INVALID")
                continue
            canonical_candidates.append(candidate)
            if candidate["source_revision"] != binding["revision"] or candidate["evidence_digest"] != binding["content_digest"]:
                reasons.add("PROJECTION_SOURCE_DIGEST_MISMATCH")
            current = current_by_ref.get(binding["ref"])
            if current is None or current["revision"] != binding["revision"]:
                reasons.add("PROJECTION_SOURCE_REVISION_DRIFT")
            if candidate["derivation"] == "DETERMINISTIC_DERIVATION" and candidate.get("derivation_rule_id") not in KNOWN_DERIVATION_RULE_IDS:
                reasons.add("PROJECTION_SOURCE_DERIVATION_UNVERIFIED")
        if not canonical_candidates:
            reasons.add("PROJECTION_SOURCE_AUTHORITY_INVALID")
        elif len({(c["source_ref"], c["source_revision"], c["evidence_digest"], c["derivation"], c.get("derivation_rule_id")) for c in canonical_candidates}) > 1:
            reasons.add("PROJECTION_SOURCE_CONFLICT")
        normalized_fields.extend(canonical_candidates)

    normalized_fields = sorted(
        {_canonical_json(item): item for item in normalized_fields}.values(),
        key=lambda item: (item["field_path"], item["source_ref"], item["source_revision"], item["evidence_digest"]),
    )

    if not reasons:
        reasons.add("PROJECTION_SOURCE_AUTHORITY_CONFIRMED")

    return _base_decision(
        task_id=task_id,
        repository=repository,
        projection_target=projection_target,
        observed_at=observed_text,
        source_bindings=normalized_bindings,
        field_authority=normalized_fields,
        reasons=reasons,
    )
