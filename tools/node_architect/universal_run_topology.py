"""Universal Run E3: pure recursive topology and ChildRun materialization semantics.

This module deliberately excludes RuntimePlan compilation, persistence, authority,
and external effects. All immutable records reuse the E1/E2 record-envelope seal
and digest verification primitives.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Iterable, Mapping, Sequence

from tools.node_architect.universal_run_kernel import (
    TERMINAL_STATES,
    UNIVERSAL_PROFILE,
    UniversalRunKernelError,
    seal_immutable_record,
    verify_record_digest,
)

RUN_KINDS = {"ROOT", "CHILD"}
NODE_KINDS = {"WORK", "CONTROL"}
REQUIREMENT_KINDS = {"REQUIRED", "OPTIONAL", "CONDITIONAL"}
CHILD_INSTANCE_POLICY = "SINGLE_ACTIVE"
MATERIALIZATION_REASONS = {"INITIAL", "RERUN_SUBTREE"}
INDEPENDENT_BOUNDARY_REASONS = {
    "INDEPENDENT_CONSUMER",
    "INDEPENDENT_ACCEPTANCE",
    "INDEPENDENT_TARGET",
    "INDEPENDENT_HANDOFF",
    "INDEPENDENT_AUTHORITY",
    "INDEPENDENT_EVIDENCE",
    "GOVERNED_RETRY_BOUNDARY",
}


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise UniversalRunKernelError(code, detail)


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _canonical_reference(value: Any, code: str, detail: str) -> str:
    _require(isinstance(value, str), code, detail)
    _require(bool(value) and value == value.strip(), code, detail)
    _require("\r" not in value and "\n" not in value, code, detail)
    return value


def _normalize_revision(value: Any) -> int:
    if isinstance(value, bool):
        _require(False, "RUN_MANIFEST_REVISION_INVALID", "revision")
    if isinstance(value, int):
        revision = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        revision = int(value)
    else:
        _require(False, "RUN_MANIFEST_REVISION_INVALID", "revision")
        revision = 0
    _require(revision >= 1, "RUN_MANIFEST_REVISION_INVALID", "revision")
    return revision


def _base_record(
    *,
    record_id: str,
    schema_id: str,
    run_id: str,
    created_at: str,
    created_by: Mapping[str, Any],
    source_refs: Iterable[str] = (),
    predecessor_refs: Iterable[str] = (),
) -> dict[str, Any]:
    record_id = _canonical_reference(record_id, "RECORD_ENVELOPE_INVALID", "record_id")
    run_id = _canonical_reference(run_id, "RECORD_ENVELOPE_INVALID", "run_id")
    _require(_non_empty_string(created_at), "RECORD_ENVELOPE_INVALID", "created_at")
    _require(isinstance(created_by, Mapping), "RECORD_ENVELOPE_INVALID", "created_by")
    return {
        "record_id": record_id,
        "schema_id": schema_id,
        "schema_version": 1,
        "run_id": run_id,
        "created_at": created_at,
        "created_by": copy.deepcopy(dict(created_by)),
        "lifecycle_profile": dict(UNIVERSAL_PROFILE),
        "provenance": {
            "predecessor_refs": list(predecessor_refs),
            "source_refs": list(source_refs),
        },
    }


def create_run_manifest_revision(
    *,
    record_id: str,
    run_id: str,
    revision: int,
    run_kind: str,
    created_at: str,
    created_by: Mapping[str, Any],
    parent_run_ref: str | None = None,
    invoking_node_allocation_ref: str | None = None,
    source_refs: Iterable[str] = (),
    predecessor_refs: Iterable[str] = (),
) -> dict[str, Any]:
    """Create a sealed ROOT/CHILD RunManifestRevision.

    ROOT/CHILD is the lineage dimension only. Atomicity is intentionally not
    represented here because it belongs to RuntimePlan/compiler semantics.
    """
    run_kind = str(run_kind).upper()
    _require(run_kind in RUN_KINDS, "RUN_KIND_UNKNOWN", run_kind)
    revision = _normalize_revision(revision)

    if run_kind == "ROOT":
        _require(parent_run_ref is None and invoking_node_allocation_ref is None, "ROOT_LINEAGE_INVALID")
    else:
        parent_run_ref = _canonical_reference(parent_run_ref, "CHILD_LINEAGE_INVALID", "parent_run_ref")
        invoking_node_allocation_ref = _canonical_reference(
            invoking_node_allocation_ref, "CHILD_LINEAGE_INVALID", "invoking_node_allocation_ref"
        )
        _require(run_id != parent_run_ref, "CHILD_PARENT_SELF_LOOP")

    record = _base_record(
        record_id=record_id,
        schema_id="gwc.universal-run.run-manifest-revision",
        run_id=run_id,
        created_at=created_at,
        created_by=created_by,
        source_refs=source_refs,
        predecessor_refs=predecessor_refs,
    )
    record.update(
        {
            "revision": revision,
            "run_kind": run_kind,
            "parent_run_ref": parent_run_ref,
            "invoking_node_allocation_ref": invoking_node_allocation_ref,
        }
    )
    return seal_immutable_record(record)


def _normalize_boundary_reasons(reasons: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in reasons:
        reason = str(raw).upper()
        _require(reason in INDEPENDENT_BOUNDARY_REASONS, "INDEPENDENT_BOUNDARY_REASON_UNKNOWN", reason)
        if reason not in seen:
            seen.add(reason)
            normalized.append(reason)
    return sorted(normalized)


def validate_node_allocation(
    allocation: Mapping[str, Any],
    *,
    independent_boundary_reasons: Iterable[str] | None = None,
) -> None:
    """Fail closed on structural/semantic NodeAllocation violations.

    The caller may supply currently observed independent governance boundaries.
    E3 never mutates CONTROL to WORK; it emits CONTROL_REQUIRES_WORK instead.
    """
    _require(isinstance(allocation, Mapping), "NODE_ALLOCATION_INVALID")
    if "content_digest" in allocation:
        _require(verify_record_digest(allocation), "NODE_ALLOCATION_DIGEST_INVALID")

    _canonical_reference(allocation.get("record_id"), "RECORD_ENVELOPE_INVALID", "record_id")
    _canonical_reference(allocation.get("run_id"), "RECORD_ENVELOPE_INVALID", "run_id")

    kind = str(allocation.get("kind", "")).upper()
    requirement = str(allocation.get("requirement", "")).upper()
    policy = allocation.get("child_instance_policy")
    _require(kind in NODE_KINDS, "NODE_KIND_UNKNOWN", kind)
    _require(requirement in REQUIREMENT_KINDS, "NODE_REQUIREMENT_UNKNOWN", requirement)
    _require(policy == CHILD_INSTANCE_POLICY, "CHILD_INSTANCE_POLICY_UNSUPPORTED", str(policy))
    _canonical_reference(allocation.get("node_allocation_id"), "NODE_ALLOCATION_ID_INVALID", "node_allocation_id")

    stored_reasons = allocation.get("independent_boundary_reasons", [])
    _require(isinstance(stored_reasons, list), "INDEPENDENT_BOUNDARY_REASONS_INVALID")
    normalized_stored_reasons = _normalize_boundary_reasons(stored_reasons)
    if independent_boundary_reasons is not None:
        normalized_override = _normalize_boundary_reasons(independent_boundary_reasons)
        if "content_digest" in allocation:
            _require(
                normalized_override == normalized_stored_reasons,
                "INDEPENDENT_BOUNDARY_OVERRIDE_MISMATCH",
            )
        effective_reasons = normalized_override
    else:
        effective_reasons = normalized_stored_reasons

    if kind == "CONTROL":
        _canonical_reference(
            allocation.get("control_justification"),
            "CONTROL_JUSTIFICATION_REQUIRED",
            "control_justification",
        )
        _require(not effective_reasons, "CONTROL_REQUIRES_WORK", ",".join(effective_reasons))
    elif allocation.get("control_justification") is not None:
        _canonical_reference(
            allocation.get("control_justification"),
            "CONTROL_JUSTIFICATION_INVALID",
            "control_justification",
        )

    if requirement == "CONDITIONAL":
        _canonical_reference(allocation.get("condition_ref"), "CONDITION_REF_REQUIRED", "condition_ref")
    elif allocation.get("condition_ref") is not None:
        _canonical_reference(
            allocation.get("condition_ref"),
            "CONDITION_REF_INVALID",
            "condition_ref",
        )


def create_node_allocation(
    *,
    record_id: str,
    run_id: str,
    node_allocation_id: str,
    kind: str,
    requirement: str,
    created_at: str,
    created_by: Mapping[str, Any],
    child_instance_policy: str = CHILD_INSTANCE_POLICY,
    condition_ref: str | None = None,
    control_justification: str | None = None,
    independent_boundary_reasons: Iterable[str] = (),
    source_refs: Iterable[str] = (),
    predecessor_refs: Iterable[str] = (),
) -> dict[str, Any]:
    reasons = _normalize_boundary_reasons(independent_boundary_reasons)
    record = _base_record(
        record_id=record_id,
        schema_id="gwc.universal-run.node-allocation",
        run_id=run_id,
        created_at=created_at,
        created_by=created_by,
        source_refs=source_refs,
        predecessor_refs=predecessor_refs,
    )
    record.update(
        {
            "node_allocation_id": node_allocation_id,
            "kind": str(kind).upper(),
            "requirement": str(requirement).upper(),
            "condition_ref": condition_ref,
            "control_justification": control_justification,
            "independent_boundary_reasons": reasons,
            "child_instance_policy": child_instance_policy,
        }
    )
    validate_node_allocation(record)
    return seal_immutable_record(record)


def _normalize_generation_states(states: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    generations: set[int] = set()
    child_refs: set[str] = set()
    for state in states:
        _require(isinstance(state, Mapping), "CHILD_GENERATION_STATE_INVALID")
        child_ref = _canonical_reference(
            state.get("child_run_ref"), "CHILD_GENERATION_STATE_INVALID", "child_run_ref"
        )
        generation = state.get("generation")
        terminal_state = str(state.get("terminal_state", "")).upper()
        if isinstance(generation, bool):
            _require(False, "CHILD_GENERATION_STATE_INVALID", "generation")
        if isinstance(generation, int):
            normalized_generation = generation
        elif isinstance(generation, float) and generation.is_integer():
            normalized_generation = int(generation)
        else:
            _require(False, "CHILD_GENERATION_STATE_INVALID", "generation")
            normalized_generation = 0
        _require(normalized_generation >= 1, "CHILD_GENERATION_STATE_INVALID", "generation")
        _require(terminal_state in TERMINAL_STATES, "CHILD_GENERATION_STATE_INVALID", "terminal_state")
        _require(normalized_generation not in generations, "CHILD_GENERATION_STATE_DUPLICATE", str(normalized_generation))
        _require(child_ref not in child_refs, "CHILD_RUN_REF_REUSED", str(child_ref))
        generations.add(normalized_generation)
        child_refs.add(str(child_ref))
        normalized.append(
            {
                "child_run_ref": str(child_ref),
                "generation": normalized_generation,
                "terminal_state": terminal_state,
            }
        )
    return sorted(normalized, key=lambda item: item["generation"])


def materialize_child_run(
    *,
    record_id: str,
    parent_run_id: str,
    child_run_id: str,
    node_allocation: Mapping[str, Any],
    created_at: str,
    created_by: Mapping[str, Any],
    generation_states: Sequence[Mapping[str, Any]] = (),
    reason: str = "INITIAL",
    source_refs: Iterable[str] = (),
) -> dict[str, Any]:
    """Materialize one immutable ChildRun generation fact.

    SINGLE_ACTIVE is enforced from caller-supplied generation state. Historical
    ChildRuns and the immutable NodeAllocation are never mutated.
    """
    validate_node_allocation(node_allocation)
    _require(node_allocation.get("kind") == "WORK", "CONTROL_CHILD_MATERIALIZATION_FORBIDDEN")
    _require(verify_record_digest(node_allocation), "NODE_ALLOCATION_DIGEST_INVALID")
    parent_run_id = _canonical_reference(parent_run_id, "CHILD_LINEAGE_INVALID", "parent_run_id")
    child_run_id = _canonical_reference(child_run_id, "CHILD_RUN_REF_INVALID", "child_run_id")
    _require(node_allocation.get("run_id") == parent_run_id, "NODE_ALLOCATION_PARENT_MISMATCH")
    _require(child_run_id != parent_run_id, "CHILD_PARENT_SELF_LOOP")

    reason = str(reason).upper()
    _require(reason in MATERIALIZATION_REASONS, "CHILD_MATERIALIZATION_REASON_UNKNOWN", reason)
    states = _normalize_generation_states(generation_states)
    historical_child_refs = {state["child_run_ref"] for state in states}
    _require(child_run_id not in historical_child_refs, "CHILD_RUN_REF_REUSED", child_run_id)
    active = [state for state in states if state["terminal_state"] == "OPEN"]
    _require(not active, "CHILD_RUN_ALREADY_ACTIVE", active[0]["child_run_ref"] if active else "")

    if reason == "INITIAL":
        _require(not states, "INITIAL_CHILD_ALREADY_MATERIALIZED")
        generation = 1
        rerun_of = None
    else:
        _require(states, "RERUN_PREDECESSOR_REQUIRED")
        latest = states[-1]
        _require(latest["terminal_state"] != "OPEN", "CHILD_RUN_ALREADY_ACTIVE", latest["child_run_ref"])
        generation = latest["generation"] + 1
        rerun_of = latest["child_run_ref"]

    record = _base_record(
        record_id=record_id,
        schema_id="gwc.universal-run.child-run-materialization-receipt",
        run_id=parent_run_id,
        created_at=created_at,
        created_by=created_by,
        source_refs=source_refs,
        predecessor_refs=(),
    )
    record.update(
        {
            "parent_run_ref": parent_run_id,
            "node_allocation_ref": node_allocation["record_id"],
            "node_allocation_id": node_allocation["node_allocation_id"],
            "child_run_ref": child_run_id,
            "generation": generation,
            "materialization_reason": reason,
            "rerun_of": rerun_of,
            "child_instance_policy": CHILD_INSTANCE_POLICY,
        }
    )
    return seal_immutable_record(record)
