#!/usr/bin/env python3
"""Pure deterministic external audit event projection renderer for SCRUM-222.

The renderer consumes a stable B1 source-authority decision, a B1 evidence
linkset, a B1 privacy-boundary decision and a closed sync-projection envelope,
then renders an approved, read-only external audit-event projection. It performs
no connector call, network request, filesystem mutation, Jira transition, branch
creation, commit, PR action, approval generation, merge, deployment or
production operation.

All runtime functions are pure decision/rendering functions. They never grant
write/approval/merge/deploy/production authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "external-audit-event-projection"

REASON_PRECEDENCE = [
    "EXTERNAL_AUDIT_INPUT_INVALID",
    "EXTERNAL_AUDIT_SOURCE_AUTHORITY_INVALID",
    "EXTERNAL_AUDIT_EVIDENCE_LINKSET_INVALID",
    "EXTERNAL_AUDIT_PRIVACY_BOUNDARY_INVALID",
    "EXTERNAL_AUDIT_PRIOR_BINDING_MISMATCH",
    "EXTERNAL_AUDIT_PRIOR_READBACK_MISMATCH",
    "EVENT_SOURCE_BINDING_CONFLICT",
    "EXTERNAL_AUDIT_EVENT_READY",
    "EXTERNAL_AUDIT_EVENT_CURRENT",
]

_TASK_RE = re.compile(r"^[A-Z][A-Z0-9]+-[1-9][0-9]*$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TARGET_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ZERO_DIGEST = "sha256:" + "0" * 64

# SCRUM-533 v3.1 (NA81-F6-N03 successor) canonical event-source format:
#   gwc.{system}.{projection_target}.v{schema_version}
# Concrete first implementation: gwc.node-architect.external-audit-projection.v1.0
# Optional key (backward compatible): when absent the projection renders exactly
# as before; when present it is validated and participates in the canonical digest.
_EVENT_SOURCE_RE = re.compile(r"^gwc\.[a-z0-9]+(?:[.-][a-z0-9]+)*\.v[0-9]+\.[0-9]+$")

ALLOWED_CANONICAL_KEYS = {
    "event_id", "event_type", "task_id", "repository", "repository_head",
    "projection_target", "gate", "gate_outcome", "evidence_linkset_digest",
    "source_authority_digest", "privacy_boundary_digest", "projected_at",
    "event_source",
}
IDEMPOTENT_KEYS = {
    "event_id", "task_id", "repository_head", "gate", "gate_outcome",
    "source_authority_digest", "evidence_linkset_digest", "privacy_boundary_digest",
    "event_source",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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
    return "EXTERNAL_AUDIT_INPUT_INVALID"


def _source_authority_is_valid(decision: dict[str, Any], task_id: str, repository: str, projection_target: str) -> bool:
    if not isinstance(decision, dict):
        return False
    required = {
        "schema_version", "artifact_type", "task_id", "repository", "projection_target",
        "source_bindings", "field_authority", "outcome", "authority_status", "reason_code",
        "reason_codes", "observed_at", "decision_digest", "read_only_projection",
        "write_authority_granted", "approval_authority_granted", "merge_authority_granted",
        "deployment_authority_granted", "production_authority_granted",
    }
    if set(decision) != required:
        return False
    digest = decision.get("decision_digest")

    def _semantic() -> str:
        semantic = {k: v for k, v in decision.items() if k not in {"reason_codes", "decision_digest"}}
        return _digest(semantic)

    try:
        digest_matches = (
            isinstance(digest, str) and bool(_DIGEST_RE.fullmatch(digest)) and digest == _semantic()
        )
    except Exception:
        digest_matches = False

    return bool(
        decision.get("schema_version") == "1.0"
        and decision.get("artifact_type") == "projection-source-authority-decision"
        and decision.get("task_id") == task_id
        and decision.get("repository") == repository
        and decision.get("projection_target") == projection_target
        and decision.get("outcome") == "READY"
        and decision.get("authority_status") == "CONFIRMED"
        and decision.get("reason_code") == "PROJECTION_SOURCE_AUTHORITY_CONFIRMED"
        and digest_matches
        and decision.get("read_only_projection") is True
        and all(decision.get(key) is False for key in (
            "write_authority_granted", "approval_authority_granted",
            "merge_authority_granted", "deployment_authority_granted", "production_authority_granted",
        ))
    )


def _evidence_linkset_is_valid(linkset: dict[str, Any], task_id: str, repository: str, projection_target: str) -> bool:
    if not isinstance(linkset, dict):
        return False
    return bool(
        linkset.get("schema_version") == "1.0"
        and linkset.get("artifact_type") == "projection-evidence-linkset"
        and linkset.get("task_id") == task_id
        and linkset.get("repository") == repository
        and linkset.get("projection_target") == projection_target
        and linkset.get("outcome") == "READY"
        and linkset.get("reason_code") == "EVIDENCE_LINKSET_READY"
        and isinstance(linkset.get("linkset_digest"), str) and bool(_DIGEST_RE.fullmatch(linkset["linkset_digest"]))
        and linkset.get("read_only_projection") is True
        and all(linkset.get(key) is False for key in (
            "write_authority_granted", "approval_authority_granted",
            "merge_authority_granted", "deployment_authority_granted", "production_authority_granted",
        ))
    )


def _privacy_boundary_is_valid(decision: dict[str, Any], task_id: str, repository: str, projection_target: str) -> bool:
    if not isinstance(decision, dict):
        return False
    return bool(
        decision.get("schema_version") == "1.0"
        and decision.get("artifact_type") == "projection-privacy-decision"
        and decision.get("task_id") == task_id
        and decision.get("repository") == repository
        and decision.get("projection_target") == projection_target
        and decision.get("outcome") == "READY"
        and decision.get("reason_code") in ("PRIVACY_APPROVED", "PRIVACY_APPROVED_REDACTED")
        and isinstance(decision.get("decision_digest"), str) and bool(_DIGEST_RE.fullmatch(decision["decision_digest"]))
        and decision.get("read_only_projection") is True
        and all(decision.get(key) is False for key in (
            "write_authority_granted", "approval_authority_granted",
            "merge_authority_granted", "deployment_authority_granted", "production_authority_granted",
        ))
    )


def _canonical_state_digest(state: dict[str, Any]) -> str:
    return _digest(state)


def project_external_audit_event(
    *,
    task_id: str,
    repository: str,
    projection_target: str,
    source_authority_decision: dict[str, Any],
    evidence_linkset: dict[str, Any],
    privacy_boundary_decision: dict[str, Any],
    envelope: dict[str, Any],
    prior_projection: dict[str, Any] | None = None,
    projected_at: str | None = None,
) -> dict[str, object]:
    """Return a schema-valid, read-only external audit event projection without I/O or mutation."""

    reasons: set[str] = set()
    safe_task_id = task_id if isinstance(task_id, str) and _TASK_RE.fullmatch(task_id) else "INVALID-1"
    safe_repository = repository if isinstance(repository, str) and _REPOSITORY_RE.fullmatch(repository) else "invalid/repository"
    safe_target = projection_target if isinstance(projection_target, str) and _TARGET_RE.fullmatch(projection_target) else "invalid-target"
    if safe_task_id != task_id or safe_repository != repository or safe_target != projection_target:
        reasons.add("EXTERNAL_AUDIT_INPUT_INVALID")

    try:
        projected_at_text = _timestamp(projected_at)
    except Exception:
        projected_at_text = "1970-01-01T00:00:00Z"
        reasons.add("EXTERNAL_AUDIT_INPUT_INVALID")

    if not isinstance(envelope, dict):
        reasons.add("EXTERNAL_AUDIT_INPUT_INVALID")
        envelope = {}
    if not isinstance(prior_projection, (dict, type(None))):
        reasons.add("EXTERNAL_AUDIT_INPUT_INVALID")

    authority_ok = _source_authority_is_valid(source_authority_decision, safe_task_id, safe_repository, safe_target)
    if not authority_ok:
        reasons.add("EXTERNAL_AUDIT_SOURCE_AUTHORITY_INVALID")
    linkset_ok = _evidence_linkset_is_valid(evidence_linkset, safe_task_id, safe_repository, safe_target)
    if not linkset_ok:
        reasons.add("EXTERNAL_AUDIT_EVIDENCE_LINKSET_INVALID")
    privacy_ok = _privacy_boundary_is_valid(privacy_boundary_decision, safe_task_id, safe_repository, safe_target)
    if not privacy_ok:
        reasons.add("EXTERNAL_AUDIT_PRIVACY_BOUNDARY_INVALID")

    envelope_digest = envelope.get("source_authority_digest") if isinstance(envelope, dict) else None
    linkset_digest = evidence_linkset.get("linkset_digest") if isinstance(evidence_linkset, dict) else None
    privacy_digest = privacy_boundary_decision.get("decision_digest") if isinstance(privacy_boundary_decision, dict) else None
    authority_digest: str | None = None

    if not reasons:
        authority_digest = source_authority_decision.get("decision_digest") if isinstance(source_authority_decision, dict) else None
        if isinstance(authority_digest, str) and _DIGEST_RE.fullmatch(authority_digest):
            if envelope_digest != authority_digest:
                reasons.add("EXTERNAL_AUDIT_SOURCE_AUTHORITY_INVALID")
        else:
            reasons.add("EXTERNAL_AUDIT_SOURCE_AUTHORITY_INVALID")
        if isinstance(linkset_digest, str) and _DIGEST_RE.fullmatch(linkset_digest):
            if envelope.get("evidence_linkset_digest") != linkset_digest:
                reasons.add("EXTERNAL_AUDIT_EVIDENCE_LINKSET_INVALID")
        else:
            reasons.add("EXTERNAL_AUDIT_EVIDENCE_LINKSET_INVALID")
        if isinstance(privacy_digest, str) and _DIGEST_RE.fullmatch(privacy_digest):
            if envelope.get("privacy_boundary_digest") != privacy_digest:
                reasons.add("EXTERNAL_AUDIT_PRIVACY_BOUNDARY_INVALID")
        else:
            reasons.add("EXTERNAL_AUDIT_PRIVACY_BOUNDARY_INVALID")

    canonical_state: dict[str, Any] = {}
    if isinstance(envelope, dict) and isinstance(envelope.get("canonical_state"), dict):
        for key, value in envelope["canonical_state"].items():
            if key not in ALLOWED_CANONICAL_KEYS:
                reasons.add("EXTERNAL_AUDIT_INPUT_INVALID")
                continue
            canonical_state[key] = value
    else:
        reasons.add("EXTERNAL_AUDIT_INPUT_INVALID")

    # SCRUM-533 v3.1 (NA81-F6-N03 successor): event_source binding validation.
    # Fail closed on (a) format violation, (b) caller-supplied inconsistency
    # with the projection's own system/target/schema-version, or (c) a read-back
    # whose bound event_source differs from the current one. Absent event_source
    # is legacy-compatible and renders exactly as before.
    supplied_source = canonical_state.get("event_source")
    if supplied_source is not None:
        if not isinstance(supplied_source, str) or not _EVENT_SOURCE_RE.fullmatch(supplied_source):
            reasons.add("EVENT_SOURCE_BINDING_CONFLICT")
        else:
            # Derive the expected namespace from the projection's own identity.
            # system := the emitting system (node-architect for this parent),
            # target := projection_target, version := SCHEMA_VERSION. The first
            # implementation binds gwc.node-architect.{projection_target}.v{SCHEMA_VERSION}.
            expected = f"gwc.node-architect.{safe_target}.v{SCHEMA_VERSION}"
            if supplied_source != expected:
                reasons.add("EVENT_SOURCE_BINDING_CONFLICT")

    prior_binding_mismatch = False
    prior_readback_mismatch = False
    if isinstance(prior_projection, dict) and not reasons:
        prior_task = prior_projection.get("task_id")
        prior_repo = prior_projection.get("repository")
        prior_target = prior_projection.get("projection_target")
        if prior_task != safe_task_id or prior_repo != safe_repository or prior_target != safe_target:
            prior_binding_mismatch = True
        else:
            prior_state = prior_projection.get("canonical_state") if isinstance(prior_projection.get("canonical_state"), dict) else prior_projection
            for key in IDEMPOTENT_KEYS:
                if prior_state.get(key) != canonical_state.get(key):
                    prior_readback_mismatch = True
                    break
    if prior_binding_mismatch:
        reasons.add("EXTERNAL_AUDIT_PRIOR_BINDING_MISMATCH")
    elif prior_readback_mismatch:
        reasons.add("EXTERNAL_AUDIT_PRIOR_READBACK_MISMATCH")

    state_digest = _canonical_state_digest(canonical_state)
    projection = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "task_id": safe_task_id,
        "repository": safe_repository,
        "projection_target": safe_target,
        "source_authority_digest": authority_digest if authority_ok and isinstance(authority_digest, str) else (envelope_digest or _ZERO_DIGEST),
        "evidence_linkset_digest": linkset_digest if isinstance(linkset_digest, str) else (envelope.get("evidence_linkset_digest") or _ZERO_DIGEST),
        "privacy_boundary_digest": privacy_digest if isinstance(privacy_digest, str) else (envelope.get("privacy_boundary_digest") or _ZERO_DIGEST),
        "canonical_state": canonical_state,
        "canonical_state_digest": state_digest,
        "prior_projection_present": isinstance(prior_projection, dict),
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "projected_at": projected_at_text,
    }

    if not reasons:
        if isinstance(prior_projection, dict) and not (prior_binding_mismatch or prior_readback_mismatch):
            reasons.add("EXTERNAL_AUDIT_EVENT_CURRENT")
        else:
            reasons.add("EXTERNAL_AUDIT_EVENT_READY")

    primary = _primary(reasons)
    ready = reasons == {"EXTERNAL_AUDIT_EVENT_READY"} or reasons == {"EXTERNAL_AUDIT_EVENT_CURRENT"}
    return {
        **projection,
        "outcome": "READY" if ready else "BLOCKED",
        "reason_code": primary,
        "reason_codes": sorted(reasons),
        "projection_digest": _digest(projection),
    }


def _observed_at_dt(decision: object) -> datetime | None:
    """Return the UTC ``datetime`` of a decision's ``observed_at`` or ``None``.

    A missing, empty, malformed, or timezone-less ``observed_at`` yields ``None``
    so callers treat freshness as indeterminate rather than fabricating a
    comparison. Pure parsing only; no I/O or mutation.
    """
    raw = decision.get("observed_at") if isinstance(decision, dict) else None
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


# SCRUM-345 (NA81-F6-N03) stale-source reason code. Added to the precedence list
# so a stale-but-digest-valid source authority decision is surfaced distinctly
# from a structurally invalid one. Backward compatible: the base renderer is
# unchanged and this code is only emitted by ``project_external_audit_event_na81``.
REASON_PRECEDENCE = [*REASON_PRECEDENCE, "EXTERNAL_AUDIT_SOURCE_STALE"]

STALE_REASON = "EXTERNAL_AUDIT_SOURCE_STALE"


def project_external_audit_event_na81(
    *,
    task_id: str,
    repository: str,
    projection_target: str,
    source_authority_decision: dict[str, Any],
    evidence_linkset: dict[str, Any],
    privacy_boundary_decision: dict[str, Any],
    envelope: dict[str, Any],
    prior_projection: dict[str, Any] | None = None,
    projected_at: str | None = None,
    source_freshness_cutoff: str | None = None,
) -> dict[str, object]:
    """SCRUM-345 (NA81-F6-N03) external audit-event projection with stale-source guard.

    Delegates all canonical-source rendering, stable correlation, idempotent
    duplicate replay, privacy-boundary handling and non-authority semantics to
    ``project_external_audit_event`` (SCRUM-222), which is left unchanged for
    backward compatibility. This wrapper adds the single behavior the current
    SCRUM-345 brief requires that the base renderer lacks:

    STALE SOURCE — a source-authority decision that is digest-valid but was
    observed against a canonical snapshot older than ``source_freshness_cutoff``
    is rendered ``BLOCKED`` with ``EXTERNAL_AUDIT_SOURCE_STALE`` instead of
    ``READY``. ``source_freshness_cutoff`` is the canonical source's known-current
    freshness timestamp; when ``None`` (default) no staleness check is performed
    and behavior is identical to the base renderer.

    Read-only. Performs no connector call, network request, filesystem mutation,
    Jira transition, branch creation, commit, PR action, approval, merge,
    deployment or production operation. Never grants write/approval/merge/deploy/
    production authority and never projects secrets or derives truth from another
    projection.
    """
    result = project_external_audit_event(
        task_id=task_id,
        repository=repository,
        projection_target=projection_target,
        source_authority_decision=source_authority_decision,
        evidence_linkset=evidence_linkset,
        privacy_boundary_decision=privacy_boundary_decision,
        envelope=envelope,
        prior_projection=prior_projection,
        projected_at=projected_at,
    )
    if source_freshness_cutoff is None or result.get("outcome") != "READY":
        return result

    observed = _observed_at_dt(source_authority_decision)
    cutoff = _observed_at_dt({"observed_at": source_freshness_cutoff})
    if observed is None or cutoff is None:
        return result
    if observed < cutoff:
        result["outcome"] = "BLOCKED"
        result["reason_code"] = STALE_REASON
        result["reason_codes"] = sorted(set(result.get("reason_codes", [])) | {STALE_REASON})
        proj_only = {
            k: v for k, v in result.items()
            if k not in ("outcome", "reason_code", "reason_codes", "projection_digest")
        }
        result["projection_digest"] = _digest(proj_only)
    return result
