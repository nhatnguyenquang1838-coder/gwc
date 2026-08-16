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
_REASON_GATE_STATE_IDENTITY = "G2_ENVELOPE_GATE_STATE_IDENTITY_MISMATCH"
_REASON_AUTHORITY_IDENTITY = "G2_ENVELOPE_AUTHORITY_IDENTITY_MISMATCH"
_REASON_EVIDENCE_IDENTITY = "G2_ENVELOPE_EVIDENCE_IDENTITY_MISMATCH"

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


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
    """True iff gate_state_resolution is in its canonical *accepted* state AND
    the accepted status is provably G2-compatible. Only `PASS` is accepted; a
    generic `NOT_APPLICABLE` is never accepted by name alone — this G2 envelope
    cannot prove the action/gate semantics that would make it applicable, so it
    fails closed per the controller intercept. No drift, no replay conflict, no
    blockers."""
    if not isinstance(gs, dict):
        return False
    if gs.get("gate_status") != "PASS":
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
    """True iff authority_boundary_decision permits execution AND the accepted
    decision is provably G2-compatible. Only `REQUIRE_APPROVAL`/`ALLOW_PREPARATION`
    are accepted; a generic `NOT_APPLICABLE` is never accepted by name alone (no
    proof of G2 applicability) -> fail closed. Not prohibited, not replay/stale
    conflict."""
    if not isinstance(ab, dict):
        return False
    if ab.get("decision") not in ("REQUIRE_APPROVAL", "ALLOW_PREPARATION"):
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


def _gate_state_identity_ok(gs: object, *, task_id: str, repository: str,
                            base_sha: str, scope_hash: str) -> bool:
    """Smallest canonical identity projection gate_state_resolution must carry to
    prove it belongs to THIS envelope, grounded in its real top-level keys
    (task_id, repository, current_base_sha, scope_hash). A PASS with missing or
    foreign identity fields is malformed/ambiguous -> False."""
    if not isinstance(gs, dict):
        return False
    if not gs.get("task_id") or gs.get("task_id") != task_id:
        return False
    if not gs.get("repository") or gs.get("repository") != repository:
        return False
    if not gs.get("current_base_sha") or gs.get("current_base_sha") != base_sha:
        return False
    if not gs.get("scope_hash") or gs.get("scope_hash") != scope_hash:
        return False
    return True


def _authority_identity_ok(ab: object, *, task_id: str, repository: str,
                           base_sha: str, scope_hash: str, risk_class: str,
                           authorized_actions: tuple[str, ...],
                           working_branch: str = "") -> bool:
    """authority_boundary_decision identity — strict per canonical
    authority-boundary-decision schema (controller micro-intercept 121a).

    The canonical schema REQUIRES top-level `risk_class` and `scope_identity`, and
    the nested `scope_identity` REQUIRES task_id/repository/base_sha/head_sha/
    scope_hash/authorized_actions. Every one of those must be present and the
    identity-bearing ones must match THIS envelope exactly. The embedded
    `head_sha` is validated as a real producer-shaped 40-hex commit (never
    compared to an invented envelope head — the renderer has no head binding).
    `authorized_actions` must be EXACTLY the envelope's authorized actions
    (order-normalized): a subset would be an authority *expansion* (granting
    fewer than the envelope is allowed — not an identity), a superset an
    over-privilege; both are rejected. `working_branch` is optional in the
    schema, so absence is allowed, but when present it must equal the envelope
    branch."""
    if not isinstance(ab, dict):
        return False
    # Top-level canonical identity (all required, exact match).
    if not ab.get("task_id") or ab.get("task_id") != task_id:
        return False
    if not ab.get("repository") or ab.get("repository") != repository:
        return False
    if not ab.get("current_base_sha") or ab.get("current_base_sha") != base_sha:
        return False
    if not ab.get("scope_hash") or ab.get("scope_hash") != scope_hash:
        return False
    # Top-level risk_class is required and must equal the envelope risk_class.
    rc = ab.get("risk_class")
    if rc != risk_class:
        return False
    # scope_identity is required and must be a dict.
    si = ab.get("scope_identity")
    if not isinstance(si, dict):
        return False
    # Nested canonical identity — all keys required, exact match.
    if not si.get("task_id") or si.get("task_id") != task_id:
        return False
    if not si.get("repository") or si.get("repository") != repository:
        return False
    if not si.get("base_sha") or si.get("base_sha") != base_sha:
        return False
    if not si.get("scope_hash") or si.get("scope_hash") != scope_hash:
        return False
    # head_sha is required and must be a real producer-shaped 40-hex commit;
    # validated for shape only (the renderer has no head binding to compare to).
    hs = si.get("head_sha")
    if not isinstance(hs, str) or not _SHA40_RE.match(hs):
        return False
    # working_branch is optional in the schema: absent allowed; present => exact.
    wb = si.get("working_branch")
    if wb is not None and wb != working_branch:
        return False
    # authorized_actions required and EXACTLY the envelope's (order-normalized).
    acts = si.get("authorized_actions")
    if not isinstance(acts, (list, tuple)):
        return False
    exp = list(authorized_actions)
    if sorted(acts) != sorted(exp):
        return False
    return True


