#!/usr/bin/env python3
"""Pure deterministic projection drift detection for SCRUM-224 (M4) + NA81 extensions.

Consumes the shared closed envelope, the three B1 decisions (source-authority,
evidence-linkset, privacy-boundary), a B2-rendered external projection, a
canonical state snapshot, and an optional ``readback_meta`` payload, then
detects divergence between the projection and the canonical state.

The evaluator is pure: it performs no connector call, network request,
filesystem mutation, Jira transition, branch/PR action, approval, merge,
deployment, release, or production operation. Every authority field is fixed
to ``false``; ``read_only_projection`` is fixed to ``true``.

NA81 extension (SCRUM-347): ``readback_meta`` enables stale/out-of-order,
conflicting-target, and unavailable-readback classifications without
breaking the original M4 interface.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple


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


# ---------------------------------------------------------------------------
# NA81 readback classification constants
# ---------------------------------------------------------------------------
PROJECTION_NO_DRIFT = "PROJECTION_NO_DRIFT"
PROJECTION_MATERIAL_DRIFT = "PROJECTION_MATERIAL_DRIFT"
PROJECTION_READBACK_STALE = "PROJECTION_READBACK_STALE"
PROJECTION_READBACK_CONFLICT = "PROJECTION_READBACK_CONFLICT"
PROJECTION_READBACK_UNAVAILABLE = "PROJECTION_READBACK_UNAVAILABLE"


def detect_projection_drift(
    *,
    envelope: Dict[str, Any],
    source_authority_decision: Dict[str, Any],
    evidence_linkset: Dict[str, Any],
    privacy_boundary_decision: Dict[str, Any],
    projection: Dict[str, Any],
    canonical_state: Dict[str, Any],
    readback_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Detect divergence between an external projection and canonical state.

    Returns a closed ``projection-drift-decision`` artifact. Fails closed (BLOCKED)
    for invalid input, missing/blocked B1 decisions, projection divergence, or
    readback meta classifications (stale / conflicting / unavailable).

    ``readback_meta`` (optional, NA81 extension) supports keys:
        - ``observed_at`` (str, ISO-8601): readback timestamp recorded on the
          decision.
        - ``stale`` (bool): readback is stale or out-of-order relative to the
          canonical state.
        - ``conflict`` (bool): external projection conflicts with canonical truth
          in a way that cannot be resolved by simple field diff.
        - ``unavailable`` (bool): readback source was unreachable or returned no
          usable state.
    """
    reason_codes: List[str] = []
    drift_fields: List[str] = []
    observed_at: Optional[str] = None

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

    # --- NA81 readback meta classification ----------------------------------
    if isinstance(readback_meta, dict):
        observed_at = readback_meta.get("observed_at")
        if readback_meta.get("unavailable"):
            reason_codes.append(PROJECTION_READBACK_UNAVAILABLE)
        if readback_meta.get("conflict"):
            reason_codes.append(PROJECTION_READBACK_CONFLICT)
        if readback_meta.get("stale"):
            reason_codes.append(PROJECTION_READBACK_STALE)

    # --- Drift comparison ---------------------------------------------------
    proj_state = projection.get("canonical_state") if isinstance(projection, dict) else None
    if proj_state is None:
        reason_codes.append("DRIFT_PROJECTION_STATE_MISSING")
    else:
        drift_fields = _walk_diff(canonical_state, proj_state)

    drift_detected = bool(drift_fields)
    if drift_detected and "DRIFT_PROJECTION_STATE_MISSING" not in reason_codes:
        reason_codes.append("DRIFT_DETECTED")

    # --- Original M4 outcome/reason_code logic (backward-compatible) ---------
    if reason_codes:
        outcome = "BLOCKED"
        if drift_detected:
            reason_code = "PROJECTION_DRIFT_DETECTED"
        else:
            reason_code = reason_codes[0]
    else:
        outcome = "READY"
        reason_code = "PROJECTION_DRIFT_NONE"

    # --- NA81 readback override (supersedes M4 defaults) --------------------
    if PROJECTION_READBACK_UNAVAILABLE in reason_codes:
        outcome = "BLOCKED"
        reason_code = PROJECTION_READBACK_UNAVAILABLE
    elif PROJECTION_READBACK_CONFLICT in reason_codes:
        outcome = "BLOCKED"
        reason_code = PROJECTION_READBACK_CONFLICT
    elif PROJECTION_READBACK_STALE in reason_codes:
        outcome = "BLOCKED"
        reason_code = PROJECTION_READBACK_STALE
    elif not reason_codes:
        # No blocks, no drift → NA81 explicit code
        outcome = "READY"
        reason_code = PROJECTION_NO_DRIFT
        reason_codes.append(PROJECTION_NO_DRIFT)
    elif drift_detected and "DRIFT_PROJECTION_STATE_MISSING" not in reason_codes:
        outcome = "BLOCKED"
        reason_code = PROJECTION_MATERIAL_DRIFT
        reason_codes.append(PROJECTION_MATERIAL_DRIFT)

    # --- Digest (must be stable for identical inputs) -----------------------
    canonical_digest = _canonical_state_digest(canonical_state) if isinstance(canonical_state, dict) else "sha256:" + "0" * 64
    digest_payload: Dict[str, Any] = {
        "task_id": (envelope.get("task_id") if isinstance(envelope, dict) else None),
        "projection_target": (envelope.get("projection_target") if isinstance(envelope, dict) else None),
        "outcome": outcome,
        "drift_detected": drift_detected,
        "drift_fields": sorted(drift_fields),
        "canonical_state_digest": canonical_digest,
        "reason_code": reason_code,
        "observed_at": observed_at,
    }
    decision_digest = "sha256:" + hashlib.sha256(
        _stable_json(digest_payload).encode("utf-8")
    ).hexdigest()

    # Ensure the M4 default code is present when there were no blocks and no drift
    # and readback_meta was absent (backward-compat for existing assertions).
    if not readback_meta and outcome == "READY" and reason_code == PROJECTION_NO_DRIFT:
        reason_code = "PROJECTION_DRIFT_NONE"
        reason_codes = ["PROJECTION_DRIFT_NONE"]

    return {
        "schema_version": "1.0",
        "artifact_type": "projection-drift-decision",
        "task_id": (envelope.get("task_id") if isinstance(envelope, dict) else None),
        "repository": (envelope.get("repository") if isinstance(envelope, dict) else None),
        "projection_target": (envelope.get("projection_target") if isinstance(envelope, dict) else None),
        "outcome": outcome,
        "authority_status": "REJECTED" if outcome == "BLOCKED" else "CONFIRMED",
        "reason_code": reason_code,
        "reason_codes": sorted(set(reason_codes)),
        "drift_detected": drift_detected,
        "drift_field_count": len(drift_fields),
        "drift_fields": drift_fields,
        "canonical_state_digest": canonical_digest,
        "observed_at": observed_at,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": decision_digest,
    }
