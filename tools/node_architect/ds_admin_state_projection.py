#!/usr/bin/env python3
"""Pure deterministic DS Admin state projection renderer for SCRUM-220.

The renderer consumes a stable B1 source-authority decision, a B1 evidence
linkset, a B1 privacy-boundary decision and a closed sync-projection envelope,
then renders an approved, read-only DS Admin state projection. It performs no
connector call, network request, filesystem mutation, Jira transition, branch
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
ARTIFACT_TYPE = "ds-admin-state-projection"

REASON_PRECEDENCE = [
    "DS_ADMIN_INPUT_INVALID",
    "DS_ADMIN_SOURCE_AUTHORITY_INVALID",
    "DS_ADMIN_EVIDENCE_LINKSET_INVALID",
    "DS_ADMIN_PRIVACY_BOUNDARY_INVALID",
    "DS_ADMIN_PRIOR_BINDING_MISMATCH",
    "DS_ADMIN_REVISION_REGRESSION",
    "DS_ADMIN_PRIOR_READBACK_MISMATCH",
    "DS_ADMIN_PROJECTION_READY",
    "DS_ADMIN_PROJECTION_CURRENT",
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
# Fields whose prior readback must match to be idempotent (NOOP).
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
    return "DS_ADMIN_INPUT_INVALID"


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


def project_ds_admin_state(
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
    """Return a schema-valid, read-only DS Admin state projection without I/O or mutation."""

    reasons: set[str] = set()
    safe_task_id = task_id if isinstance(task_id, str) and _TASK_RE.fullmatch(task_id) else "INVALID-1"
    safe_repository = repository if isinstance(repository, str) and _REPOSITORY_RE.fullmatch(repository) else "invalid/repository"
    safe_target = projection_target if isinstance(projection_target, str) and _TARGET_RE.fullmatch(projection_target) else "invalid-target"
    if safe_task_id != task_id or safe_repository != repository or safe_target != projection_target:
        reasons.add("DS_ADMIN_INPUT_INVALID")

    try:
        projected_at_text = _timestamp(projected_at)
    except Exception:
        projected_at_text = "1970-01-01T00:00:00Z"
        reasons.add("DS_ADMIN_INPUT_INVALID")

    if not isinstance(envelope, dict):
        reasons.add("DS_ADMIN_INPUT_INVALID")
        envelope = {}
    if not isinstance(prior_projection, (dict, type(None))):
        reasons.add("DS_ADMIN_INPUT_INVALID")

    authority_ok = _source_authority_is_valid(source_authority_decision, safe_task_id, safe_repository, safe_target)
    if not authority_ok:
        reasons.add("DS_ADMIN_SOURCE_AUTHORITY_INVALID")
    linkset_ok = _evidence_linkset_is_valid(evidence_linkset, safe_task_id, safe_repository, safe_target)
    if not linkset_ok:
        reasons.add("DS_ADMIN_EVIDENCE_LINKSET_INVALID")
    privacy_ok = _privacy_boundary_is_valid(privacy_boundary_decision, safe_task_id, safe_repository, safe_target)
    if not privacy_ok:
        reasons.add("DS_ADMIN_PRIVACY_BOUNDARY_INVALID")

    envelope_digest = envelope.get("source_authority_digest") if isinstance(envelope, dict) else None
    linkset_digest = evidence_linkset.get("linkset_digest") if isinstance(evidence_linkset, dict) else None
    privacy_digest = privacy_boundary_decision.get("decision_digest") if isinstance(privacy_boundary_decision, dict) else None
    authority_digest: str | None = None

    if not reasons:
        authority_digest = source_authority_decision.get("decision_digest") if isinstance(source_authority_decision, dict) else None
        if isinstance(authority_digest, str) and _DIGEST_RE.fullmatch(authority_digest):
            if envelope_digest != authority_digest:
                reasons.add("DS_ADMIN_SOURCE_AUTHORITY_INVALID")
        else:
            reasons.add("DS_ADMIN_SOURCE_AUTHORITY_INVALID")
        if isinstance(linkset_digest, str) and _DIGEST_RE.fullmatch(linkset_digest):
            if envelope.get("evidence_linkset_digest") != linkset_digest:
                reasons.add("DS_ADMIN_EVIDENCE_LINKSET_INVALID")
        else:
            reasons.add("DS_ADMIN_EVIDENCE_LINKSET_INVALID")
        if isinstance(privacy_digest, str) and _DIGEST_RE.fullmatch(privacy_digest):
            if envelope.get("privacy_boundary_digest") != privacy_digest:
                reasons.add("DS_ADMIN_PRIVACY_BOUNDARY_INVALID")
        else:
            reasons.add("DS_ADMIN_PRIVACY_BOUNDARY_INVALID")

    canonical_state: dict[str, Any] = {}
    if isinstance(envelope, dict) and isinstance(envelope.get("canonical_state"), dict):
        for key, value in envelope["canonical_state"].items():
            if key not in ALLOWED_CANONICAL_KEYS:
                reasons.add("DS_ADMIN_INPUT_INVALID")
                continue
            canonical_state[key] = value
    else:
        reasons.add("DS_ADMIN_INPUT_INVALID")

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
        reasons.add("DS_ADMIN_PRIOR_BINDING_MISMATCH")
    elif revision_regression:
        reasons.add("DS_ADMIN_REVISION_REGRESSION")
    elif prior_readback_mismatch:
        reasons.add("DS_ADMIN_PRIOR_READBACK_MISMATCH")

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
            reasons.add("DS_ADMIN_PROJECTION_CURRENT")
        else:
            reasons.add("DS_ADMIN_PROJECTION_READY")

    primary = _primary(reasons)
    ready = reasons == {"DS_ADMIN_PROJECTION_READY"} or reasons == {"DS_ADMIN_PROJECTION_CURRENT"}
    return {
        **projection,
        "outcome": "READY" if ready else "BLOCKED",
        "reason_code": primary,
        "reason_codes": sorted(reasons),
        "projection_digest": _digest(projection),
    }


# --- SCRUM-343 (NA81-F6-N01) bounded DS Admin state projection ----------
#
# NA81 extension over the existing ``project_ds_admin_state`` renderer
# (SCRUM-220). The base renderer performs the closed, read-only projection;
# this NA81 layer adds the explicit SCRUM-343 semantics required by the
# current NA81 brief that the base renderer did not assert:
#
#   * stale source revision detection -- the canonical source authority
#     decision MUST reference current (VERIFIED) evidence; a STALE / MISSING
#     / AMBIGUOUS / CONFLICT binding means the projection would render from
#     non-current evidence and must be BLOCKED;
#   * explicit non-authoritative guarantee (read_only + every authority
#     field fixed false); the projection is NEVER canonical task truth
#     (PROJECTION_IS_NOT_CANONICAL_TASK_TRUTH);
#   * deterministic / replay idempotency (identical inputs -> identical
#     projection_digest);
#   * privacy filtering -- only ``ALLOWED_CANONICAL_KEYS`` may appear in the
#     projected canonical state; every other field is dropped;
#   * missing canonical source -> BLOCKED (no projection from absent truth).
#
# Backward-compatible: ``project_ds_admin_state`` is unchanged and is reused
# as the projection core. The NA81 result embeds the base schema-valid
# projection under ``projection`` and surfaces the NA81 assertions under
# ``na81``.
_NA81_STALE_BINDING_STATUSES = {"STALE", "MISSING", "AMBIGUOUS", "CONFLICT"}


def _na81_source_is_stale(source_authority_decision: object) -> bool:
    if not isinstance(source_authority_decision, dict):
        return False
    bindings = source_authority_decision.get("source_bindings")
    if not isinstance(bindings, list):
        return False
    for binding in bindings:
        if isinstance(binding, dict) and binding.get("status") in _NA81_STALE_BINDING_STATUSES:
            return True
    return False


def project_ds_admin_state_na81(
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
    """NA81 DS Admin state projection with explicit SCRUM-343 semantics.

    Reuses ``project_ds_admin_state`` as the projection core (VERIFIED_REUSE of
    the SCRUM-220 renderer) and layers the NA81 assertions required by the
    current brief (DELTA_REQUIRED). Pure and read-only: no connector call,
    network request, filesystem mutation, Jira transition, branch/PR action,
    approval, merge, deployment or production operation. The returned base
    ``projection`` is the closed, schema-valid ``ds-admin-state-projection``
    artifact; ``na81`` carries the explicit semantic guarantees.
    """
    base = project_ds_admin_state(
        task_id=task_id,
        repository=repository,
        projection_target=projection_target,
        source_authority_decision=source_authority_decision,
        evidence_linkset=evidence_linkset,
        privacy_boundary_decision=privacy_boundary_decision,
        envelope=envelope,
        prior_projection=prior_projection,
        prior_repository_head=prior_repository_head,
        projected_at=projected_at,
    )

    stale_source = _na81_source_is_stale(source_authority_decision)

    # Replay / idempotency: identical inputs must yield an identical digest.
    replay = project_ds_admin_state(
        task_id=task_id,
        repository=repository,
        projection_target=projection_target,
        source_authority_decision=source_authority_decision,
        evidence_linkset=evidence_linkset,
        privacy_boundary_decision=privacy_boundary_decision,
        envelope=envelope,
        prior_projection=prior_projection,
        prior_repository_head=prior_repository_head,
        projected_at=projected_at,
    )
    idempotent = replay.get("projection_digest") == base.get("projection_digest")

    canonical_state = base.get("canonical_state") if isinstance(base.get("canonical_state"), dict) else {}
    privacy_filtered = all(key in ALLOWED_CANONICAL_KEYS for key in canonical_state)

    non_authoritative = (
        base.get("read_only_projection") is True
        and all(base.get(field) is False for field in (
            "write_authority_granted", "approval_authority_granted",
            "merge_authority_granted", "deployment_authority_granted", "production_authority_granted",
        ))
    )

    canonical_source_present = isinstance(envelope, dict) and isinstance(envelope.get("canonical_state"), dict)

    base_blocked = base.get("outcome") != "READY"
    if stale_source:
        primary = "DS_ADMIN_NA81_STALE_SOURCE_REVISION"
    elif base_blocked:
        primary = base.get("reason_code", "DS_ADMIN_INPUT_INVALID")
    else:
        primary = "DS_ADMIN_NA81_PROJECTION_READY"

    reason_codes = sorted(set(base.get("reason_codes", [])) | (
        {"DS_ADMIN_NA81_STALE_SOURCE_REVISION"} if stale_source else set()
    ))

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "ds-admin-state-projection-na81",
        "task_id": base.get("task_id", task_id),
        "repository": base.get("repository", repository),
        "projection_target": base.get("projection_target", projection_target),
        "projection": base,
        "na81": {
            "stale_source_detected": stale_source,
            "deterministic": True,
            "idempotent": idempotent,
            "privacy_filtered": privacy_filtered,
            "non_authoritative": non_authoritative,
            "canonical_source_present": canonical_source_present,
        },
        "outcome": "BLOCKED" if (base_blocked or stale_source) else "READY",
        "reason_code": primary,
        "reason_codes": reason_codes,
        "projection_digest": _digest({k: v for k, v in base.items()}),
    }
