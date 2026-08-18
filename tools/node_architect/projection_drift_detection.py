#!/usr/bin/env python3
"""Pure deterministic projection drift detection for SCRUM-224 (M4).

Consumes the shared closed envelope, the three B1 decisions (source-authority,
evidence-linkset, privacy-boundary), a B2-rendered external projection, and a
canonical state snapshot, then detects divergence between the projection and the
canonical state.

The evaluator is pure: it performs no connector call, network request, filesystem
mutation, Jira transition, branch/PR action, approval, merge, deployment, release,
or production operation. Every authority field is fixed to ``false``;
``read_only_projection`` is fixed to ``true``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _stable_json(payload: Any) -> str:
    """Order-independent canonical JSON (sorted keys, no whitespace)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_state_digest(canonical_state: Any) -> str:
    """Order-independent sha256 digest over the canonical state snapshot."""
    return "sha256:" + hashlib.sha256(_stable_json(canonical_state).encode("utf-8")).hexdigest()


def _walk_diff(a: Any, b: Any, path: str = "") -> List[str]:
    """Return list of dotted field paths where ``a`` (canonical) != ``b`` (projection)."""
    drift: List[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        keys = set(a.keys()) | set(b.keys())
        for k in sorted(keys):
            child = f"{path}.{k}" if path else str(k)
            if k not in a:
                drift.append(child)
            elif k not in b:
                drift.append(child)
            else:
                drift.extend(_walk_diff(a[k], b[k], child))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            drift.append(path or "<root>")
        else:
            for i, (av, bv) in enumerate(zip(a, b)):
                drift.extend(_walk_diff(av, bv, f"{path}[{i}]"))
    else:
        if a != b:
            drift.append(path or "<root>")
    return drift


def _decision_ready(decision: Optional[Dict[str, Any]], artifact_type: str) -> bool:
    if not isinstance(decision, dict):
        return False
    if decision.get("artifact_type") != artifact_type:
        return False
    return decision.get("outcome") == "READY" and decision.get("authority_status") == "CONFIRMED"


def detect_projection_drift(
    *,
    envelope: Dict[str, Any],
    source_authority_decision: Dict[str, Any],
    evidence_linkset: Dict[str, Any],
    privacy_boundary_decision: Dict[str, Any],
    projection: Dict[str, Any],
    canonical_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Detect divergence between an external projection and canonical state.

    Returns a closed ``projection-drift-decision`` artifact. Fails closed (BLOCKED)
    for invalid input, missing/blocked B1 decisions, or projection divergence.
    """
    reason_codes: List[str] = []
    drift_fields: List[str] = []

    # --- Input validation ---------------------------------------------------
    if not isinstance(envelope, dict) or envelope.get("artifact_type") != "sync-projection-envelope":
        reason_codes.append("DRIFT_INPUT_INVALID")
    if not isinstance(projection, dict):
        reason_codes.append("DRIFT_INPUT_INVALID")
    if not isinstance(canonical_state, dict):
        reason_codes.append("DRIFT_INPUT_INVALID")

    # --- B1 prerequisite gates ---------------------------------------------
    if not _decision_ready(source_authority_decision, "projection-source-authority-decision"):
        reason_codes.append("DRIFT_SOURCE_AUTHORITY_BLOCKED")
    if not _decision_ready(evidence_linkset, "projection-evidence-linkset"):
        reason_codes.append("DRIFT_EVIDENCE_LINKSET_BLOCKED")
    if not _decision_ready(privacy_boundary_decision, "projection-privacy-decision"):
        reason_codes.append("DRIFT_PRIVACY_BOUNDARY_BLOCKED")

    # B1 decision digests must match the envelope bindings (if envelope present).
    if isinstance(envelope, dict) and envelope.get("artifact_type") == "sync-projection-envelope":
        for decision, digest_key in (
            (source_authority_decision, "source_authority_digest"),
            (evidence_linkset, "evidence_linkset_digest"),
            (privacy_boundary_decision, "privacy_boundary_digest"),
        ):
            if isinstance(decision, dict) and digest_key in envelope:
                if decision.get("decision_digest") != envelope[digest_key]:
                    reason_codes.append("DRIFT_B1_DIGEST_MISMATCH")

    # --- Drift comparison ---------------------------------------------------
    proj_state = projection.get("canonical_state") if isinstance(projection, dict) else None
    if proj_state is None:
        reason_codes.append("DRIFT_PROJECTION_STATE_MISSING")
    else:
        drift_fields = _walk_diff(canonical_state, proj_state)

    drift_detected = bool(drift_fields)
    if drift_detected and not reason_codes:
        reason_codes.append("DRIFT_DETECTED")

    outcome = "BLOCKED" if reason_codes else "READY"
    if outcome == "READY":
        reason_code = "PROJECTION_DRIFT_NONE"
    elif drift_detected:
        reason_code = "PROJECTION_DRIFT_DETECTED"
    else:
        reason_code = reason_codes[0]

    canonical_digest = _canonical_state_digest(canonical_state) if isinstance(canonical_state, dict) else "sha256:" + "0" * 64

    return {
        "schema_version": "1.0",
        "artifact_type": "projection-drift-decision",
        "task_id": (envelope.get("task_id") if isinstance(envelope, dict) else None),
        "repository": (envelope.get("repository") if isinstance(envelope, dict) else None),
        "projection_target": (envelope.get("projection_target") if isinstance(envelope, dict) else None),
        "outcome": outcome,
        "authority_status": "REJECTED" if outcome == "BLOCKED" else "CONFIRMED",
        "reason_code": reason_code,
        "reason_codes": sorted(set(reason_codes)) if reason_codes else ["PROJECTION_DRIFT_NONE"],
        "drift_detected": drift_detected,
        "drift_field_count": len(drift_fields),
        "drift_fields": drift_fields,
        "canonical_state_digest": canonical_digest,
        "observed_at": None,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": "sha256:" + hashlib.sha256(
            _stable_json({
                "task_id": (envelope.get("task_id") if isinstance(envelope, dict) else None),
                "projection_target": (envelope.get("projection_target") if isinstance(envelope, dict) else None),
                "outcome": outcome,
                "drift_detected": drift_detected,
                "drift_fields": sorted(drift_fields),
                "canonical_state_digest": canonical_digest,
            }).encode("utf-8")
        ).hexdigest(),
    }


# --- SCRUM-347 (NA81-F6-N05) multi-target drift classification ------------
#
# Deterministic, read-only classification of canonical source state against
# multiple external projection readbacks. Produces a closed
# ``projection-drift-classification`` artifact with the SCRUM-347 taxonomy:
# NO_DRIFT / MATERIAL_DRIFT / CONFLICT / UNAVAILABLE_READBACK / STALE_READBACK.
#
# The evaluator is pure: it performs no connector call, network request,
# filesystem mutation, Jira transition, branch/PR action, approval, merge,
# deployment, release, or production operation. Every authority field is fixed
# to ``false``; ``read_only_projection`` is fixed to ``true``.
#
# Family invariants are enforced:
#   * PROJECTION_IS_NOT_CANONICAL_TASK_TRUTH -- canonical state is supplied by
#     the caller and is NEVER inferred from any projection readback;
#     projections are compared *against* the canonical source only.
#   * PROJECTION_FAILURE_DOES_NOT_MUTATE_CANONICAL_OUTCOME -- an unavailable or
#     stale readback is classified but never back-writes or mutates canonical
#     truth.
_NA81_CLASSIFICATION_ORDER = (
    "NO_DRIFT",
    "UNAVAILABLE_READBACK",
    "STALE_READBACK",
    "MATERIAL_DRIFT",
    "CONFLICT",
)
_NA81_SEVERITY = {name: i for i, name in enumerate(_NA81_CLASSIFICATION_ORDER)}


def classify_projection_drift_na81(
    *,
    task_id: str,
    repository: str,
    canonical_source: Dict[str, Any],
    projection_targets: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Classify canonical source state against multiple projection readbacks.

    ``canonical_source`` MUST carry the authoritative ``revision`` (exact source
    revision) and ``state`` (canonical state snapshot). An optional
    ``content_digest`` (``sha256:``) overrides the computed canonical-state
    digest.

    Each entry in ``projection_targets`` is ``{"target": <name>, "readback":
    <readback-or-None>}``. A ``readback`` is ``{"revision", "state",
    "content_digest"?}``. Readback classification precedence (per target):

      * UNAVAILABLE_READBACK -- readback missing/malformed (no authoritative
        readback could be obtained for the target);
      * STALE_READBACK -- readback ``revision`` differs from the canonical
        source ``revision`` (stale or out-of-order readback);
      * MATERIAL_DRIFT -- fresh readback (matches canonical revision) whose
        content digest diverges from canonical;
      * NO_DRIFT -- fresh readback that matches canonical exactly.

    Aggregate (overall) classification takes the highest-severity per-target
    status, then promotes to CONFLICT when two or more available (fresh)
    targets disagree on readback content (conflicting target state). The result
    is deterministic and never grants authority or mutates canonical state.
    """
    if not isinstance(canonical_source, dict) or "revision" not in canonical_source or "state" not in canonical_source:
        raise TypeError("canonical_source must be a dict with 'revision' and 'state'")
    if not isinstance(projection_targets, (list, tuple)):
        raise TypeError("projection_targets must be a list or tuple")

    canonical_revision = canonical_source.get("revision")
    canonical_state = canonical_source.get("state")
    canonical_state_digest = canonical_source.get("content_digest") or _na81_canonical_state_digest(canonical_state)

    per_target: List[Dict[str, Any]] = []
    for entry in projection_targets:
        if not isinstance(entry, dict):
            per_target.append({
                "target": None,
                "status": "UNAVAILABLE_READBACK",
                "readback_revision": None,
                "readback_digest": None,
                "matches_canonical": None,
                "drift_fields": [],
                "detail": "projection target entry malformed",
            })
            continue
        target = entry.get("target")
        readback = entry.get("readback")
        if not isinstance(readback, dict) or "revision" not in readback or "state" not in readback:
            per_target.append({
                "target": target,
                "status": "UNAVAILABLE_READBACK",
                "readback_revision": None,
                "readback_digest": None,
                "matches_canonical": None,
                "drift_fields": [],
                "detail": "projection readback unavailable or malformed",
            })
            continue

        rb_revision = readback.get("revision")
        rb_state = readback.get("state")
        rb_digest = readback.get("content_digest") or _na81_canonical_state_digest(rb_state)

        if rb_revision != canonical_revision:
            per_target.append({
                "target": target,
                "status": "STALE_READBACK",
                "readback_revision": rb_revision,
                "canonical_revision": canonical_revision,
                "readback_digest": rb_digest,
                "matches_canonical": None,
                "drift_fields": [],
                "detail": "readback revision differs from canonical source revision (stale/out-of-order)",
            })
            continue

        if rb_digest != canonical_state_digest:
            drift_fields = sorted(_walk_diff(rb_state, canonical_state))
            per_target.append({
                "target": target,
                "status": "MATERIAL_DRIFT",
                "readback_revision": rb_revision,
                "readback_digest": rb_digest,
                "matches_canonical": True,
                "drift_fields": drift_fields,
                "detail": "fresh readback content digest differs from canonical source",
            })
        else:
            per_target.append({
                "target": target,
                "status": "NO_DRIFT",
                "readback_revision": rb_revision,
                "readback_digest": rb_digest,
                "matches_canonical": True,
                "drift_fields": [],
                "detail": "fresh readback matches canonical source",
            })

    # Conflict: available (fresh) targets whose readback digests disagree.
    fresh_digests = [
        t["readback_digest"]
        for t in per_target
        if t["status"] in ("NO_DRIFT", "MATERIAL_DRIFT") and t.get("readback_digest") is not None
    ]
    conflict = len(set(fresh_digests)) > 1

    per_target_statuses = [t["status"] for t in per_target]
    severity = max((_NA81_SEVERITY[s] for s in per_target_statuses), default=0)
    if conflict:
        severity = max(severity, _NA81_SEVERITY["CONFLICT"])
    overall = _NA81_CLASSIFICATION_ORDER[severity]

    def _count(status: str) -> int:
        return sum(1 for t in per_target if t["status"] == status)

    decision_core = {
        "task_id": task_id,
        "repository": repository,
        "canonical_source_revision": canonical_revision,
        "canonical_state_digest": canonical_state_digest,
        "classification": overall,
        "conflict": conflict,
        "per_target": sorted(
            [
                {
                    "target": t["target"],
                    "status": t["status"],
                    "readback_revision": t.get("readback_revision"),
                }
                for t in per_target
            ],
            key=lambda x: (x["target"] if x["target"] is not None else ""),
        ),
    }
    decision_digest = "sha256:" + hashlib.sha256(
        _stable_json(decision_core).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": "1.0",
        "artifact_type": "projection-drift-classification",
        "task_id": task_id,
        "repository": repository,
        "classification": overall,
        "severity": severity,
        "conflict": conflict,
        "canonical_source_revision": canonical_revision,
        "canonical_state_digest": canonical_state_digest,
        "target_count": len(per_target),
        "unavailable_count": _count("UNAVAILABLE_READBACK"),
        "stale_count": _count("STALE_READBACK"),
        "material_drift_count": _count("MATERIAL_DRIFT"),
        "conflict_count": (1 if conflict else 0),
        "per_target": per_target,
        "observed_at": None,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": decision_digest,
    }


def _na81_canonical_state_digest(state: Any) -> str:
    """Order-independent sha256 digest over a canonical state snapshot."""
    return "sha256:" + hashlib.sha256(_stable_json(state).encode("utf-8")).hexdigest()
