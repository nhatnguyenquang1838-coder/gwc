#!/usr/bin/env python3
"""Pure deterministic projection reconcile-readback for SCRUM-225 (M4).

Consumes the shared closed envelope, the three B1 decisions (source-authority,
evidence-linkset, privacy-boundary), the SCRUM-224 drift decision, a B2-rendered
external projection, and a prior projection readback, then reconciles the
projection against the prior readback.

The evaluator is pure: it performs no connector call, network request, filesystem
mutation, Jira transition, branch/PR action, approval, merge, deployment, release,
or production operation. Every authority field is fixed to ``false``;
``read_only_projection`` is fixed to ``true``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _decision_ready(decision: Optional[Dict[str, Any]], artifact_type: str) -> bool:
    if not isinstance(decision, dict):
        return False
    if decision.get("artifact_type") != artifact_type:
        return False
    return decision.get("outcome") == "READY" and decision.get("authority_status") == "CONFIRMED"


def _digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def reconcile_projection_readback(
    *,
    envelope: Dict[str, Any],
    source_authority_decision: Dict[str, Any],
    evidence_linkset: Dict[str, Any],
    privacy_boundary_decision: Dict[str, Any],
    drift_decision: Dict[str, Any],
    projection: Dict[str, Any],
    prior_readback: Dict[str, Any],
) -> Dict[str, Any]:
    """Reconcile an external projection against a prior readback and drift decision.

    Returns a closed ``projection-reconcile-readback`` artifact. Fails closed (BLOCKED)
    for invalid input, missing/blocked B1 decisions, missing drift decision, or
    projection divergence from the prior readback.
    """
    reason_codes: List[str] = []
    divergence_fields: List[str] = []

    # --- Input validation ---------------------------------------------------
    if not isinstance(envelope, dict) or envelope.get("artifact_type") != "sync-projection-envelope":
        reason_codes.append("RECONCILE_INPUT_INVALID")
    if not isinstance(projection, dict):
        reason_codes.append("RECONCILE_INPUT_INVALID")
    if not isinstance(prior_readback, dict):
        reason_codes.append("RECONCILE_INPUT_INVALID")

    # --- B1 prerequisite gates ---------------------------------------------
    if not _decision_ready(source_authority_decision, "projection-source-authority-decision"):
        reason_codes.append("RECONCILE_SOURCE_AUTHORITY_BLOCKED")
    if not _decision_ready(evidence_linkset, "projection-evidence-linkset"):
        reason_codes.append("RECONCILE_EVIDENCE_LINKSET_BLOCKED")
    if not _decision_ready(privacy_boundary_decision, "projection-privacy-decision"):
        reason_codes.append("RECONCILE_PRIVACY_BOUNDARY_BLOCKED")

    # --- 224 drift decision gate -------------------------------------------
    if not _decision_ready(drift_decision, "projection-drift-decision"):
        reason_codes.append("RECONCILE_DRIFT_DECISION_BLOCKED")
    elif drift_decision.get("drift_detected") is True:
        reason_codes.append("RECONCILE_DRIFT_DETECTED")

    # --- Readback comparison ------------------------------------------------
    if isinstance(projection, dict) and isinstance(prior_readback, dict):
        proj_state = projection.get("canonical_state")
        prior_state = prior_readback.get("canonical_state")
        if proj_state is None:
            reason_codes.append("RECONCILE_PROJECTION_STATE_MISSING")
        elif prior_state is None:
            reason_codes.append("RECONCILE_PRIOR_STATE_MISSING")
        else:
            if proj_state != prior_state:
                reason_codes.append("RECONCILE_READBACK_DIVERGENCE")
                for key in set(proj_state.keys()) | set(prior_state.keys()):
                    if proj_state.get(key) != prior_state.get(key):
                        divergence_fields.append(str(key))

    current = not bool(reason_codes) and not bool(divergence_fields)
    if current:
        outcome = "READY"
        reason_code = "PROJECTION_CURRENT"
    elif divergence_fields:
        outcome = "BLOCKED"
        reason_code = "RECONCILE_READBACK_DIVERGENCE"
    else:
        outcome = "BLOCKED"
        reason_code = reason_codes[0]

    semantic = {
        "task_id": envelope.get("task_id") if isinstance(envelope, dict) else None,
        "projection_target": envelope.get("projection_target") if isinstance(envelope, dict) else None,
        "outcome": outcome,
        "current": current,
        "divergence_fields": sorted(divergence_fields),
        "canonical_state_digest": _digest(projection.get("canonical_state", {}) if isinstance(projection, dict) else {}),
    }
    decision_digest = "sha256:" + hashlib.sha256(_stable_json(semantic).encode("utf-8")).hexdigest()

    return {
        "schema_version": "1.0",
        "artifact_type": "projection-reconcile-readback",
        "task_id": (envelope.get("task_id") if isinstance(envelope, dict) else None),
        "repository": (envelope.get("repository") if isinstance(envelope, dict) else None),
        "projection_target": (envelope.get("projection_target") if isinstance(envelope, dict) else None),
        "outcome": outcome,
        "authority_status": "REJECTED" if outcome == "BLOCKED" else "CONFIRMED",
        "reason_code": reason_code,
        "reason_codes": sorted(set(reason_codes)) if reason_codes else (["PROJECTION_CURRENT"] if current else ["RECONCILE_READBACK_DIVERGENCE"]),
        "current": current,
        "divergence_fields": divergence_fields,
        "canonical_state_digest": semantic["canonical_state_digest"],
        "observed_at": None,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": decision_digest,
    }
