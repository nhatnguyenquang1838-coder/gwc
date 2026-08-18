#!/usr/bin/env python3
"""Pure deterministic Task Center synchronization projection renderer for SCRUM-221.

The renderer consumes a stable B1 source-authority decision, a B1 evidence
linkset, a B1 privacy-boundary decision and a closed sync-projection envelope,
then renders an approved, read-only Task Center synchronization projection. It
performs no connector call, network request, filesystem mutation, Jira
transition, branch creation, commit, PR action, approval generation, merge,
deployment or production operation.

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
ARTIFACT_TYPE = "task-center-sync-projection"

REASON_PRECEDENCE = [
    "TASK_CENTER_INPUT_INVALID",
    "TASK_CENTER_SOURCE_AUTHORITY_INVALID",
    "TASK_CENTER_EVIDENCE_LINKSET_INVALID",
    "TASK_CENTER_PRIVACY_BOUNDARY_INVALID",
    "TASK_CENTER_PRIOR_BINDING_MISMATCH",
    "TASK_CENTER_REVISION_REGRESSION",
    "TASK_CENTER_PRIOR_READBACK_MISMATCH",
    "TASK_CENTER_SYNC_READY",
    "TASK_CENTER_SYNC_CURRENT",
]

_TASK_RE = re.compile(r"^[A-Z][A-Z0-9]+-[1-9][0-9]*$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TARGET_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ZERO_DIGEST = "sha256:" + "0" * 64

ALLOWED_CANONICAL_KEYS = {
    "task_id", "task_status", "task_title", "task_type", "task_assignee",
    "gate", "gate_outcome", "repository", "repository_head",
    "projection_target", "projected_at", "evidence_linkset_digest",
    "source_authority_digest", "privacy_boundary_digest",
}
IDEMPOTENT_KEYS = {
    "task_id", "task_status", "task_assignee", "gate", "gate_outcome",
    "repository_head", "source_authority_digest", "evidence_linkset_digest",
    "privacy_boundary_digest",
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
    return "TASK_CENTER_INPUT_INVALID"


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


def project_task_center_sync(
    *,
    task_id: str,
    repository: str,
    projection_target: str,
    source_authority_decision: dict[str, Any],
    evidence_linkset: dict[str, Any],
    privacy_boundary_decision: dict[str, Any],
    envelope: dict[str, Any],
    prior_projection: dict[str, Any] | None = None,
    prior_repository_head: str | None = None,
    projected_at: str | None = None,
) -> dict[str, object]:
    """Return a schema-valid, read-only Task Center sync projection without I/O or mutation."""

    reasons: set[str] = set()
    safe_task_id = task_id if isinstance(task_id, str) and _TASK_RE.fullmatch(task_id) else "INVALID-1"
    safe_repository = repository if isinstance(repository, str) and _REPOSITORY_RE.fullmatch(repository) else "invalid/repository"
    safe_target = projection_target if isinstance(projection_target, str) and _TARGET_RE.fullmatch(projection_target) else "invalid-target"
    if safe_task_id != task_id or safe_repository != repository or safe_target != projection_target:
        reasons.add("TASK_CENTER_INPUT_INVALID")

    try:
        projected_at_text = _timestamp(projected_at)
    except Exception:
        projected_at_text = "1970-01-01T00:00:00Z"
        reasons.add("TASK_CENTER_INPUT_INVALID")

    if not isinstance(envelope, dict):
        reasons.add("TASK_CENTER_INPUT_INVALID")
        envelope = {}
    if not isinstance(prior_projection, (dict, type(None))):
        reasons.add("TASK_CENTER_INPUT_INVALID")

    authority_ok = _source_authority_is_valid(source_authority_decision, safe_task_id, safe_repository, safe_target)
    if not authority_ok:
        reasons.add("TASK_CENTER_SOURCE_AUTHORITY_INVALID")
    linkset_ok = _evidence_linkset_is_valid(evidence_linkset, safe_task_id, safe_repository, safe_target)
    if not linkset_ok:
        reasons.add("TASK_CENTER_EVIDENCE_LINKSET_INVALID")
    privacy_ok = _privacy_boundary_is_valid(privacy_boundary_decision, safe_task_id, safe_repository, safe_target)
    if not privacy_ok:
        reasons.add("TASK_CENTER_PRIVACY_BOUNDARY_INVALID")

    envelope_digest = envelope.get("source_authority_digest") if isinstance(envelope, dict) else None
    linkset_digest = evidence_linkset.get("linkset_digest") if isinstance(evidence_linkset, dict) else None
    privacy_digest = privacy_boundary_decision.get("decision_digest") if isinstance(privacy_boundary_decision, dict) else None
    authority_digest: str | None = None

    if not reasons:
        authority_digest = source_authority_decision.get("decision_digest") if isinstance(source_authority_decision, dict) else None
        if isinstance(authority_digest, str) and _DIGEST_RE.fullmatch(authority_digest):
            if envelope_digest != authority_digest:
                reasons.add("TASK_CENTER_SOURCE_AUTHORITY_INVALID")
        else:
            reasons.add("TASK_CENTER_SOURCE_AUTHORITY_INVALID")
        if isinstance(linkset_digest, str) and _DIGEST_RE.fullmatch(linkset_digest):
            if envelope.get("evidence_linkset_digest") != linkset_digest:
                reasons.add("TASK_CENTER_EVIDENCE_LINKSET_INVALID")
        else:
            reasons.add("TASK_CENTER_EVIDENCE_LINKSET_INVALID")
        if isinstance(privacy_digest, str) and _DIGEST_RE.fullmatch(privacy_digest):
            if envelope.get("privacy_boundary_digest") != privacy_digest:
                reasons.add("TASK_CENTER_PRIVACY_BOUNDARY_INVALID")
        else:
            reasons.add("TASK_CENTER_PRIVACY_BOUNDARY_INVALID")

    canonical_state: dict[str, Any] = {}
    if isinstance(envelope, dict) and isinstance(envelope.get("canonical_state"), dict):
        for key, value in envelope["canonical_state"].items():
            if key not in ALLOWED_CANONICAL_KEYS:
                reasons.add("TASK_CENTER_INPUT_INVALID")
                continue
            canonical_state[key] = value
    else:
        reasons.add("TASK_CENTER_INPUT_INVALID")

    prior_binding_mismatch = False
    revision_regression = False
    prior_readback_mismatch = False
    if isinstance(prior_projection, dict) and not reasons:
        prior_task = prior_projection.get("task_id")
        prior_repo = prior_projection.get("repository")
        prior_target = prior_projection.get("projection_target")
        if prior_task != safe_task_id or prior_repo != safe_repository or prior_target != safe_target:
            prior_binding_mismatch = True
        else:
            prior_state = prior_projection.get("canonical_state") if isinstance(prior_projection.get("canonical_state"), dict) else prior_projection
            prior_head = prior_state.get("repository_head")
            current_head = canonical_state.get("repository_head")
            if isinstance(prior_head, str) and isinstance(current_head, str) and prior_head != current_head:
                revision_regression = True
            for key in IDEMPOTENT_KEYS:
                if prior_state.get(key) != canonical_state.get(key):
                    prior_readback_mismatch = True
                    break
    if prior_binding_mismatch:
        reasons.add("TASK_CENTER_PRIOR_BINDING_MISMATCH")
    elif revision_regression:
        reasons.add("TASK_CENTER_REVISION_REGRESSION")
    elif prior_readback_mismatch:
        reasons.add("TASK_CENTER_PRIOR_READBACK_MISMATCH")

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
        if isinstance(prior_projection, dict) and not (prior_binding_mismatch or revision_regression or prior_readback_mismatch):
            reasons.add("TASK_CENTER_SYNC_CURRENT")
        else:
            reasons.add("TASK_CENTER_SYNC_READY")

    primary = _primary(reasons)
    ready = reasons == {"TASK_CENTER_SYNC_READY"} or reasons == {"TASK_CENTER_SYNC_CURRENT"}
    return {
        **projection,
        "outcome": "READY" if ready else "BLOCKED",
        "reason_code": primary,
        "reason_codes": sorted(reasons),
        "projection_digest": _digest(projection),
    }


# ---------------------------------------------------------------------------
# NA81 execution-level Task Center sync intent (SCRUM-279 / SCRUM-344)
#
# The M4 ``project_task_center_sync`` renderer above is a pure projection of
# B1 decisions + envelope. SCRUM-279 (#279) requires the *execution-level*
# deterministic sync intent with three properties the M4 renderer does not
# expose:
#
#   * monotonic source revision  -- a strictly increasing ``source_revision``
#                                   that rejects out-of-order / stale sources;
#   * stable idempotency key     -- a deterministic key over canonical facts so
#                                   duplicate replay is a clean no-op;
#   * explicit readback expectation -- the consumer is told exactly what to read
#                                   back (expected canonical digest + revision).
#
# This function is additive and backward-compatible: ``project_task_center_sync``
# is unchanged. It is pure: no connector call, network request, filesystem
# mutation, Jira transition, approval, merge, deployment or production
# operation. Task Center remains a projection surface -- it never becomes
# canonical task truth or authority (PROJECTION_IS_NOT_CANONICAL_TASK_TRUTH),
# and a projection failure never mutates canonical outcome
# (PROJECTION_FAILURE_DOES_NOT_MUTATE_CANONICAL_OUTCOME).
# ---------------------------------------------------------------------------

NA81_REASON_PRECEDENCE = [
    "TASK_CENTER_NA81_INPUT_INVALID",
    "TASK_CENTER_NA81_MISSING_CANONICAL_SOURCE",
    "TASK_CENTER_NA81_NON_AUTHORITATIVE",
    "TASK_CENTER_NA81_PRIVACY_BOUNDARY_INVALID",
    "TASK_CENTER_NA81_REVISION_OUT_OF_ORDER",
    "TASK_CENTER_NA81_STALE_SOURCE",
    "TASK_CENTER_NA81_PRIOR_READBACK_MISMATCH",
    "TASK_CENTER_NA81_SYNC_READY",
    "TASK_CENTER_NA81_SYNC_CURRENT",
]

NA81_ARTIFACT_TYPE = "task-center-sync-intent"


def _na81_primary(reasons: set[str]) -> str:
    for code in NA81_REASON_PRECEDENCE:
        if code in reasons:
            return code
    return "TASK_CENTER_NA81_INPUT_INVALID"


def render_task_center_sync_na81(
    *,
    task_id: str,
    repository: str,
    projection_target: str,
    source_authority_decision: dict[str, Any],
    evidence_linkset: dict[str, Any],
    privacy_boundary_decision: dict[str, Any],
    envelope: dict[str, Any],
    source_revision: int,
    prior_readback_expectation: dict[str, Any] | None = None,
    projected_at: str | None = None,
) -> dict[str, object]:
    """Render a deterministic Task Center sync intent with monotonic revision.

    Returns a read-only, authority-false intent carrying a stable
    ``idempotency_key`` and an explicit ``readback_expectation``. Rejects
    out-of-order (``source_revision`` regresses) and stale (same revision but
    canonical content mutated) sources. Never derives canonical truth from the
    projection.
    """

    reasons: set[str] = set()
    safe_task_id = task_id if isinstance(task_id, str) and _TASK_RE.fullmatch(task_id) else "INVALID-1"
    safe_repository = repository if isinstance(repository, str) and _REPOSITORY_RE.fullmatch(repository) else "invalid/repository"
    safe_target = projection_target if isinstance(projection_target, str) and _TARGET_RE.fullmatch(projection_target) else "invalid-target"
    if safe_task_id != task_id or safe_repository != repository or safe_target != projection_target:
        reasons.add("TASK_CENTER_NA81_INPUT_INVALID")

    if not isinstance(source_revision, int) or isinstance(source_revision, bool) or source_revision < 0:
        reasons.add("TASK_CENTER_NA81_INPUT_INVALID")

    try:
        projected_at_text = _timestamp(projected_at)
    except Exception:
        projected_at_text = "1970-01-01T00:00:00Z"
        reasons.add("TASK_CENTER_NA81_INPUT_INVALID")

    if not isinstance(envelope, dict):
        reasons.add("TASK_CENTER_NA81_INPUT_INVALID")
        envelope = {}

    authority_ok = _source_authority_is_valid(source_authority_decision, safe_task_id, safe_repository, safe_target)
    if not authority_ok:
        reasons.add("TASK_CENTER_NA81_NON_AUTHORITATIVE")
    linkset_ok = _evidence_linkset_is_valid(evidence_linkset, safe_task_id, safe_repository, safe_target)
    if not linkset_ok:
        reasons.add("TASK_CENTER_NA81_NON_AUTHORITATIVE")
    privacy_ok = _privacy_boundary_is_valid(privacy_boundary_decision, safe_task_id, safe_repository, safe_target)
    if not privacy_ok:
        reasons.add("TASK_CENTER_NA81_PRIVACY_BOUNDARY_INVALID")

    canonical_state: dict[str, Any] = {}
    if isinstance(envelope.get("canonical_state"), dict):
        for key, value in envelope["canonical_state"].items():
            if key not in ALLOWED_CANONICAL_KEYS:
                reasons.add("TASK_CENTER_NA81_INPUT_INVALID")
                continue
            canonical_state[key] = value
    else:
        reasons.add("TASK_CENTER_NA81_INPUT_INVALID")

    # A Task Center sync intent needs a canonical source anchor. Without a
    # repository head we have no canonical source to project.
    if "repository_head" not in canonical_state:
        reasons.add("TASK_CENTER_NA81_MISSING_CANONICAL_SOURCE")

    authority_digest = source_authority_decision.get("decision_digest") if isinstance(source_authority_decision, dict) else None
    linkset_digest = evidence_linkset.get("linkset_digest") if isinstance(evidence_linkset, dict) else None
    privacy_digest = privacy_boundary_decision.get("decision_digest") if isinstance(privacy_boundary_decision, dict) else None
    if not (isinstance(authority_digest, str) and _DIGEST_RE.fullmatch(authority_digest)):
        authority_digest = envelope.get("source_authority_digest") if isinstance(envelope.get("source_authority_digest"), str) and _DIGEST_RE.fullmatch(envelope["source_authority_digest"]) else None
    if not (isinstance(linkset_digest, str) and _DIGEST_RE.fullmatch(linkset_digest)):
        linkset_digest = envelope.get("evidence_linkset_digest") if isinstance(envelope.get("evidence_linkset_digest"), str) and _DIGEST_RE.fullmatch(envelope["evidence_linkset_digest"]) else None
    if not (isinstance(privacy_digest, str) and _DIGEST_RE.fullmatch(privacy_digest)):
        privacy_digest = envelope.get("privacy_boundary_digest") if isinstance(envelope.get("privacy_boundary_digest"), str) and _DIGEST_RE.fullmatch(envelope["privacy_boundary_digest"]) else None

    canonical_state_digest = _canonical_state_digest(canonical_state)

    # Stable idempotency key over canonical facts + revision. Deterministic and
    # order-independent so duplicate replay yields an identical intent.
    idempotency_facts = {
        "task_id": safe_task_id,
        "repository": safe_repository,
        "projection_target": safe_target,
        "source_revision": source_revision,
        "canonical_state_digest": canonical_state_digest,
        "source_authority_digest": authority_digest or _ZERO_DIGEST,
        "evidence_linkset_digest": linkset_digest or _ZERO_DIGEST,
        "privacy_boundary_digest": privacy_digest or _ZERO_DIGEST,
    }
    idempotency_key = _digest(idempotency_facts)

    # Monotonic revision + stale-source rejection using the prior readback.
    if not reasons and isinstance(prior_readback_expectation, dict):
        prior_rev = prior_readback_expectation.get("source_revision")
        prior_digest = prior_readback_expectation.get("expected_canonical_state_digest")
        prior_idem = prior_readback_expectation.get("idempotency_key")
        if not (
            isinstance(prior_rev, int) and not isinstance(prior_rev, bool)
            and isinstance(prior_digest, str) and bool(_DIGEST_RE.fullmatch(prior_digest))
            and isinstance(prior_idem, str) and bool(_DIGEST_RE.fullmatch(prior_idem))
        ):
            reasons.add("TASK_CENTER_NA81_PRIOR_READBACK_MISMATCH")
        elif prior_rev > source_revision:
            # Source moved backwards -> out-of-order, never accepted.
            reasons.add("TASK_CENTER_NA81_REVISION_OUT_OF_ORDER")
        elif prior_rev == source_revision and prior_digest != canonical_state_digest:
            # Same revision but canonical content changed -> stale source.
            reasons.add("TASK_CENTER_NA81_STALE_SOURCE")

    if not reasons:
        if isinstance(prior_readback_expectation, dict):
            prior_rev = prior_readback_expectation.get("source_revision")
            prior_digest = prior_readback_expectation.get("expected_canonical_state_digest")
            prior_idem = prior_readback_expectation.get("idempotency_key")
            if (
                isinstance(prior_rev, int) and not isinstance(prior_rev, bool)
                and prior_rev == source_revision
                and prior_digest == canonical_state_digest
                and prior_idem == idempotency_key
            ):
                reasons.add("TASK_CENTER_NA81_SYNC_CURRENT")
            else:
                reasons.add("TASK_CENTER_NA81_SYNC_READY")
        else:
            reasons.add("TASK_CENTER_NA81_SYNC_READY")

    primary = _na81_primary(reasons)
    ready = reasons == {"TASK_CENTER_NA81_SYNC_READY"} or reasons == {"TASK_CENTER_NA81_SYNC_CURRENT"}

    readback_expectation: dict[str, object] | None = None
    if ready:
        readback_expectation = {
            "task_id": safe_task_id,
            "projection_target": safe_target,
            "source_revision": source_revision,
            "expected_canonical_state_digest": canonical_state_digest,
            "idempotency_key": idempotency_key,
        }

    projection = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": NA81_ARTIFACT_TYPE,
        "task_id": safe_task_id,
        "repository": safe_repository,
        "projection_target": safe_target,
        "source_authority_digest": authority_digest or (envelope.get("source_authority_digest") or _ZERO_DIGEST),
        "evidence_linkset_digest": linkset_digest or (envelope.get("evidence_linkset_digest") or _ZERO_DIGEST),
        "privacy_boundary_digest": privacy_digest or (envelope.get("privacy_boundary_digest") or _ZERO_DIGEST),
        "canonical_state": canonical_state,
        "canonical_state_digest": canonical_state_digest,
        "monotonic_source_revision": source_revision if ready else None,
        "idempotency_key": idempotency_key,
        "readback_expectation": readback_expectation,
        "prior_readback_present": isinstance(prior_readback_expectation, dict),
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "projected_at": projected_at_text,
    }

    return {
        **projection,
        "outcome": "READY" if ready else "BLOCKED",
        "reason_code": primary,
        "reason_codes": sorted(reasons),
        "projection_digest": _digest(projection),
        "decision_digest": _digest(projection),
    }
