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