def _evidence_identity_ok(em: object, *, task_id: str, repository: str,
                          base_sha: str) -> bool:
    """Smallest canonical identity projection evidence_artifact_map must carry
    (top-level task_id, repository, base_sha — the ONLY identity keys the producer
    emits; it exposes no top-level scope_hash and head_sha is not bound for this
    G2 map). A READY map with missing/foreign task/repo/base binding is
    stale/foreign -> False. Scope mismatch is already reflected by the canonical
    map's own BLOCKED/reason when correctly constructed."""
    if not isinstance(em, dict):
        return False
    if not em.get("task_id") or em.get("task_id") != task_id:
        return False
    if not em.get("repository") or em.get("repository") != repository:
        return False
    if not em.get("base_sha") or em.get("base_sha") != base_sha:
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
    if not _SHA256_RE.match(str(scope_identity.get("scope_hash", ""))):
        raise ValueError(
            f"{_REASON_SCOPE_MISMATCH}: scope_hash must be sha256:<64hex>"
        )
    scope_hash = str(scope_identity["scope_hash"])
    risk_class = str(risk_profile.get("risk_class", ""))
    risk_digest = str(risk_profile.get("risk_digest", ""))
    if not re.match(r"^R[0-9]$", risk_class):
        raise ValueError(f"{_REASON_SCOPE_MISMATCH}: risk_class invalid")
    if not _SHA256_RE.match(risk_digest):
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
        elif not _gate_state_identity_ok(
            gate_state_resolution,
            task_id=task_id, repository=repository, base_sha=base_sha, scope_hash=scope_hash,
        ):
            activation_state = "BLOCKED"
            reason_code = _REASON_GATE_STATE_IDENTITY
        elif not _authority_identity_ok(
            authority_boundary_decision,
            task_id=task_id, repository=repository, base_sha=base_sha,
            scope_hash=scope_hash, risk_class=risk_class, authorized_actions=authorized_actions,
            working_branch=working_branch,
        ):
            activation_state = "BLOCKED"
            reason_code = _REASON_AUTHORITY_IDENTITY
        elif not _evidence_identity_ok(
            evidence_map,
            task_id=task_id, repository=repository, base_sha=base_sha,
        ):
            activation_state = "BLOCKED"
            reason_code = _REASON_EVIDENCE_IDENTITY
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
        # Identity projection of each required input: foreign/stale identity must
        # change the digest (task/repo/base for gate+evidence; task/repo/base/
        # scope/risk/branch/actions for authority). Grounded in each producer's
        # real emitted identity keys — evidence has no scope_hash, so omitted.
        _digest(
            _canon(gate_state_resolution.get("task_id")) if isinstance(gate_state_resolution, dict) else None,
            _canon(gate_state_resolution.get("repository")) if isinstance(gate_state_resolution, dict) else None,
            _canon(gate_state_resolution.get("current_base_sha")) if isinstance(gate_state_resolution, dict) else None,
            _canon(gate_state_resolution.get("scope_hash")) if isinstance(gate_state_resolution, dict) else None,
        ),
        _digest(
            _canon(authority_boundary_decision.get("task_id")) if isinstance(authority_boundary_decision, dict) else None,
            _canon(authority_boundary_decision.get("repository")) if isinstance(authority_boundary_decision, dict) else None,
            _canon(authority_boundary_decision.get("current_base_sha")) if isinstance(authority_boundary_decision, dict) else None,
            _canon(authority_boundary_decision.get("scope_hash")) if isinstance(authority_boundary_decision, dict) else None,
            _canon(authority_boundary_decision.get("risk_class")) if isinstance(authority_boundary_decision, dict) else None,
            _canon(authority_boundary_decision.get("scope_identity")) if isinstance(authority_boundary_decision, dict) else None,
        ),
        _digest(
            _canon(evidence_map.get("task_id")) if isinstance(evidence_map, dict) else None,
            _canon(evidence_map.get("repository")) if isinstance(evidence_map, dict) else None,
            _canon(evidence_map.get("base_sha")) if isinstance(evidence_map, dict) else None,
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
