"""Pure, deterministic rendering of a bounded G2 execution envelope.

The renderer composes a closed envelope from approved F1 scope artifacts and F2
authority decisions. It may produce DRAFT / AWAITING_APPROVAL / ACTIVE states,
but it never executes the envelope or performs any write.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

_SCHEMA_VERSION = "1.0"
_ARTIFACT_TYPE = "g2-execution-envelope"

_REASON_AWAITING = "G2_ENVELOPE_AWAITING_APPROVAL"
_REASON_ACTIVE = "G2_ENVELOPE_ACTIVE"
_REASON_DRAFT = "G2_ENVELOPE_DRAFT"
_REASON_BLOCKED = "G2_ENVELOPE_APPROVAL_INVALID"
_REASON_EXPIRED = "G2_ENVELOPE_EXPIRED"
_REASON_SCOPE_MISMATCH = "G2_ENVELOPE_SCOPE_HASH_MISMATCH"
_REASON_BINDING_MISMATCH = "G2_ENVELOPE_BINDING_MISMATCH"
_REASON_AMBIGUOUS = "G2_ENVELOPE_APPROVAL_AMBIGUOUS"
_REASON_GATE_STATE_BLOCKED = "G2_ENVELOPE_GATE_STATE_BLOCKED"
_REASON_AUTHORITY_BLOCKED = "G2_ENVELOPE_AUTHORITY_BLOCKED"
_REASON_EVIDENCE_BLOCKED = "G2_ENVELOPE_EVIDENCE_BLOCKED"

_SCOPE_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class _EnvelopeInput:
    task_id: str
    repository: str
    base_ref: str
    base_sha: str
    risk_class: str
    risk_digest: str
    bounded_read_scope: tuple[str, ...]
    bounded_write_scope: tuple[str, ...]
    authorized_actions: tuple[str, ...]
    scope_hash: str
    f1_artifact_digests: dict[str, Any]
    f2_digests: dict[str, Any]
    checkpoint_id: str
    issued_at: str
    expires_at: str
    approval_request: dict[str, Any] | None = None
    approval_validation: dict[str, Any] | None = None
    working_branch: str = ""


def _is_expired(issued_at: str, expires_at: str, now: str | None = None) -> bool:
    """Compare ISO timestamps lexicographically (zero-padded UTC).

    Expired only when an explicit `now` is provided and is at/after expires_at.
    Without `now`, the envelope is not yet expired.
    """
    if now is None:
        return False
    return now >= expires_at


def _canon(obj: Any) -> str:
    if isinstance(obj, dict):
        return "{" + ",".join(f"{k}:{_canon(v)}" for k, v in sorted(obj.items())) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_canon(v) for v in obj) + "]"
    return str(obj)


def _digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(_canon(p).encode("utf-8"))
    return "sha256:" + h.hexdigest()


# Canonical blocker reason codes taken verbatim from the producer modules so the
# renderer gates on the *same* semantics the producers emit (no parallel fields).
_GATE_STATE_BLOCKERS = {
    "GATE_STATE_INPUT_INVALID",
    "GATE_STATE_REPLAY_CONFLICT",
    "GATE_STATE_BINDING_MISMATCH",
    "GATE_STATE_EVIDENCE_CONFLICT",
    "GATE_STATE_GATE_FAILED",
    "GATE_STATE_DRIFT",
    "GATE_STATE_EVIDENCE_STALE",
    "GATE_STATE_REQUIRED_EVIDENCE_MISSING",
}
_EVIDENCE_BLOCKERS = {
    "EVIDENCE_INPUT_INVALID",
    "EVIDENCE_BINDING_MISMATCH",
    "EVIDENCE_CONFLICT",
    "EVIDENCE_PROJECTION_ONLY",
    "EVIDENCE_STALE",
    "EVIDENCE_REQUIRED_MISSING",
    "EVIDENCE_OBSERVABILITY_INCOMPLETE",
    "EVIDENCE_CI_BINDING_MISMATCH",
}


def _gate_state_accepted(gs: object) -> bool:
    """True iff gate_state_resolution is in its canonical accepted state:
    gate_status PASS/NOT_APPLICABLE, no drift, no replay conflict, no blockers."""
    if not isinstance(gs, dict):
        return False
    if gs.get("gate_status") not in ("PASS", "NOT_APPLICABLE"):
        return False
    drift = gs.get("drift_decision")
    if isinstance(drift, dict) and drift.get("status") not in ("NO_DRIFT", None):
        return False
    if gs.get("replay_status") == "REPLAY_CONFLICT":
        return False
    reasons = gs.get("reason_codes") or []
    if any(r in _GATE_STATE_BLOCKERS for r in reasons):
        return False
    return True


def _authority_accepted(ab: object) -> bool:
    """True iff authority_boundary_decision permits execution: decision is one
    of REQUIRE_APPROVAL/ALLOW_PREPARATION/NOT_APPLICABLE, not prohibited, not
    replay/stale-conflicted."""
    if not isinstance(ab, dict):
        return False
    if ab.get("decision") not in ("REQUIRE_APPROVAL", "ALLOW_PREPARATION", "NOT_APPLICABLE"):
        return False
    if ab.get("prohibited") is True:
        return False
    if ab.get("replay_status") == "REPLAY_CONFLICT":
        return False
    if ab.get("stale_evidence") is True:
        return False
    return True


def _evidence_accepted(em: object) -> bool:
    """True iff evidence_artifact_map is READY with no blocker reasons and no
    missing/stale/projection-only required evidence."""
    if not isinstance(em, dict):
        return False
    if em.get("outcome") != "READY":
        return False
    reasons = em.get("reason_codes") or []
    if any(r in _EVIDENCE_BLOCKERS for r in reasons):
        return False
    if em.get("missing_required") or em.get("stale_required") or em.get("projection_only"):
        return False
    return True


def render_g2_execution_envelope(
    *,
    task_id: str,
    repository: str,
    base_ref: str,
    base_sha: str,
    risk_profile: dict[str, object],
    bounded_read_scope: dict[str, object],
    bounded_write_scope: dict[str, object],
    scope_identity: dict[str, object],
    gate_state_resolution: dict[str, object],
    authority_boundary_decision: dict[str, object],
    evidence_map: dict[str, object],
    approval_request: dict[str, object],
    approval_validation: dict[str, object] | None,
    checkpoint: dict[str, object],
    rendered_at: str | None = None,
) -> dict[str, object]:
    """Render a closed G2 execution envelope (no execution side-effect)."""
    if not _SCOPE_HASH_RE.match(str(scope_identity.get("scope_hash", ""))):
        raise ValueError(
            f"{_REASON_SCOPE_MISMATCH}: scope_hash must be sha256:<64hex>"
        )
    scope_hash = str(scope_identity["scope_hash"])
    risk_class = str(risk_profile.get("risk_class", ""))
    risk_digest = str(risk_profile.get("risk_digest", ""))
    if not re.match(r"^R[0-9]$", risk_class):
        raise ValueError(f"{_REASON_SCOPE_MISMATCH}: risk_class invalid")
    if not _SCOPE_HASH_RE.match(risk_digest):
        raise ValueError(f"{_REASON_SCOPE_MISMATCH}: risk_digest invalid")

    # Normalize all required *structured* inputs to dicts up front so a malformed
    # (non-dict) required input fails closed at the gating branch below — never
    # raises on digestion. The original input objects are still passed to the
    # acceptance checks, which treat non-dicts as not-accepted.
    gate_state_resolution = gate_state_resolution if isinstance(gate_state_resolution, dict) else {}
    authority_boundary_decision = authority_boundary_decision if isinstance(authority_boundary_decision, dict) else {}
    evidence_map = evidence_map if isinstance(evidence_map, dict) else {}

    working_branch = str(bounded_write_scope.get("working_branch", ""))
    authorized_actions = tuple(bounded_write_scope.get("authorized_actions", []))
    excluded = ["G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"]

    inp = _EnvelopeInput(
        task_id=task_id,
        repository=repository,
        base_ref=base_ref,
        base_sha=base_sha,
        risk_class=risk_class,
        risk_digest=risk_digest,
        bounded_read_scope=tuple(bounded_read_scope.get("paths", [])),
        bounded_write_scope=tuple(bounded_write_scope.get("paths", [])),
        authorized_actions=authorized_actions,
        scope_hash=scope_hash,
        f1_artifact_digests=dict(evidence_map.get("f1_artifact_digests", {})),
        f2_digests={
            "gate_state_resolution": _digest(gate_state_resolution),
            "authority_boundary_decision": _digest(authority_boundary_decision),
        },
        checkpoint_id=str(checkpoint.get("checkpoint_id", "")),
        issued_at=str(approval_request.get("issued_at", "")),
        expires_at=str(approval_request.get("expires_at", "")),
        approval_request=dict(approval_request),
        approval_validation=dict(approval_validation) if isinstance(approval_validation, dict) else None,
        working_branch=working_branch,
    )

    issued_at = inp.issued_at
    expires_at = inp.expires_at
    now = rendered_at

    if _is_expired(issued_at, expires_at, now):
        activation_state = "EXPIRED"
        reason_code = _REASON_EXPIRED
    elif approval_validation is None:
        activation_state = "AWAITING_APPROVAL"
        reason_code = _REASON_AWAITING
    else:
        # ACTIVE requires (a) an exact, valid SCRUM-186 approval whose asserted
        # bindings match this envelope on every material axis, AND (b) each
        # required input in its canonical *accepted* state. Any missing,
        # ambiguous, mismatched, blocked, stale, drifted, or replay-conflicted
        # input fails closed to BLOCKED — never ACTIVE. This closes the
        # SCRUM-314 fail-closed gap flagged by independent review: a VALID
        # approval must not activate a usable envelope while gate_state/
        # authority/evidence inputs are blocking.
        av = approval_validation
        is_dict = isinstance(av, dict)
        valid = is_dict and av.get("outcome") == "VALID"
        scope_ok = bool(is_dict and str(av.get("scope_hash", "")) == scope_hash)
        _binding_fields = (
            ("task_id", task_id),
            ("repository", repository),
            ("base_sha", base_sha),
            ("working_branch", working_branch),
            ("risk_class", risk_class),
            ("authorized_actions", list(authorized_actions)),
        )
        binding_ok = True
        for _key, _expected in _binding_fields:
            if not is_dict or _key not in av or av[_key] != _expected:
                binding_ok = False
                break
        if not is_dict or "outcome" not in av:
            activation_state = "BLOCKED"
            reason_code = _REASON_AMBIGUOUS
        elif not valid:
            activation_state = "BLOCKED"
            reason_code = _REASON_BLOCKED
        elif not scope_ok:
            activation_state = "BLOCKED"
            reason_code = _REASON_SCOPE_MISMATCH
        elif not binding_ok:
            activation_state = "BLOCKED"
            reason_code = _REASON_BINDING_MISMATCH
        elif not _gate_state_accepted(gate_state_resolution):
            activation_state = "BLOCKED"
            reason_code = _REASON_GATE_STATE_BLOCKED
        elif not _authority_accepted(authority_boundary_decision):
            activation_state = "BLOCKED"
            reason_code = _REASON_AUTHORITY_BLOCKED
        elif not _evidence_accepted(evidence_map):
            activation_state = "BLOCKED"
            reason_code = _REASON_EVIDENCE_BLOCKED
        else:
            activation_state = "ACTIVE"
            reason_code = _REASON_ACTIVE

    # Digest covers every material binding so any material drift (base, branch,
    # scope, risk, actions, read/write scope) changes the envelope digest —
    # satisfying "digest changes on material drift" while staying replay-stable
    # for identical inputs.
    envelope_digest = _digest(
        task_id, repository, base_sha, scope_hash, activation_state,
        inp.checkpoint_id, issued_at, expires_at,
        working_branch, risk_class, list(authorized_actions),
        list(inp.bounded_read_scope), list(inp.bounded_write_scope),
        inp.f2_digests["gate_state_resolution"],
        inp.f2_digests["authority_boundary_decision"],
        _digest(
            evidence_map.get("outcome") if isinstance(evidence_map, dict) else None,
            evidence_map.get("reason_codes") if isinstance(evidence_map, dict) else None,
            evidence_map.get("missing_required") if isinstance(evidence_map, dict) else None,
            evidence_map.get("stale_required") if isinstance(evidence_map, dict) else None,
            evidence_map.get("projection_only") if isinstance(evidence_map, dict) else None,
        ),
    )

    return {
        "schema_version": _SCHEMA_VERSION,
        "artifact_type": _ARTIFACT_TYPE,
        "activation_state": activation_state,
        "task_id": task_id,
        "repository": repository,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "working_branch": working_branch,
        "risk_class": risk_class,
        "risk_digest": risk_digest,
        "bounded_read_scope": list(inp.bounded_read_scope),
        "bounded_write_scope": list(inp.bounded_write_scope),
        "authorized_actions": list(authorized_actions),
        "excluded_actions": [
            "open_draft_pr", "mark_pr_ready", "merge", "auto_merge",
            "force_push", "branch_deletion", "protected_branch_write",
            "deploy", "release", "production_data_change",
            "production_config_change", "g3_pr_promotion", "g4_merge",
            "g5_deploy", "g6_production",
        ],
        "scope_hash": scope_hash,
        "f1_artifact_digests": inp.f1_artifact_digests,
        "f2_digests": inp.f2_digests,
        "approval_request_ref": inp.approval_request,
        "approval_validation_ref": inp.approval_validation,
        "checkpoint_id": inp.checkpoint_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "reason_code": reason_code,
        "envelope_digest": envelope_digest,
        "exclusions": excluded,
        "execution_started": False,
    }
