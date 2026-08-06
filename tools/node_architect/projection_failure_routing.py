#!/usr/bin/env python3
"""Pure deterministic projection failure routing for SCRUM-226 (M4).

Consumes the shared closed envelope, B1 decisions (source-authority,
evidence-linkset, privacy-boundary), the SCRUM-224 drift decision, and the
SCRUM-225 reconcile decision, then classifies the projection outcome into a
closed routing verdict: ``RETRYABLE``, ``HARD_DENIED``, ``STALE_EVIDENCE``, or
``AUTHORITY_CONFLICT``.

The routing is pure classification: it performs no connector call, network
request, filesystem mutation, Jira transition, branch/PR action, approval, merge,
deployment, release, or production operation. Every authority field is fixed to
``false``; ``read_only_projection`` is fixed to ``true``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _decision_present(decision: Optional[Dict[str, Any]], artifact_type: str) -> bool:
    if not isinstance(decision, dict):
        return False
    return decision.get("artifact_type") == artifact_type


def _decision_ready(decision: Optional[Dict[str, Any]], artifact_type: str) -> bool:
    if not isinstance(decision, dict):
        return False
    if decision.get("artifact_type") != artifact_type:
        return False
    return decision.get("outcome") == "READY" and decision.get("authority_status") == "CONFIRMED"


def route_projection_failure(
    *,
    envelope: Dict[str, Any],
    source_authority_decision: Dict[str, Any],
    evidence_linkset: Dict[str, Any],
    privacy_boundary_decision: Dict[str, Any],
    drift_decision: Dict[str, Any],
    reconcile_decision: Dict[str, Any],
) -> Dict[str, Any]:
    """Route a projection outcome from drift + reconcile decisions.

    Returns a closed ``projection-failure-routing`` artifact. Fails closed (BLOCKED)
    for invalid input, missing/blocked B1 decisions, or missing 224/225 decisions.
    Otherwise classifies into a routing verdict.
    """
    reason_codes: List[str] = []

    if not isinstance(envelope, dict) or envelope.get("artifact_type") != "sync-projection-envelope":
        reason_codes.append("ROUTE_INPUT_INVALID")
    if not _decision_ready(source_authority_decision, "projection-source-authority-decision"):
        reason_codes.append("ROUTE_SOURCE_AUTHORITY_BLOCKED")
    if not _decision_ready(evidence_linkset, "projection-evidence-linkset"):
        reason_codes.append("ROUTE_EVIDENCE_LINKSET_BLOCKED")
    if not _decision_ready(privacy_boundary_decision, "projection-privacy-decision"):
        reason_codes.append("ROUTE_PRIVACY_BOUNDARY_BLOCKED")
    if not _decision_present(drift_decision, "projection-drift-decision"):
        reason_codes.append("ROUTE_DRIFT_DECISION_BLOCKED")
    if not _decision_present(reconcile_decision, "projection-reconcile-readback"):
        reason_codes.append("ROUTE_RECONCILE_DECISION_BLOCKED")

    if reason_codes:
        outcome = "BLOCKED"
        reason_code = reason_codes[0]
        routing_verdict = "BLOCKED"
    else:
        # Classify from upstream decisions.
        drift_detected = bool(drift_decision.get("drift_detected"))
        reconcile_current = bool(reconcile_decision.get("current"))
        if drift_detected and not reconcile_current:
            routing_verdict = "RETRYABLE"
            reason_code = "ROUTE_RETRYABLE"
        elif not drift_detected and reconcile_current:
            routing_verdict = "HARD_DENIED"
            reason_code = "ROUTE_HARD_DENIED"
        elif not drift_detected and not reconcile_current:
            routing_verdict = "STALE_EVIDENCE"
            reason_code = "ROUTE_STALE_EVIDENCE"
        else:
            routing_verdict = "AUTHORITY_CONFLICT"
            reason_code = "ROUTE_AUTHORITY_CONFLICT"
        outcome = "READY"
        reason_codes = [reason_code]

    semantic = {
        "task_id": envelope.get("task_id") if isinstance(envelope, dict) else None,
        "projection_target": envelope.get("projection_target") if isinstance(envelope, dict) else None,
        "outcome": outcome,
        "routing_verdict": routing_verdict,
        "reason_code": reason_code,
    }
    decision_digest = "sha256:" + hashlib.sha256(_stable_json(semantic).encode("utf-8")).hexdigest()

    return {
        "schema_version": "1.0",
        "artifact_type": "projection-failure-routing",
        "task_id": (envelope.get("task_id") if isinstance(envelope, dict) else None),
        "repository": (envelope.get("repository") if isinstance(envelope, dict) else None),
        "projection_target": (envelope.get("projection_target") if isinstance(envelope, dict) else None),
        "outcome": outcome,
        "authority_status": "REJECTED" if outcome == "BLOCKED" else "CONFIRMED",
        "reason_code": reason_code,
        "reason_codes": sorted(set(reason_codes)),
        "routing_verdict": routing_verdict,
        "observed_at": None,
        "read_only_projection": True,
        "write_authority_granted": False,
        "approval_authority_granted": False,
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
        "decision_digest": decision_digest,
    }
