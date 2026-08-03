#!/usr/bin/env python3
"""Pure deterministic projection evidence-link canonicalizer for SCRUM-227."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "projection-evidence-linkset"
SOURCE_TYPES = {"REPOSITORY", "GATE_ARTIFACT", "TASK_RECORD", "PULL_REQUEST", "CI_RUN", "AUDIT_EVENT"}
RELATIONS = {"SUPPORTS_FIELD", "DERIVED_FROM", "VALIDATED_BY", "READBACK_OF", "SUPERSEDES"}
VERIFICATION_STATUSES = {"VERIFIED", "STALE", "BROKEN", "UNVERIFIED", "CONFLICT"}
COVERAGE_RELATIONS = {"SUPPORTS_FIELD", "DERIVED_FROM"}

SOURCE_AUTHORITY_FIELDS = {
    "schema_version", "artifact_type", "task_id", "repository", "projection_target",
    "source_bindings", "field_authority", "outcome", "authority_status", "reason_code",
    "reason_codes", "observed_at", "read_only_projection", "write_authority_granted",
    "approval_authority_granted", "merge_authority_granted",
    "deployment_authority_granted", "production_authority_granted", "decision_digest",
}
SOURCE_BINDING_FIELDS = {
    "source_type", "authority_class", "ref", "revision", "content_digest", "observed_at", "status",
}
FIELD_AUTHORITY_REQUIRED = {"field_path", "source_ref", "source_revision", "evidence_digest", "derivation"}
FIELD_AUTHORITY_ALLOWED = FIELD_AUTHORITY_REQUIRED | {"derivation_rule_id"}
AUTHORITY_CLASSES = {"CANONICAL", "PROJECTION", "ADVISORY"}
SOURCE_STATUSES = {"VERIFIED", "STALE", "MISSING", "AMBIGUOUS", "CONFLICT"}
DERIVATIONS = {"DIRECT", "DETERMINISTIC_DERIVATION"}
REASON_PRECEDENCE = [
    "EVIDENCE_LINK_INPUT_INVALID",
    "EVIDENCE_LINK_SOURCE_AUTHORITY_INVALID",
    "EVIDENCE_LINK_REQUIRED_MISSING",
    "EVIDENCE_LINK_IMMUTABLE_REF_MISSING",
    "EVIDENCE_LINK_CONTRACT_INVALID",
    "EVIDENCE_LINK_BROKEN",
    "EVIDENCE_LINK_UNVERIFIED",
    "EVIDENCE_LINK_STALE",
    "EVIDENCE_LINK_DIGEST_CONFLICT",
    "EVIDENCE_LINK_FIELD_UNBOUND",
    "EVIDENCE_LINK_DIGEST_MISMATCH",
    "EVIDENCE_LINK_URL_NOT_AUTHORITY",
    "EVIDENCE_LINKSET_READY",
]

_TASK_RE = re.compile(r"^[A-Z][A-Z0-9]+-[1-9][0-9]*$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TARGET_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[A-Za-z0-9._:/@+\-]{1,200}$")
_FIELD_RE = re.compile(r"^(?:/[A-Za-z0-9_.~\-/]+|[a-z][a-z0-9_.-]{0,255})$")
_ZERO_DIGEST = "sha256:" + "0" * 64


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_field(value: str) -> str:
    if value.startswith("/"):
        return "/" + "/".join(part for part in value.split("/")[1:] if part)
    return value.strip().lower()


def _timestamp(value: object) -> str:
    if value is None:
        return "1970-01-01T00:00:00Z"
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _primary(reasons: set[str]) -> str:
    for code in REASON_PRECEDENCE:
        if code in reasons:
            return code
    return "EVIDENCE_LINK_INPUT_INVALID"


def _source_authority_digest(decision: dict[str, object]) -> str:
    semantic = {
        key: value
        for key, value in decision.items()
        if key not in {"observed_at", "decision_digest"}
    }
    return _hash(semantic)


def _authority_is_valid(
    decision: object, task_id: str, repository: str, projection_target: str
) -> tuple[bool, str, set[tuple[str, str, str]], set[tuple[str, str, str, str]]]:
    if not isinstance(decision, dict) or set(decision) != SOURCE_AUTHORITY_FIELDS:
        return False, _ZERO_DIGEST, set(), set()

    digest = decision.get("decision_digest")
    try:
        _timestamp(decision.get("observed_at"))
        digest_matches = (
            isinstance(digest, str)
            and bool(_DIGEST_RE.fullmatch(digest))
            and digest == _source_authority_digest(decision)
        )
    except Exception:
        digest_matches = False

    valid = (
        decision.get("schema_version") == "1.0"
        and decision.get("artifact_type") == "projection-source-authority-decision"
        and decision.get("task_id") == task_id
        and decision.get("repository") == repository
        and decision.get("projection_target") == projection_target
        and decision.get("outcome") == "READY"
        and decision.get("authority_status") == "CONFIRMED"
        and decision.get("reason_code") == "PROJECTION_SOURCE_AUTHORITY_CONFIRMED"
        and decision.get("reason_codes") == ["PROJECTION_SOURCE_AUTHORITY_CONFIRMED"]
        and digest_matches
        and decision.get("read_only_projection") is True
        and all(decision.get(key) is False for key in (
            "write_authority_granted", "approval_authority_granted", "merge_authority_granted",
            "deployment_authority_granted", "production_authority_granted"
        ))
        and isinstance(decision.get("source_bindings"), list)
        and isinstance(decision.get("field_authority"), list)
    )

    canonical: set[tuple[str, str, str]] = set()
    authorized_fields: set[tuple[str, str, str, str]] = set()
    if valid:
        for item in decision["source_bindings"]:
            if not isinstance(item, dict) or set(item) != SOURCE_BINDING_FIELDS:
                valid = False
                break
            ref = item.get("ref")
            revision = item.get("revision")
            content_digest = item.get("content_digest")
            try:
                _timestamp(item.get("observed_at"))
            except Exception:
                valid = False
                break
            if (
                item.get("source_type") not in SOURCE_TYPES
                or item.get("authority_class") not in AUTHORITY_CLASSES
                or item.get("status") not in SOURCE_STATUSES
                or not isinstance(ref, str) or not ref or len(ref) > 512
                or not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision)
                or not isinstance(content_digest, str) or not _DIGEST_RE.fullmatch(content_digest)
            ):
                valid = False
                break
            if item.get("authority_class") == "CANONICAL" and item.get("status") == "VERIFIED":
                canonical.add((ref, revision, content_digest))
        if not canonical:
            valid = False

    if valid:
        for item in decision["field_authority"]:
            if (
                not isinstance(item, dict)
                or not FIELD_AUTHORITY_REQUIRED.issubset(item)
                or set(item) - FIELD_AUTHORITY_ALLOWED
            ):
                valid = False
                break
            field_path = item.get("field_path")
            ref = item.get("source_ref")
            revision = item.get("source_revision")
            evidence_digest = item.get("evidence_digest")
            derivation = item.get("derivation")
            rule_id = item.get("derivation_rule_id")
            if (
                not isinstance(field_path, str) or not _FIELD_RE.fullmatch(field_path)
                or not isinstance(ref, str) or not ref
                or not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision)
                or not isinstance(evidence_digest, str) or not _DIGEST_RE.fullmatch(evidence_digest)
                or derivation not in DERIVATIONS
                or (rule_id is not None and (not isinstance(rule_id, str) or not rule_id))
                or (derivation == "DETERMINISTIC_DERIVATION" and not isinstance(rule_id, str))
                or (ref, revision, evidence_digest) not in canonical
            ):
                valid = False
                break
            authorized_fields.add((_normalize_field(field_path), ref, revision, evidence_digest))
        if not authorized_fields:
            valid = False

    return (
        valid,
        digest if isinstance(digest, str) and _DIGEST_RE.fullmatch(digest) else _ZERO_DIGEST,
        canonical,
        authorized_fields,
    )


def _linkset_payload(*, task_id: str, repository: str, projection_target: str, source_authority_digest: str,
                     links: list[dict[str, Any]], covered_fields: list[str], uncovered_fields: list[str]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "task_id": task_id,
        "repository": repository,
        "projection_target": projection_target,
        "source_authority_digest": source_authority_digest,
        "links": links,
        "covered_fields": covered_fields,
        "uncovered_fields": uncovered_fields,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _linkset_digest(payload: dict[str, Any]) -> str:
    semantic = dict(payload)
    semantic["links"] = [
        {key: value for key, value in link.items() if key != "display_url"}
        for link in payload["links"]
    ]
    return _hash(semantic)


def build_projection_evidence_linkset(
    *,
    task_id: str,
    repository: str,
    projection_target: str,
    source_authority_decision: dict[str, object],
    evidence_items: list[dict[str, object]],
    projected_fields: list[str],
    expected_linkset_digest: str | None = None,
    linked_at: str | None = None,
) -> dict[str, object]:
    """Return a schema-valid, read-only evidence linkset without I/O or mutation."""

    reasons: set[str] = set()
    safe_task_id = task_id if isinstance(task_id, str) and _TASK_RE.fullmatch(task_id) else "INVALID-1"
    safe_repository = repository if isinstance(repository, str) and _REPOSITORY_RE.fullmatch(repository) else "invalid/repository"
    safe_target = projection_target if isinstance(projection_target, str) and _TARGET_RE.fullmatch(projection_target) else "invalid-target"
    if safe_task_id != task_id or safe_repository != repository or safe_target != projection_target:
        reasons.add("EVIDENCE_LINK_INPUT_INVALID")

    try:
        linked_at_text = _timestamp(linked_at)
    except Exception:
        linked_at_text = "1970-01-01T00:00:00Z"
        reasons.add("EVIDENCE_LINK_INPUT_INVALID")

    if not isinstance(projected_fields, list) or not isinstance(evidence_items, list):
        reasons.add("EVIDENCE_LINK_INPUT_INVALID")
        projected_fields = projected_fields if isinstance(projected_fields, list) else []
        evidence_items = evidence_items if isinstance(evidence_items, list) else []

    normalized_fields: list[str] = []
    for field in projected_fields:
        if not isinstance(field, str) or not _FIELD_RE.fullmatch(field):
            reasons.add("EVIDENCE_LINK_CONTRACT_INVALID")
            continue
        normalized_fields.append(_normalize_field(field))
    normalized_fields = sorted(set(normalized_fields))
    if not normalized_fields or not evidence_items:
        reasons.add("EVIDENCE_LINK_REQUIRED_MISSING")

    authority_valid, authority_digest, canonical_sources, authorized_fields = _authority_is_valid(
        source_authority_decision, task_id, repository, projection_target
    )
    if not authority_valid:
        reasons.add("EVIDENCE_LINK_SOURCE_AUTHORITY_INVALID")

    by_semantic: dict[str, dict[str, Any]] = {}
    digest_by_identity: dict[tuple[str, str, str, str], str] = {}

    for raw in evidence_items:
        if not isinstance(raw, dict):
            reasons.add("EVIDENCE_LINK_INPUT_INVALID")
            continue
        allowed = {
            "evidence_id", "source_type", "ref", "revision", "content_digest", "relation",
            "field_paths", "display_url", "verification_status", "supersedes_revision"
        }
        if set(raw) - allowed:
            reasons.add("EVIDENCE_LINK_CONTRACT_INVALID")

        evidence_id = raw.get("evidence_id")
        source_type = raw.get("source_type")
        ref = raw.get("ref")
        revision = raw.get("revision")
        content_digest = raw.get("content_digest")
        relation = raw.get("relation")
        field_paths = raw.get("field_paths")
        display_url = raw.get("display_url")
        verification_status = raw.get("verification_status")
        supersedes_revision = raw.get("supersedes_revision")

        missing_immutable = not (
            isinstance(ref, str) and ref and isinstance(revision, str) and _REVISION_RE.fullmatch(revision)
            and isinstance(content_digest, str) and _DIGEST_RE.fullmatch(content_digest)
        )
        if missing_immutable:
            reasons.add("EVIDENCE_LINK_IMMUTABLE_REF_MISSING")
            if isinstance(display_url, str) and display_url:
                reasons.add("EVIDENCE_LINK_URL_NOT_AUTHORITY")
            continue

        if (
            not isinstance(evidence_id, str) or not evidence_id or len(evidence_id) > 200
            or source_type not in SOURCE_TYPES or relation not in RELATIONS
            or verification_status not in VERIFICATION_STATUSES
            or not isinstance(field_paths, list)
            or (display_url is not None and (not isinstance(display_url, str) or not re.match(r"^https?://", display_url)))
        ):
            reasons.add("EVIDENCE_LINK_CONTRACT_INVALID")
            continue

        normalized_paths: list[str] = []
        for field in field_paths:
            if not isinstance(field, str) or not _FIELD_RE.fullmatch(field):
                reasons.add("EVIDENCE_LINK_CONTRACT_INVALID")
                continue
            normalized_paths.append(_normalize_field(field))
        normalized_paths = sorted(set(normalized_paths))

        if relation == "SUPERSEDES":
            if not isinstance(supersedes_revision, str) or not _REVISION_RE.fullmatch(supersedes_revision) or supersedes_revision == revision:
                reasons.add("EVIDENCE_LINK_CONTRACT_INVALID")
                continue
        elif supersedes_revision is not None:
            reasons.add("EVIDENCE_LINK_CONTRACT_INVALID")
            continue

        if verification_status == "BROKEN":
            reasons.add("EVIDENCE_LINK_BROKEN")
        elif verification_status == "UNVERIFIED":
            reasons.add("EVIDENCE_LINK_UNVERIFIED")
        elif verification_status == "STALE":
            reasons.add("EVIDENCE_LINK_STALE")
        elif verification_status == "CONFLICT":
            reasons.add("EVIDENCE_LINK_DIGEST_CONFLICT")

        link: dict[str, Any] = {
            "evidence_id": evidence_id,
            "source_type": source_type,
            "ref": ref,
            "revision": revision,
            "content_digest": content_digest,
            "relation": relation,
            "field_paths": normalized_paths,
            "verification_status": verification_status,
        }
        if isinstance(display_url, str) and display_url:
            link["display_url"] = display_url
        if relation == "SUPERSEDES":
            link["supersedes_revision"] = supersedes_revision

        identity = (evidence_id, source_type, ref, revision)
        prior_digest = digest_by_identity.get(identity)
        if prior_digest is not None and prior_digest != content_digest:
            reasons.add("EVIDENCE_LINK_DIGEST_CONFLICT")
        digest_by_identity[identity] = content_digest

        semantic = {key: value for key, value in link.items() if key != "display_url"}
        semantic_key = _canonical_json(semantic)
        if semantic_key in by_semantic:
            urls = [value for value in (by_semantic[semantic_key].get("display_url"), link.get("display_url")) if value]
            if urls:
                by_semantic[semantic_key]["display_url"] = min(urls)
        else:
            by_semantic[semantic_key] = link

    normalized_links = sorted(by_semantic.values(), key=lambda item: (
        item["source_type"], item["ref"], item["revision"], item["relation"], item["evidence_id"], item["content_digest"]
    ))

    covered: set[str] = set()
    if authority_valid:
        for link in normalized_links:
            if (
                link["verification_status"] == "VERIFIED"
                and link["relation"] in COVERAGE_RELATIONS
                and (link["ref"], link["revision"], link["content_digest"]) in canonical_sources
            ):
                covered.update(
                    path
                    for path in link["field_paths"]
                    if path in normalized_fields
                    and (path, link["ref"], link["revision"], link["content_digest"]) in authorized_fields
                )
    uncovered = sorted(set(normalized_fields) - covered)
    covered_fields = sorted(covered)
    if uncovered:
        reasons.add("EVIDENCE_LINK_FIELD_UNBOUND")

    output_payload = _linkset_payload(
        task_id=safe_task_id,
        repository=safe_repository,
        projection_target=safe_target,
        source_authority_digest=authority_digest,
        links=normalized_links,
        covered_fields=covered_fields,
        uncovered_fields=uncovered,
    )
    linkset_digest = _linkset_digest(output_payload)
    if expected_linkset_digest is not None:
        if not isinstance(expected_linkset_digest, str) or not _DIGEST_RE.fullmatch(expected_linkset_digest):
            reasons.add("EVIDENCE_LINK_INPUT_INVALID")
        elif expected_linkset_digest != linkset_digest:
            reasons.add("EVIDENCE_LINK_DIGEST_MISMATCH")

    if not reasons:
        reasons.add("EVIDENCE_LINKSET_READY")
    primary = _primary(reasons)
    ready = reasons == {"EVIDENCE_LINKSET_READY"}
    return {
        **output_payload,
        "link_status": "VERIFIED" if ready else "BLOCKED",
        "outcome": "READY" if ready else "BLOCKED",
        "reason_code": primary,
        "reason_codes": sorted(reasons),
        "linked_at": linked_at_text,
        "linkset_digest": linkset_digest,
    }
