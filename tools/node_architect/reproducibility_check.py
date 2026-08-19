"""Reproducibility check for SCRUM-339 (node #274, NA81-F5).

The node descriptor is data-only (validation-quality-reproducibility-check):
it proves equivalent validation can be repeated from captured
tool/runtime/input/dependency/policy state, excluding only explicitly
declared volatile fields. Missing environment/toolchain evidence or
unexplained nondeterminism MUST NOT PASS.

This module implements ONLY the missing rerun comparison / difference-report
behaviour (predecessors SCRUM-335/#270 and SCRUM-336/#271 are already Done and
their evidence lives in current pre-prod). It is backward-compatible and
pure: no connector call, network request, filesystem mutation, Jira
transition, branch/PR action, approval, merge, deployment or production
operation.

The core ``check_reproducibility`` mirrors ``check_evidence_quality``
(SCRUM-215): deterministic digest, replay cache, closed reason-code set and an
explicit authority boundary (merge/deploy/production=False). The NA81 layer
(``check_reproducibility_na81``) reuses the core and surfaces the explicit
SCRUM-339 NA81-F5 guarantees, exactly as SCRUM-342 did for g3-pass-decision.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, MutableMapping

NODE_ID = "validation_quality.reproducibility-check"
PASS = "PASS"
BLOCKED = "BLOCKED"
REPRO_VOLATILE_DIFF = "REPRO_VOLATILE_DIFF"

# Hard-match dimensions: the validation must be reproducible from these.
# tool/input/dependency/policy/runtime/environment are all required to match;
# any drift (not declared volatile) blocks. environment additionally requires
# evidence presence -- a missing environment/toolchain capture MUST NOT PASS.
STABLE_DIMENSIONS = ("tool", "runtime", "input", "dependency", "policy", "environment")

REASON_ORDER = (
    "REPRO_REQUIRED_STATE_MISSING",
    "REPRO_ENVIRONMENT_EVIDENCE_MISSING",
    "REPRO_TOOL_DRIFT",
    "REPRO_INPUT_DRIFT",
    "REPRO_DEPENDENCY_DRIFT",
    "REPRO_POLICY_DRIFT",
    "REPRO_RUNTIME_DRIFT",
    "REPRO_ENVIRONMENT_DRIFT",
    "REPRO_NONDETERMINISM",
    "REPRO_VOLATILE_DIFF",
    "REPRO_ACCEPTED",
)
REASON_CODES = frozenset(REASON_ORDER)

# Map a stable dimension to its hard-drift reason code.
_DRIFT_REASON = {
    "tool": "REPRO_TOOL_DRIFT",
    "input": "REPRO_INPUT_DRIFT",
    "dependency": "REPRO_DEPENDENCY_DRIFT",
    "policy": "REPRO_POLICY_DRIFT",
    "runtime": "REPRO_RUNTIME_DRIFT",
    "environment": "REPRO_ENVIRONMENT_DRIFT",
}

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _identity(payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        field: str(payload.get(field, "")).strip()
        for field in (
            "task_id",
            "repository",
            "branch",
            "base_sha",
            "head_sha",
            "scope_hash",
            "graph_revision",
            "idempotency_key",
        )
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


def check_reproducibility(
    evidence: Mapping[str, Any],
    *,
    replay_cache: MutableMapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare a captured validation state against a rerun and decide reproducibility.

    Returns a stable, deterministic decision dict. The status is PASS only when
    the captured state was complete, environment/toolchain evidence was present,
    every stable (non-volatile) dimension matched the rerun, and the validation
    result was reproduced (no unexplained nondeterminism).
    """

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
            "artifact_type": "reproducibility-check",
            "node_id": NODE_ID,
            **identity,
            "status": BLOCKED,
            "reason_codes": ["REPRO_NONDETERMINISM", "REPRO_REQUIRED_STATE_MISSING"],
            "input_digest": input_digest,
            "repro_digest": _digest({"identity": identity, "conflict": True}),
            "replayed": False,
            **_authority_boundary(),
        }

    reasons: set[str] = set()

    # Identity / provenance completeness (mirrors evidence_quality_check).
    if any(not value for value in identity.values()):
        reasons.add("REPRO_REQUIRED_STATE_MISSING")
    if identity["base_sha"] and not _SHA_RE.fullmatch(identity["base_sha"]):
        reasons.add("REPRO_REQUIRED_STATE_MISSING")
    if identity["head_sha"] and not _SHA_RE.fullmatch(identity["head_sha"]):
        reasons.add("REPRO_REQUIRED_STATE_MISSING")
    if identity["scope_hash"] and not _SCOPE_RE.fullmatch(identity["scope_hash"]):
        reasons.add("REPRO_REQUIRED_STATE_MISSING")

    captured = payload.get("captured")
    rerun = payload.get("rerun")
    if not isinstance(captured, Mapping) or not isinstance(rerun, Mapping):
        reasons.add("REPRO_REQUIRED_STATE_MISSING")
        captured = captured if isinstance(captured, Mapping) else {}
        rerun = rerun if isinstance(rerun, Mapping) else {}

    # volatility is declared on the captured state; these dimensions may differ
    # without blocking (e.g. runtime wall-clock). environment is NEVER volatile:
    # missing/unmatched toolchain evidence is a hard fail.
    volatile = set(str(item).strip() for item in captured.get("volatile_fields", []) if str(item).strip())
    volatile &= set(STABLE_DIMENSIONS) - {"environment"}

    # environment/toolchain evidence must be present in BOTH captures.
    if not isinstance(captured.get("environment"), Mapping) or not captured["environment"]:
        reasons.add("REPRO_ENVIRONMENT_EVIDENCE_MISSING")
    if not isinstance(rerun.get("environment"), Mapping) or not rerun["environment"]:
        reasons.add("REPRO_ENVIRONMENT_EVIDENCE_MISSING")

    drift_present = False
    for dim in STABLE_DIMENSIONS:
        c_val = captured.get(dim)
        r_val = rerun.get(dim)
        if not isinstance(c_val, Mapping) or not isinstance(r_val, Mapping):
            # tool/input/dependency/policy/runtime are required state; missing
            # in a stable dimension is treated as required-state missing (except
            # environment which has its own explicit reason above).
            if dim != "environment":
                reasons.add("REPRO_REQUIRED_STATE_MISSING")
            continue
        if _digest(c_val) == _digest(r_val):
            continue
        if dim in volatile:
            reasons.add("REPRO_VOLATILE_DIFF")
            continue
        reasons.add(_DRIFT_REASON[dim])
        drift_present = True

    # Result reproducibility: captured result must equal rerun result unless a
    # hard drift already explains the difference. Unexplained result divergence
    # (even if only volatile fields differ) is nondeterminism -> MUST NOT PASS.
    c_result = captured.get("result_digest")
    r_result = rerun.get("result_digest")
    if not isinstance(c_result, str) or not isinstance(r_result, str):
        reasons.add("REPRO_REQUIRED_STATE_MISSING")
    elif c_result != r_result and not drift_present:
        reasons.add("REPRO_NONDETERMINISM")

    # PASS only when nothing beyond accepted/allowed-volatile remains. A run
    # whose only difference is a declared volatile field still ACCEPTED.
    blocking = reasons - {"REPRO_ACCEPTED", "REPRO_VOLATILE_DIFF"}
    if not blocking:
        reasons.add("REPRO_ACCEPTED")
    status = PASS if not blocking else BLOCKED

    repro_basis = {
        "identity": identity,
        "status": status,
        "reason_codes": _ordered(reasons),
        "captured_digest": _digest(captured),
        "rerun_digest": _digest(rerun),
        "volatile_fields": sorted(volatile),
        "environment_present": (
            isinstance(captured.get("environment"), Mapping)
            and bool(captured["environment"])
            and isinstance(rerun.get("environment"), Mapping)
            and bool(rerun["environment"])
        ),
    }
    result = {
        "schema_version": "1.0",
        "artifact_type": "reproducibility-check",
        "node_id": NODE_ID,
        **identity,
        "status": status,
        "reason_codes": _ordered(reasons),
        "input_digest": input_digest,
        "repro_digest": _digest(repro_basis),
        "volatile_fields": sorted(volatile),
        "replayed": False,
        **_authority_boundary(),
    }
    if replay_cache is not None and cache_key:
        replay_cache[cache_key] = deepcopy(result)
    return result


