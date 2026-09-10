"""Trusted G0 ContextSnapshot adapter for the Universal Run R1 seam.

Pure, transport-neutral and authority-neutral. It seals observed context into the
existing immutable record envelope; it never performs external reads or effects.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Mapping, Sequence

from tools.node_architect.universal_run_kernel import (
    UNIVERSAL_PROFILE,
    UniversalRunKernelError,
    seal_immutable_record,
    verify_record_digest,
)

_SOURCE_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise UniversalRunKernelError(code, detail)


def _text(value: Any, field: str) -> str:
    _require(isinstance(value, str) and bool(value) and value == value.strip(), "CONTEXT_SNAPSHOT_INVALID", field)
    _require("\r" not in value and "\n" not in value, "CONTEXT_SNAPSHOT_INVALID", field)
    return value


def _string_list(value: Any, field: str, *, non_empty: bool = False) -> list[str]:
    _require(isinstance(value, (list, tuple)), "CONTEXT_SNAPSHOT_INVALID", field)
    items = [_text(item, field) for item in value]
    if non_empty:
        _require(bool(items), "CONTEXT_SNAPSHOT_INVALID", field)
    return items


def _validate_source_bindings(value: Any) -> dict[str, Any]:
    _require(isinstance(value, Mapping), "CONTEXT_SOURCE_BINDING_INVALID")
    required = ("repository", "baseline_ref", "baseline_sha", "observed_at")
    for field in required:
        _require(field in value, "CONTEXT_SOURCE_BINDING_INVALID", field)
    repository = _text(value["repository"], "source_bindings.repository")
    baseline_ref = _text(value["baseline_ref"], "source_bindings.baseline_ref")
    baseline_sha = _text(value["baseline_sha"], "source_bindings.baseline_sha")
    observed_at = _text(value["observed_at"], "source_bindings.observed_at")
    _require(bool(_SOURCE_SHA_RE.fullmatch(baseline_sha)), "CONTEXT_SOURCE_BINDING_INVALID", "baseline_sha")
    return {
        "repository": repository,
        "baseline_ref": baseline_ref,
        "baseline_sha": baseline_sha,
        "observed_at": observed_at,
    }


def _validate_snapshot_payload(snapshot: Mapping[str, Any]) -> None:
    _text(snapshot.get("run_id"), "run_id")
    _require(snapshot.get("lifecycle_profile") == UNIVERSAL_PROFILE, "LIFECYCLE_PROFILE_UNSUPPORTED")
    _text(snapshot.get("objective"), "objective")
    _text(snapshot.get("consumer_or_parent_ref"), "consumer_or_parent_ref")
    _string_list(snapshot.get("context_refs"), "context_refs", non_empty=True)
    _require(isinstance(snapshot.get("scope"), Mapping) and bool(snapshot["scope"]), "CONTEXT_SNAPSHOT_INVALID", "scope")
    _require(isinstance(snapshot.get("candidate_target"), Mapping) and bool(snapshot["candidate_target"]), "CONTEXT_SNAPSHOT_INVALID", "candidate_target")
    _string_list(snapshot.get("constraints"), "constraints")

    authority = snapshot.get("authority_effect_boundary")
    _require(isinstance(authority, Mapping), "CONTEXT_AUTHORITY_BOUNDARY_INVALID")
    _require(authority.get("grants_authority") is False, "CONTEXT_AUTHORITY_GRANT_FORBIDDEN")
    _require(isinstance(authority.get("effects"), list), "CONTEXT_AUTHORITY_BOUNDARY_INVALID", "effects")

    _require(isinstance(snapshot.get("acceptance_boundary"), Mapping), "CONTEXT_SNAPSHOT_INVALID", "acceptance_boundary")
    _require(snapshot.get("execution_shape") in {"ATOMIC", "RECURSIVE"}, "CONTEXT_EXECUTION_SHAPE_INVALID")
    _validate_source_bindings(snapshot.get("source_bindings"))

    ambiguities = snapshot.get("ambiguities")
    _require(isinstance(ambiguities, list), "CONTEXT_AMBIGUITIES_INVALID")
    _require(all(isinstance(item, Mapping) for item in ambiguities), "CONTEXT_AMBIGUITIES_INVALID")
    _require(isinstance(snapshot.get("blocked"), bool), "CONTEXT_BLOCKED_INVALID")
    if ambiguities:
        _require(snapshot.get("blocked") is True, "CONTEXT_BLOCKING_AMBIGUITY")

    strength = snapshot.get("evidence_strength_ref")
    _require(isinstance(strength, Mapping), "CONTEXT_EVIDENCE_STRENGTH_REF_INVALID")
    _text(strength.get("kind"), "evidence_strength_ref.kind")
    _text(strength.get("ref"), "evidence_strength_ref.ref")
    _text(snapshot.get("created_at"), "created_at")
    _require(isinstance(snapshot.get("created_by"), Mapping), "CONTEXT_SNAPSHOT_INVALID", "created_by")


def create_context_snapshot(
    *,
    run_id: str,
    lifecycle_profile: Mapping[str, Any] | str,
    objective: str,
    consumer_or_parent_ref: str,
    context_refs: Sequence[str],
    scope: Mapping[str, Any],
    candidate_target: Mapping[str, Any],
    constraints: Sequence[str],
    authority_effect_boundary: Mapping[str, Any],
    acceptance_boundary: Mapping[str, Any],
    execution_shape: str,
    source_bindings: Mapping[str, Any],
    ambiguities: Sequence[Mapping[str, Any]],
    blocked: bool,
    evidence_strength_ref: Mapping[str, Any],
    created_at: str,
    created_by: Mapping[str, Any],
) -> dict[str, Any]:
    """Create one immutable, trusted-source-bound G0 ContextSnapshot."""
    normalized_sources = _validate_source_bindings(source_bindings)
    record = {
        "record_id": f"CTX:{run_id}",
        "schema_id": "gwc.universal-run.context-snapshot",
        "schema_version": 1,
        "run_id": run_id,
        "created_at": created_at,
        "created_by": copy.deepcopy(dict(created_by)),
        "lifecycle_profile": copy.deepcopy(lifecycle_profile),
        "provenance": {
            "predecessor_refs": [],
            "source_refs": list(context_refs)
            + [f"repo:{normalized_sources['repository']}@{normalized_sources['baseline_sha']}"],
        },
        "objective": objective,
        "consumer_or_parent_ref": consumer_or_parent_ref,
        "context_refs": list(context_refs),
        "scope": copy.deepcopy(dict(scope)),
        "candidate_target": copy.deepcopy(dict(candidate_target)),
        "constraints": list(constraints),
        "authority_effect_boundary": copy.deepcopy(dict(authority_effect_boundary)),
        "acceptance_boundary": copy.deepcopy(dict(acceptance_boundary)),
        "execution_shape": str(execution_shape).upper(),
        "source_bindings": normalized_sources,
        "ambiguities": copy.deepcopy(list(ambiguities)),
        "blocked": blocked,
        "evidence_strength_ref": copy.deepcopy(dict(evidence_strength_ref)),
    }
    _validate_snapshot_payload(record)
    return seal_immutable_record(record)


def verify_context_snapshot(snapshot: Mapping[str, Any]) -> bool:
    """Return True only for a semantically valid, untampered ContextSnapshot."""
    if not isinstance(snapshot, Mapping) or snapshot.get("schema_id") != "gwc.universal-run.context-snapshot":
        return False
    if not verify_record_digest(snapshot):
        return False
    try:
        _validate_snapshot_payload(snapshot)
    except (UniversalRunKernelError, TypeError, ValueError):
        return False
    return True


__all__ = ["create_context_snapshot", "verify_context_snapshot"]
