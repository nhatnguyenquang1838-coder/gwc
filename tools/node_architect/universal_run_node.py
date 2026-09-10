#!/usr/bin/env python3
"""R3: NodeDefinition / NodeAllocation, WORK/CONTROL promotion, DAG budgets and
SINGLE_ACTIVE concurrency guard.

C11 (NodeDefinition/Allocation, WORK/CONTROL promotion, DAG budgets and
SINGLE_ACTIVE) and C8 (recursive Parent-Child materialization, composition,
failure propagation and budgets) per the C1-C15 matrix. Composes E1 kernel
identity/digest primitives and E3 topology; reuses the committed
node-allocation.schema.json shape.

Pure / transport-neutral: never persists, never grants authority, never mutates
external targets. Every function returns a typed result or raises a
deterministic fail-closed error before any effect.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE, UniversalRunKernelError

PROFILE = UNIVERSAL_PROFILE
NODE_KINDS = ("WORK", "CONTROL")
REQUIREMENT_KINDS = ("REQUIRED", "OPTIONAL", "CONDITIONAL")
CHILD_INSTANCE_POLICY = "SINGLE_ACTIVE"


class NodeArchitectureError(ValueError):
    """Deterministic fail-closed node architecture error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


class DAGBudgetError(NodeArchitectureError):
    """Typed error when a DAG budget is exceeded (C8/C11)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("DAG_BUDGET_EXCEEDED", detail)


class SingleActiveError(NodeArchitectureError):
    """Typed error when SINGLE_ACTIVE concurrency guard is violated (C11)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("SINGLE_ACTIVE_VIOLATION", detail)


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise NodeArchitectureError(code, detail)


def _canonical_json_bytes(value: Any) -> bytes:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(_canonical_json_bytes(part))
    return "sha256:" + h.hexdigest()


@dataclass(frozen=True)
class NodeDefinition:
    """Immutable node definition (C11)."""

    node_id: str
    kind: str
    requirement: str
    description: str = ""
    budget: int = 0
    control_justification: str | None = None
    condition_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "requirement": self.requirement,
            "description": self.description,
            "budget": self.budget,
            "control_justification": self.control_justification,
            "condition_ref": self.condition_ref,
        }


@dataclass(frozen=True)
class NodeAllocation:
    """Immutable node allocation record matching node-allocation schema shape."""

    record_id: str
    run_id: str
    node_id: str
    kind: str
    requirement: str
    condition_ref: str | None
    control_justification: str | None
    independent_boundary_reasons: tuple[str, ...]
    child_instance_policy: str
    content_digest: str = field(default_factory=str)

    def to_dict(self) -> dict[str, Any]:
        reasons = list(self.independent_boundary_reasons)
        # CONTROL allocations must have empty independent_boundary_reasons (schema allOf).
        if self.kind == "CONTROL":
            reasons = []
        return {
            "record_id": self.record_id,
            "schema_id": "gwc.universal-run.node-allocation",
            "schema_version": 1,
            "run_id": self.run_id,
            "created_at": "2026-01-01T00:00:00Z",
            "created_by": {"profile": "dwa-hermes"},
            "lifecycle_profile": copy.deepcopy(dict(PROFILE)),
            "provenance": {"predecessor_refs": [], "source_refs": [self.node_id]},
            "node_allocation_id": f"{self.run_id}:{self.node_id}",
            "kind": self.kind,
            "requirement": self.requirement,
            "condition_ref": self.condition_ref,
            "control_justification": self.control_justification,
            "independent_boundary_reasons": reasons,
            "child_instance_policy": self.child_instance_policy,
            "content_digest": {
                "algorithm": "sha256",
                "canonicalization": "JCS",
                "value": self.content_digest.split(":", 1)[1] if self.content_digest.startswith("sha256:") else self.content_digest,
            },
        }


def build_node_definition(
    *,
    node_id: str,
    kind: str,
    requirement: str,
    description: str = "",
    budget: int = 0,
    control_justification: str | None = None,
    condition_ref: str | None = None,
) -> NodeDefinition:
    """Construct and validate a NodeDefinition (C11)."""
    _require(isinstance(node_id, str) and node_id.strip(), "NODE_ID_INVALID", "node_id")
    _require(kind in NODE_KINDS, "NODE_KIND_UNKNOWN", str(kind))
    _require(requirement in REQUIREMENT_KINDS, "NODE_REQUIREMENT_UNKNOWN", str(requirement))
    _require(isinstance(budget, int) and budget >= 0, "NODE_BUDGET_INVALID", str(budget))
    if kind == "CONTROL":
        _require(
            isinstance(control_justification, str) and control_justification.strip(),
            "CONTROL_JUSTIFICATION_REQUIRED",
            "CONTROL node requires control_justification",
        )
    return NodeDefinition(
        node_id=node_id, kind=kind, requirement=requirement,
        description=description, budget=budget,
        control_justification=control_justification, condition_ref=condition_ref,
    )


def _node_allocation_digest(alloc_fields: Mapping[str, Any]) -> str:
    return _sha256_digest(
        alloc_fields.get("run_id"), alloc_fields.get("node_id"),
        alloc_fields.get("kind"), alloc_fields.get("requirement"),
        alloc_fields.get("condition_ref"), alloc_fields.get("control_justification"),
        tuple(alloc_fields.get("independent_boundary_reasons", [])),
        alloc_fields.get("child_instance_policy"),
    )


