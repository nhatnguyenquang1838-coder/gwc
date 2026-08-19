"""Replay-safe final G3 decision for SCRUM-219."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Mapping, MutableMapping

NODE_ID = "validation_quality.g3-pass-decision"
G3_PASS = "G3_PASS"
G3_CHANGES_REQUIRED = "G3_CHANGES_REQUIRED"
G3_BLOCKED = "G3_BLOCKED"
G3_INCONCLUSIVE = "G3_INCONCLUSIVE"

REASON_ORDER = (
    "REQUIRED_EVIDENCE_MISSING",
    "EVIDENCE_REJECTED",
    "CI_NOT_SUCCESS",
    "REVIEW_STALE",
    "HEAD_DRIFT",
    "UNRESOLVED_BLOCKER",
    "SIDE_EFFECT_UNRESOLVED",
    "G3_CHANGES_REQUIRED",
    "G3_BLOCKED",
    "G3_INCONCLUSIVE",
    "G3_PASS",
)
REASON_CODES = frozenset(REASON_ORDER)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _authority_boundary() -> dict[str, bool]:
    return {"merge_authority_granted": False, "deployment_authority_granted": False, "production_authority_granted": False}


def _identity(payload: Mapping[str, Any]) -> dict[str, str]:
    return {field: str(payload.get(field, "")).strip() for field in ("task_id", "repository", "branch", "base_sha", "head_sha", "scope_hash", "graph_revision", "policy_digest", "idempotency_key")}


def _ordered(reasons: set[str]) -> list[str]:
    unknown = reasons.difference(REASON_CODES)
    if unknown:
        raise AssertionError(f"reason code escaped closed set: {sorted(unknown)}")
    return [code for code in REASON_ORDER if code in reasons]


def decide_g3_pass(evidence: Mapping[str, Any], *, replay_cache: MutableMapping[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = deepcopy(dict(evidence))
    identity = _identity(payload)
    input_digest = _digest(payload)
    cache_key = identity["idempotency_key"]

    if replay_cache is not None and cache_key and cache_key in replay_cache:
        cached = replay_cache[cache_key]
        if cached.get("input_digest") == input_digest:
            replay = deepcopy(cached)
            replay["replayed"] = True
            return replay
        return {"schema_version": "1.0", "artifact_type": "g3-pass-decision", "node_id": NODE_ID, **identity, "outcome": G3_BLOCKED, "reason_codes": ["EVIDENCE_REJECTED", "G3_BLOCKED"], "input_digest": input_digest, "decision_digest": _digest({"identity": identity, "outcome": G3_BLOCKED, "conflict": True}), "transition_effect_applied": False, "replayed": False, **_authority_boundary()}

    reasons: set[str] = set()
    if any(not value for value in identity.values()):
        reasons.add("REQUIRED_EVIDENCE_MISSING")
    if identity["base_sha"] and not _SHA_RE.fullmatch(identity["base_sha"]):
        reasons.add("EVIDENCE_REJECTED")
    if identity["head_sha"] and not _SHA_RE.fullmatch(identity["head_sha"]):
        reasons.add("EVIDENCE_REJECTED")
    if identity["scope_hash"] and not _SCOPE_RE.fullmatch(identity["scope_hash"]):
        reasons.add("EVIDENCE_REJECTED")

    quality = payload.get("evidence_quality_decision")
    if not isinstance(quality, Mapping):
        quality = {}
        reasons.add("REQUIRED_EVIDENCE_MISSING")
    if quality.get("status") != "PASS" or quality.get("reason_codes") != ["EVIDENCE_ACCEPTED"]:
        reasons.add("EVIDENCE_REJECTED")
    for field in ("task_id", "repository", "branch", "head_sha", "scope_hash", "graph_revision"):
        value = str(quality.get(field, "")).strip()
        if not value:
            reasons.add("REQUIRED_EVIDENCE_MISSING")
        elif value != identity[field]:
            reasons.add("HEAD_DRIFT" if field == "head_sha" else "EVIDENCE_REJECTED")

    validations = payload.get("validations")
    if not isinstance(validations, list) or not validations:
        reasons.add("REQUIRED_EVIDENCE_MISSING")
        validations = []
    for validation in validations:
        if not isinstance(validation, Mapping):
            reasons.add("EVIDENCE_REJECTED")
            continue
        if str(validation.get("status", "")).upper() != "PASS":
            reasons.add("CI_NOT_SUCCESS")
        if str(validation.get("head_sha", "")) != identity["head_sha"]:
            reasons.add("HEAD_DRIFT")
        if str(validation.get("scope_hash", "")) != identity["scope_hash"]:
            reasons.add("EVIDENCE_REJECTED")

    ready = payload.get("ready_for_review")
    if not isinstance(ready, Mapping):
        ready = {}
        reasons.add("REQUIRED_EVIDENCE_MISSING")
    if ready.get("eligible") is not True:
        reasons.add("REQUIRED_EVIDENCE_MISSING")
    if str(ready.get("head_sha", "")) != identity["head_sha"]:
        reasons.add("HEAD_DRIFT")
    if ready.get("scope_drift") is True:
        reasons.add("HEAD_DRIFT")
    if int(ready.get("unresolved_threads", 0) or 0) != 0:
        reasons.add("UNRESOLVED_BLOCKER")

    if payload.get("review_stale") is True:
        reasons.add("REVIEW_STALE")
    if payload.get("head_drift") is True or payload.get("graph_drift") is True or payload.get("policy_drift") is True:
        reasons.add("HEAD_DRIFT")
    if payload.get("side_effects_unresolved") is True:
        reasons.add("SIDE_EFFECT_UNRESOLVED")

    for finding in payload.get("findings") or []:
        if not isinstance(finding, Mapping):
            reasons.add("EVIDENCE_REJECTED")
            continue
        if str(finding.get("status", "OPEN")).upper() == "CLOSED":
            continue
        severity = str(finding.get("severity", "BLOCKER")).upper()
        if severity == "BLOCKER" or (severity == "MAJOR" and finding.get("risk_acceptance") is not True):
            reasons.add("UNRESOLVED_BLOCKER")

    if "REQUIRED_EVIDENCE_MISSING" in reasons or "EVIDENCE_REJECTED" in reasons or "HEAD_DRIFT" in reasons:
        outcome = G3_BLOCKED
        reasons.add("G3_BLOCKED")
    elif "CI_NOT_SUCCESS" in reasons or "REVIEW_STALE" in reasons:
        outcome = G3_INCONCLUSIVE
        reasons.add("G3_INCONCLUSIVE")
    elif "UNRESOLVED_BLOCKER" in reasons or "SIDE_EFFECT_UNRESOLVED" in reasons:
        outcome = G3_CHANGES_REQUIRED
        reasons.add("G3_CHANGES_REQUIRED")
    else:
        outcome = G3_PASS
        reasons.add("G3_PASS")

    reason_codes = _ordered(reasons)
    decision_basis = {"identity": identity, "outcome": outcome, "reason_codes": reason_codes, "quality_digest": quality.get("quality_digest"), "validation_digests": [item.get("digest") for item in validations if isinstance(item, Mapping)], "ready_for_review": dict(ready)}
    result = {"schema_version": "1.0", "artifact_type": "g3-pass-decision", "node_id": NODE_ID, **identity, "outcome": outcome, "reason_codes": reason_codes, "input_digest": input_digest, "decision_digest": _digest(decision_basis), "transition_effect_applied": outcome == G3_PASS, "replayed": False, **_authority_boundary()}
    if replay_cache is not None and cache_key:
        replay_cache[cache_key] = deepcopy(result)
    return result


# --- SCRUM-342 (NA81-F5-N09) bounded g3-pass-decision -----------------
#
# NA81 extension over the existing ``decide_g3_pass`` renderer (SCRUM-219).
# The base renderer performs the fail-closed G3 decision with a deterministic
# digest, replay cache and authority boundary (merge/deploy/production=False);
# this NA81 layer adds the explicit SCRUM-342 semantics required by the current
# NA81-F5-N09 brief that the core did not assert on its own surface:
#
#   * deterministic / replay idempotency -- identical inputs yield an identical
#     na81_decision_digest (na81.deterministic / na81.idempotent);
#   * explicit authority boundary -- no merge / approval / deployment /
#     production authority is granted (approval_authority_granted surfaced
#     False and the core authority boundary embedded);
#   * fail-closed -- if the core returns a non-PASS outcome caused by
#     EVIDENCE_REJECTED / HEAD_DRIFT / REQUIRED_EVIDENCE_MISSING the NA81
#     result stays BLOCKED (never silently passes);
#   * explicit non-authoritative guarantee with a stable decision_digest.
#
# Backward-compatible: ``decide_g3_pass`` is unchanged and is reused as the
# core. The NA81 result embeds the core decision under ``decision`` and surfaces
# the NA81 assertions under ``na81``.
_NA81_BLOCKING_REASONS = frozenset({"EVIDENCE_REJECTED", "HEAD_DRIFT", "REQUIRED_EVIDENCE_MISSING"})
_NA81_IDENTITY_FIELDS = (
    "task_id", "repository", "branch", "base_sha", "head_sha",
    "scope_hash", "graph_revision", "policy_digest", "idempotency_key",
)


def decide_g3_pass_na81(
    evidence: Mapping[str, Any],
    *,
    replay_cache: MutableMapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """NA81 g3-pass-decision semantics over the decide_g3_pass core (SCRUM-342).

    Reuses ``decide_g3_pass`` as the fail-closed G3 decision core (VERIFIED_REUSE
    of the SCRUM-219 renderer) and layers the explicit SCRUM-342 NA81-F5-N09
    guarantees on top. Pure and read-only: no connector call, network request,
    filesystem mutation, Jira transition, branch/PR action, approval, merge,
    deployment or production operation. The returned ``decision`` is the closed,
    schema-valid ``g3-pass-decision`` artifact; ``na81`` carries the explicit
    semantic guarantees.

    G3 PASS never grants merge authority; standing pre-prod authority is
    evaluated separately. This function is mechanical only -- it does not and
    cannot perform any autonomous merge/main action.
    """
    core = decide_g3_pass(evidence, replay_cache=replay_cache)

    core_reasons = frozenset(core.get("reason_codes", []))
    blocking_present = bool(core_reasons & _NA81_BLOCKING_REASONS)

    # Fail-closed: NA81 never upgrades a blocked decision to PASS, and any
    # evidence-blocking reason keeps the decision BLOCKED (never silently pass).
    na81_outcome = core["outcome"]
    if blocking_present:
        na81_outcome = G3_BLOCKED
    na81_reasons = list(core["reason_codes"])
    if blocking_present and "NA81_FAIL_CLOSED" not in na81_reasons:
        na81_reasons = sorted(set(na81_reasons) | {"NA81_FAIL_CLOSED"})

    identity = {field: core.get(field, "") for field in _NA81_IDENTITY_FIELDS}
    authority_boundary = _authority_boundary()

    na81 = {
        "deterministic": True,
        "idempotent": True,
        "fail_closed": bool(blocking_present),
        "non_authoritative": True,
        "approval_authority_granted": False,
        "authority_boundary": authority_boundary,
    }

    na81_basis = {
        "identity": identity,
        "outcome": na81_outcome,
        "reason_codes": na81_reasons,
        "decision_digest": core["decision_digest"],
    }
    na81_decision_digest = _digest(na81_basis)

    return {
        "schema_version": "1.0",
        "artifact_type": "g3-pass-decision-na81",
        "node_id": NODE_ID,
        **identity,
        "decision": core,
        "na81": na81,
        "outcome": na81_outcome,
        "reason_codes": na81_reasons,
        "input_digest": core["input_digest"],
        "decision_digest": core["decision_digest"],
        "na81_decision_digest": na81_decision_digest,
        "transition_effect_applied": False,
        "replayed": bool(core.get("replayed", False)),
        **authority_boundary,
        "approval_authority_granted": False,
    }


__all__ = ["G3_BLOCKED", "G3_CHANGES_REQUIRED", "G3_INCONCLUSIVE", "G3_PASS", "NODE_ID", "REASON_CODES", "decide_g3_pass", "decide_g3_pass_na81"]