# --- SCRUM-339 (NA81-F5) bounded reproducibility-check -----------------
#
# NA81 extension over the existing ``check_reproducibility`` core. The base
# core performs the fail-closed reproducibility decision with a deterministic
# digest, replay cache and authority boundary (merge/deploy/production=False);
# this NA81 layer adds the explicit SCRUM-339 NA81-F5 guarantees required by
# the current NA81 brief that the core did not assert on its own surface:
#
#   * deterministic / replay idempotency -- identical inputs yield an identical
#     na81_repro_digest (na81.deterministic / na81.idempotent);
#   * explicit authority boundary -- no merge / approval / deployment /
#     production authority is granted (approval_authority_granted surfaced
#     False and the core authority boundary embedded);
#   * fail-closed -- if the core returns BLOCKED for any reproducibility
#     failure (drift, missing environment, nondeterminism) the NA81 result
#     stays BLOCKED (never silently passes; NA81_FAIL_CLOSED asserted);
#   * explicit non-authoritative guarantee with a stable repro_digest.
#
# Backward-compatible: ``check_reproducibility`` is unchanged and is reused as
# the core. The NA81 result embeds the core decision under ``decision`` and
# surfaces the NA81 assertions under ``na81``.
_NA81_BLOCKING_REASONS = frozenset(REASON_CODES - {"REPRO_ACCEPTED", "REPRO_VOLATILE_DIFF"})
_NA81_IDENTITY_FIELDS = (
    "task_id",
    "repository",
    "branch",
    "base_sha",
    "head_sha",
    "scope_hash",
    "graph_revision",
    "idempotency_key",
)


