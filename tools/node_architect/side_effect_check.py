"""Replay-safe side-effect observation/readback readback decision for SCRUM-341.

NA81-F5 validation_quality.side-effect-check.

The node is intentionally data-only. It classifies validation-related external
observations / side effects through authoritative readback and never calls
providers or grants later-gate authority.

Classification outcomes
-----------------------
* confirmed           -- external observation confirmed via readback; stable.
* pending             -- observation not yet confirmed (fence active / awaited).
* failed              -- observation failed / readback contradicted expectation.
* unknown             -- outcome interrupted / not observed; MUST reconcile
                         before any retry (never silently replays to confirmed).
* duplicate-equivalent -- identical replay detected; effect MUST NOT be
                         duplicated (idempotency / fencing invariant).

Unknown/interrupted outcomes MUST reconcile before retry; an identical replay
MUST NOT duplicate effects. The function is pure, deterministic and replay-safe:
identical inputs yield an identical ``decision_digest`` and a replayed result is
returned verbatim from the cache without re-applying any effect.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, MutableMapping

NODE_ID = "validation_quality.side-effect-check"
PASS = "PASS"
BLOCKED = "BLOCKED"

# Canonical classification verdicts the node may emit for an observation.
VERDICT_CONFIRMED = "confirmed"
VERDICT_PENDING = "pending"
VERDICT_FAILED = "failed"
VERDICT_UNKNOWN = "unknown"
VERDICT_DUPLICATE = "duplicate-equivalent"

REASON_ORDER = (
    "OBSERVATIONS_INCOMPLETE",
    "OBSERVATION_MALFORMED",
    "OBSERVATION_PROVENANCE_MISSING",
    "OBSERVATION_PENDING",
    "OBSERVATION_FAILED",
    "READBACK_MISMATCH",
    "STALE_FENCE",
    "TIMEOUT_INTERRUPTED",
    "UNKNOWN_OUTCOME_UNRECONCILED",
    "DUPLICATE_EFFECT",
    "SIDE_EFFECTS_RESOLVED",
)
REASON_CODES = frozenset(REASON_ORDER)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(payload.get("task_id", "")).strip(),
        "repository": str(payload.get("repository", "")).strip(),
        "branch": str(payload.get("branch", "")).strip(),
        "base_sha": str(payload.get("base_sha", "")).strip(),
        "head_sha": str(payload.get("head_sha", "")).strip(),
        "scope_hash": str(payload.get("scope_hash", "")).strip(),
        "graph_revision": str(payload.get("graph_revision", "")).strip(),
        "idempotency_key": str(payload.get("idempotency_key", "")).strip(),
        "pr_number": payload.get("pr_number"),
    }


def _ordered(reasons: set[str]) -> list[str]:
    unknown = reasons.difference(REASON_CODES)
    if unknown:
        raise AssertionError(f"reason code escaped closed set: {sorted(unknown)}")
    return [code for code in REASON_ORDER if code in reasons]


def _authority_boundary() -> dict[str, bool]:
    return {
        "merge_authority_granted": False,
        "deployment_authority_granted": False,
        "production_authority_granted": False,
    }


def _classify_observation(obs: Mapping[str, Any], identity: Mapping[str, Any]) -> tuple[str, set[str]]:
    """Return (verdict, reasons) for one external observation/readback pair."""
    reasons: set[str] = set()

    required = ("effect_id", "observation_kind", "declared_intent")
    if any(not str(obs.get(field, "")).strip() for field in required):
        reasons.add("OBSERVATION_MALFORMED")
    for field in ("task_id", "repository", "head_sha", "scope_hash"):
        value = str(obs.get(field, "")).strip()
        if not value:
            reasons.add("OBSERVATION_PROVENANCE_MISSING")
        elif value != str(identity.get(field, "")):
            reasons.add("READBACK_MISMATCH" if field == "head_sha" else "OBSERVATION_PROVENANCE_MISSING")

    declared = str(obs.get("declared_intent", "")).strip().lower()
    verbatim = str(obs.get("verbatim_observation", "")).strip()
    status = str(obs.get("status", "")).strip().upper()
    interrupted = obs.get("interrupted") is True
    timeout = obs.get("timeout") is True
    readback = obs.get("authoritative_readback")
    readback_kind = str(obs.get("readback_kind", "")).strip().lower()

    # Idempotency / fencing: identical replay MUST NOT duplicate effects.
    if str(obs.get("duplicate_of", "")).strip() or obs.get("replay_equivalent") is True:
        if str(obs.get("effect_duplicate", "")).strip().lower() in ("true", "yes", "applied"):
            reasons.add("DUPLICATE_EFFECT")
        return VERDICT_DUPLICATE, reasons

    # Unknown / interrupted outcomes MUST reconcile before retry and never
    # silently become confirmed.
    if interrupted or timeout or status in ("UNKNOWN", "INTERRUPTED", "TIMEOUT"):
        return VERDICT_UNKNOWN, reasons

    # Stale fence: the readback was taken under an expired fence/scoped window.
    fence_expires_at = obs.get("fence_expires_at")
    evaluated_at = obs.get("evaluated_at")
    if fence_expires_at is not None and evaluated_at is not None:
        fence_ts = _parse_time(fence_expires_at)
        eval_ts = _parse_time(evaluated_at)
        if fence_ts is not None and eval_ts is not None and eval_ts > fence_ts:
            reasons.add("STALE_FENCE")

    # Authoritative readback (observed state) must match declared intent.
    verdict = VERDICT_PENDING
    if readback is not None:
        readback_text = str(readback).strip().lower()
        if verbatim and readback_text and readback_text != verbatim.lower():
            reasons.add("READBACK_MISMATCH")
        if declared and readback_text and readback_text != declared:
            reasons.add("READBACK_MISMATCH")
        if status == "FAILED" or str(obs.get("readback_status", "")).strip().upper() == "FAILED":
            verdict = VERDICT_FAILED
        elif status in ("PENDING", "AWAITED") or readback_kind == "pending":
            verdict = VERDICT_PENDING
        else:
            verdict = VERDICT_CONFIRMED
    elif readback_kind:
        # No readback but an authoritative one was expected -> pending.
        verdict = VERDICT_PENDING
    elif status == "PENDING":
        verdict = VERDICT_PENDING
    elif status == "FAILED":
        verdict = VERDICT_FAILED
    elif status == "CONFIRMED" and declared and verbatim:
        verdict = VERDICT_CONFIRMED
    else:
        # No authoritative readback and no confirmed signal -> pending (not
        # assumed confirmed; fail-closed visibility).
        verdict = VERDICT_PENDING

    if verdict == VERDICT_PENDING:
        reasons.add("OBSERVATION_PENDING")
    elif verdict == VERDICT_FAILED:
        reasons.add("OBSERVATION_FAILED")
    return verdict, reasons


def check_side_effects(
    evidence: Mapping[str, Any],
    *,
    replay_cache: MutableMapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate validation-related external observations and return a decision."""

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
        return {
            "schema_version": "1.0",
            "artifact_type": "side-effect-decision",
            "node_id": NODE_ID,
            **identity,
            "status": BLOCKED,
            "reason_codes": ["UNKNOWN_OUTCOME_UNRECONCILED"],
            "input_digest": input_digest,
            "decision_digest": _digest({"identity": identity, "reason_codes": ["UNKNOWN_OUTCOME_UNRECONCILED"]}),
            "verdicts": {},
            "replayed": False,
            **_authority_boundary(),
        }

    reasons: set[str] = set()

    required_text = ("task_id", "repository", "branch", "base_sha", "head_sha", "scope_hash", "graph_revision", "idempotency_key")
    if any(not identity[field] for field in required_text) or not isinstance(identity["pr_number"], int):
        reasons.add("OBSERVATIONS_INCOMPLETE")
    if identity["base_sha"] and not _SHA_RE.fullmatch(identity["base_sha"]):
        reasons.add("OBSERVATION_MALFORMED")
    if identity["head_sha"] and not _SHA_RE.fullmatch(identity["head_sha"]):
        reasons.add("OBSERVATION_MALFORMED")
    if identity["scope_hash"] and not _SCOPE_RE.fullmatch(identity["scope_hash"]):
        reasons.add("OBSERVATION_MALFORMED")

    observations = payload.get("observations")
    if not isinstance(observations, list) or not observations:
        reasons.add("OBSERVATIONS_INCOMPLETE")
        observations = []

    verdicts: dict[str, str] = {}
    for obs in observations:
        if not isinstance(obs, Mapping):
            reasons.add("OBSERVATION_MALFORMED")
            continue
        effect_id = str(obs.get("effect_id", "")).strip() or f"obs-{len(verdicts) + 1}"
        verdict, obs_reasons = _classify_observation(obs, identity)
        verdicts[effect_id] = verdict
        reasons |= obs_reasons

    # Unknown outcomes MUST reconcile before any retry: forbidden from PASS.
    if any(v == VERDICT_UNKNOWN for v in verdicts.values()):
        reasons.add("UNKNOWN_OUTCOME_UNRECONCILED")
    # Duplicate effects must never be re-applied.
    if any(v == VERDICT_DUPLICATE for v in verdicts.values()):
        reasons.add("DUPLICATE_EFFECT")

    if not reasons:
        reasons.add("SIDE_EFFECTS_RESOLVED")
    reason_codes = _ordered(reasons)
    status = PASS if reason_codes == ["SIDE_EFFECTS_RESOLVED"] else BLOCKED
    decision_basis = {
        "identity": identity,
        "status": status,
        "reason_codes": reason_codes,
        "verdicts": verdicts,
    }
    result = {
        "schema_version": "1.0",
        "artifact_type": "side-effect-decision",
        "node_id": NODE_ID,
        **identity,
        "status": status,
        "reason_codes": reason_codes,
        "input_digest": input_digest,
        "decision_digest": _digest(decision_basis),
        "verdicts": verdicts,
        "replayed": False,
        **_authority_boundary(),
    }
    if replay_cache is not None and cache_key:
        replay_cache[cache_key] = deepcopy(result)
    return result


__all__ = [
    "BLOCKED",
    "NODE_ID",
    "PASS",
    "REASON_CODES",
    "VERDICT_CONFIRMED",
    "VERDICT_DUPLICATE",
    "VERDICT_FAILED",
    "VERDICT_PENDING",
    "VERDICT_UNKNOWN",
    "check_side_effects",
]