def allocate_node(
    *,
    run_id: str,
    node: NodeDefinition,
    condition_ref: str | None = None,
    control_justification: str | None = None,
    independent_boundary_reasons: list[str] | tuple[str, ...] = (),
) -> NodeAllocation:
    """Create an immutable NodeAllocation (C11)."""
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
    _require(isinstance(node, NodeDefinition), "NODE_DEFINITION_REQUIRED")
    if node.kind == "CONTROL":
        _require(
            isinstance(control_justification, str) and control_justification.strip(),
            "CONTROL_JUSTIFICATION_REQUIRED",
            "CONTROL allocation requires control_justification",
        )
    reasons = tuple(sorted(set(independent_boundary_reasons)))
    fields = {
        "run_id": run_id,
        "node_id": node.node_id,
        "kind": node.kind,
        "requirement": node.requirement,
        "condition_ref": condition_ref if condition_ref is not None else node.condition_ref,
        "control_justification": control_justification if control_justification is not None else node.control_justification,
        "independent_boundary_reasons": reasons,
        "child_instance_policy": CHILD_INSTANCE_POLICY,
    }
    digest = _node_allocation_digest(fields)
    record_id = _sha256_digest(run_id, node.node_id, digest)
    return NodeAllocation(
        record_id=record_id,
        run_id=run_id,
        node_id=node.node_id,
        kind=node.kind,
        requirement=node.requirement,
        condition_ref=fields["condition_ref"],
        control_justification=fields["control_justification"],
        independent_boundary_reasons=reasons,
        child_instance_policy=CHILD_INSTANCE_POLICY,
        content_digest=digest,
    )


def promote_node(
    *,
    node_id: str,
    kind: str,
    new_kind: str,
    control_justification: str | None = None,
) -> dict[str, Any]:
    """WORK -> CONTROL promotion (C11). CONTROL -> WORK is forbidden. Same kind is a typed no-op."""
    _require(kind in NODE_KINDS, "NODE_KIND_UNKNOWN", str(kind))
    _require(new_kind in NODE_KINDS, "NODE_KIND_UNKNOWN", str(new_kind))
    if kind == new_kind:
        return {
            "node_id": node_id,
            "kind": kind,
            "new_kind": new_kind,
            "noop": True,
            "reason_code": "NOOP_SAME_KIND",
            "promoted": False,
        }
    if kind == "CONTROL" and new_kind == "WORK":
        raise NodeArchitectureError("CONTROL_TO_WORK_FORBIDDEN", "CONTROL nodes cannot demote to WORK")
    if new_kind == "CONTROL":
        _require(
            isinstance(control_justification, str) and control_justification.strip(),
            "CONTROL_JUSTIFICATION_REQUIRED",
            "WORK->CONTROL promotion requires control_justification",
        )
    return {
        "node_id": node_id,
        "kind": new_kind,
        "new_kind": new_kind,
        "control_justification": control_justification,
        "noop": False,
        "reason_code": "PROMOTED",
        "promoted": True,
    }


def enforce_dag_budget(
    *,
    run_id: str,
    node_ids: list[str] | tuple[str, ...],
    budget: int,
    kind: str,
) -> dict[str, Any]:
    """Enforce a DAG budget (C8/C11): total node count must not exceed budget.

    Raises a typed DAGBudgetError before any effect when the budget is exceeded,
    so a failing child propagates a deterministic typed error to its parent.
    """
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
    _require(kind in NODE_KINDS, "NODE_KIND_UNKNOWN", str(kind))
    _require(isinstance(budget, int) and budget >= 0, "NODE_BUDGET_INVALID", str(budget))
    node_ids = list(node_ids or [])
    count = len(node_ids)
    if count > budget:
        raise DAGBudgetError(f"run={run_id} kind={kind} count={count} budget={budget}")
    return {"run_id": run_id, "kind": kind, "count": count, "budget": budget, "ok": True}


def resolve_single_active(
    *,
    run_id: str,
    child_run_ids: list[str] | tuple[str, ...],
    active_child_run_id: str | None,
) -> dict[str, Any]:
    """SINGLE_ACTIVE concurrency guard (C11).

    Exactly one child may be ACTIVE per parent. Activating a second child while
    one is already active raises a typed SingleActiveError. Re-asserting the same
    active child is idempotent.
    """
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
    child_run_ids = list(child_run_ids or [])
    _require(len(child_run_ids) > 0, "CHILD_RUNS_EMPTY", "at least one child required")
    if active_child_run_id is not None:
        if active_child_run_id not in child_run_ids:
            raise NodeArchitectureError("ACTIVE_CHILD_UNKNOWN", str(active_child_run_id))
        # SINGLE_ACTIVE: exactly one child may be active. If another child is
        # requested while one is already active, that is a violation.
        if active_child_run_id != child_run_ids[0] or len(child_run_ids) > 1:
            raise SingleActiveError(
                f"run={run_id} already active child={active_child_run_id}; cannot activate {child_run_ids}"
            )
    else:
        if len(child_run_ids) > 1:
            raise SingleActiveError(f"run={run_id} cannot auto-activate multiple children {child_run_ids}")
    return {"run_id": run_id, "active_child_run_id": active_child_run_id or child_run_ids[0], "ok": True}


__all__ = [
    "CHILD_INSTANCE_POLICY",
    "DAGBudgetError",
    "NODE_KINDS",
    "NodeAllocation",
    "NodeArchitectureError",
    "NodeDefinition",
    "REQUIREMENT_KINDS",
    "SingleActiveError",
    "allocate_node",
    "build_node_definition",
    "enforce_dag_budget",
    "promote_node",
    "resolve_single_active",
]