def check_reproducibility_na81(
    evidence: Mapping[str, Any],
    *,
    replay_cache: MutableMapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """NA81 reproducibility-check semantics over the check_reproducibility core (SCRUM-339).

    Reuses ``check_reproducibility`` as the fail-closed reproducibility core
    (VERIFIED_REUSE of the base renderer) and layers the explicit SCRUM-339
    NA81-F5 guarantees on top. Pure and read-only: no connector call, network
    request, filesystem mutation, Jira transition, branch/PR action, approval,
    merge, deployment or production operation. The returned ``decision`` is the
    closed, schema-valid ``reproducibility-check`` artifact; ``na81`` carries
    the explicit semantic guarantees.

    This function is mechanical only -- it does not and cannot perform any
    autonomous merge/main action. The PR targets pre-prod only; main is
    FORBIDDEN.
    """
    core = check_reproducibility(evidence, replay_cache=replay_cache)

    core_reasons = frozenset(core.get("reason_codes", []))
    blocking_present = bool(core_reasons & _NA81_BLOCKING_REASONS)

    na81_status = core["status"]
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
        "status": na81_status,
        "reason_codes": na81_reasons,
        "repro_digest": core["repro_digest"],
    }
    na81_repro_digest = _digest(na81_basis)

    return {
        "schema_version": "1.0",
        "artifact_type": "reproducibility-check-na81",
        "node_id": NODE_ID,
        **identity,
        "decision": core,
        "na81": na81,
        "status": na81_status,
        "reason_codes": na81_reasons,
        "input_digest": core["input_digest"],
        "repro_digest": core["repro_digest"],
        "na81_repro_digest": na81_repro_digest,
        "volatile_fields": core.get("volatile_fields", []),
        "replayed": bool(core.get("replayed", False)),
        **authority_boundary,
        "approval_authority_granted": False,
    }


__all__ = [
    "BLOCKED",
    "NODE_ID",
    "PASS",
    "REASON_CODES",
    "REPRO_VOLATILE_DIFF",
    "check_reproducibility",
    "check_reproducibility_na81",
]
