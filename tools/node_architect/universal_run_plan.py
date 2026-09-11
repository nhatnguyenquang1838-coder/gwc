#!/usr/bin/env python3
"""R4: hierarchical RuntimePlan revisions, cursor, recovery,
retry/rerun/replan/restart and drift detection.

C4 (G1 RuntimePlan, TargetContract and topology are immutable/digest-bound) and
C9 (retry/rerun/replan/restart, cursor recovery, drift and unknown-effect safety)
per the C1-C15 matrix. Composes E1 kernel digest primitives and E3 topology
manifest-revision; reuses the run-manifest-revision.schema.json shape.

Pure / transport-neutral: never persists, never grants authority, never mutates
external targets. Every function returns a typed result or raises a
deterministic fail-closed error before any effect.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from tools.node_architect.universal_run_kernel import UNIVERSAL_PROFILE, UniversalRunKernelError

PROFILE = UNIVERSAL_PROFILE
RESTART_MODES = ("RETRY", "RERUN", "REPLAN")


class PlanArchitectureError(ValueError):
    """Deterministic fail-closed plan architecture error."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


class CursorRecoveryError(PlanArchitectureError):
    """Typed error for cursor advance/recovery violations (C9)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("CURSOR_RECOVERY_VIOLATION", detail)


class DriftError(PlanArchitectureError):
    """Typed error when enforced drift is detected (C9)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("PLAN_DRIFT_DETECTED", detail)


class PlanFrozenError(PlanArchitectureError):
    """Typed error: a plan/revision frozen at G1 exit may not be mutated (Notion §9).

    Post-G1 material drift must create a NEW immutable revision with provenance,
    never silently mutate the frozen plan.
    """

    def __init__(self, detail: str = "") -> None:
        super().__init__("PLAN_FROZEN_AFTER_G1", detail)


MATERIAL_DRIFT_REASONS = ("MATERIAL_DRIFT",)


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise PlanArchitectureError(code, detail)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_digest(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(_canonical_json_bytes(part))
    return "sha256:" + h.hexdigest()


@dataclass(frozen=True)
class PlanRevision:
    """Immutable RuntimePlan revision (C4)."""

    run_id: str
    revision: int
    target_contract_ref: str
    node_allocations: tuple[str, ...]
    previous_digest: str | None
    digest: str = field(default_factory=str)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "revision": self.revision,
            "target_contract_ref": self.target_contract_ref,
            "node_allocations": list(self.node_allocations),
            "previous_digest": self.previous_digest,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanRevision":
        return cls(
            run_id=str(data.get("run_id", "")),
            revision=int(data.get("revision", 0)),
            target_contract_ref=str(data.get("target_contract_ref", "")),
            node_allocations=tuple(data.get("node_allocations", [])),
            previous_digest=data.get("previous_digest"),
            digest=str(data.get("digest", "")),
        )

    def to_manifest_record(self) -> dict[str, Any]:
        """Emit the run-manifest-revision schema shape."""
        return {
            "record_id": _sha256_digest("manifest", self.run_id, self.revision),
            "schema_id": "gwc.universal-run.run-manifest-revision",
            "schema_version": 1,
            "run_id": self.run_id,
            "created_at": "2026-01-01T00:00:00Z",
            "created_by": {"profile": "dwa-hermes"},
            "lifecycle_profile": copy.deepcopy(dict(PROFILE)),
            "provenance": {
                "predecessor_refs": [self.previous_digest] if self.previous_digest else [],
                "source_refs": [self.target_contract_ref],
            },
            "revision": self.revision,
            "run_kind": "ROOT",
            "parent_run_ref": None,
            "invoking_node_allocation_ref": None,
            "content_digest": {
                "algorithm": "sha256",
                "canonicalization": "JCS",
                "value": self.digest.split(":", 1)[1] if self.digest.startswith("sha256:") else self.digest,
            },
        }


class RuntimePlan(PlanRevision):
    """Alias for the first-class plan type (convenience + readability).

    This subclass exists for naming readability; it carries no extra fields and
    factory functions below return it (so ``isinstance(x, RuntimePlan)`` holds).
    ``from_dict`` must reconstruct the subclass to preserve round-trip identity.
    """

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RuntimePlan":
        return cls(
            run_id=str(data.get("run_id", "")),
            revision=int(data.get("revision", 0)),
            target_contract_ref=str(data.get("target_contract_ref", "")),
            node_allocations=tuple(data.get("node_allocations", [])),
            previous_digest=data.get("previous_digest"),
            digest=str(data.get("digest", "")),
        )


def _compute_digest(
    *,
    run_id: str,
    revision: int,
    target_contract_ref: str,
    node_allocations: tuple[str, ...],
    previous_digest: str | None,
) -> str:
    return _sha256_digest(
        run_id, revision, target_contract_ref,
        tuple(sorted(node_allocations)), previous_digest,
    )


@dataclass(frozen=True)
class ChildPlan:
    """Immutable Child Run RuntimePlan bound to its parent plan digest (Notion §9).

    The parent RuntimePlan REFERENCES child plans rather than embedding their
    operations; the binding is digest-bound and provenance-carrying, so a child
    plan revision can be validated against the exact parent revision it was
    compiled from.
    """

    run_id: str
    revision: int
    target_contract_ref: str
    node_allocations: tuple[str, ...]
    previous_digest: str | None
    parent_run_id: str
    parent_digest: str
    invoking_node_allocation_ref: str
    digest: str = field(default_factory=str)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "revision": self.revision,
            "target_contract_ref": self.target_contract_ref,
            "node_allocations": list(self.node_allocations),
            "previous_digest": self.previous_digest,
            "parent_run_id": self.parent_run_id,
            "parent_plan_digest": self.parent_digest,
            "invoking_node_allocation_ref": self.invoking_node_allocation_ref,
            "digest": self.digest,
        }


def _compute_child_digest(
    *,
    run_id: str,
    revision: int,
    target_contract_ref: str,
    node_allocations: tuple[str, ...],
    previous_digest: str | None,
    parent_run_id: str,
    parent_digest: str,
    invoking_node_allocation_ref: str,
) -> str:
    return _sha256_digest(
        "child-plan", run_id, revision, target_contract_ref,
        tuple(sorted(node_allocations)), previous_digest,
        parent_run_id, parent_digest, invoking_node_allocation_ref,
    )


def _compute_binding_digest(
    *, parent_run_id: str, parent_digest: str, child_run_id: str,
    invoking_node_allocation_ref: str,
) -> str:
    return _sha256_digest(
        "plan-binding", parent_run_id, parent_digest, child_run_id,
        invoking_node_allocation_ref,
    )


def create_runtime_plan(
    *,
    run_id: str,
    revision: int,
    target_contract_ref: str,
    node_allocations: list[str] | tuple[str, ...],
) -> PlanRevision:
    """Create the initial immutable RuntimePlan revision (C4)."""
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
    _require(isinstance(revision, int) and revision >= 1, "PLAN_REVISION_INVALID", str(revision))
    _require(isinstance(target_contract_ref, str) and target_contract_ref.strip(), "TARGET_CONTRACT_REF_INVALID")
    nodes = tuple(sorted(set(node_allocations or [])))
    _require(len(nodes) > 0, "PLAN_NODE_ALLOCATIONS_EMPTY")
    digest = _compute_digest(
        run_id=run_id, revision=revision, target_contract_ref=target_contract_ref,
        node_allocations=nodes, previous_digest=None,
    )
    return RuntimePlan(
        run_id=run_id, revision=revision, target_contract_ref=target_contract_ref,
        node_allocations=nodes, previous_digest=None, digest=digest,
    )


def create_plan_revision(
    *,
    previous: PlanRevision,
    run_id: str,
    revision: int,
    target_contract_ref: str,
    node_allocations: list[str] | tuple[str, ...],
) -> PlanRevision:
    """Create a successor plan revision; revision must strictly increase (C4/C9)."""
    _require(isinstance(previous, PlanRevision), "PLAN_PREVIOUS_REQUIRED")
    _require(run_id == previous.run_id, "PLAN_RUN_ID_CHANGE_FORBIDDEN")
    _require(isinstance(revision, int) and revision > previous.revision, "PLAN_REVISION_MUST_INCREASE")
    nodes = tuple(sorted(set(node_allocations or [])))
    _require(len(nodes) > 0, "PLAN_NODE_ALLOCATIONS_EMPTY")
    digest = _compute_digest(
        run_id=run_id, revision=revision, target_contract_ref=target_contract_ref,
        node_allocations=nodes, previous_digest=previous.digest,
    )
    return RuntimePlan(
        run_id=run_id, revision=revision, target_contract_ref=target_contract_ref,
        node_allocations=nodes, previous_digest=previous.digest, digest=digest,
    )


def validate_plan_digest(plan: PlanRevision) -> bool:
    """Verify a plan revision digest against its canonical inputs (C4)."""
    try:
        expected = _compute_digest(
            run_id=plan.run_id, revision=plan.revision,
            target_contract_ref=plan.target_contract_ref,
            node_allocations=tuple(plan.node_allocations),
            previous_digest=plan.previous_digest,
        )
        return plan.digest == expected
    except Exception:
        return False


def advance_cursor(
    *,
    run_id: str,
    current_cursor: int,
    next_cursor: int,
) -> dict[str, Any]:
    """Advance a run cursor; must be monotonic (C9)."""
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
    _require(isinstance(current_cursor, int) and current_cursor >= 0, "CURSOR_INVALID")
    _require(isinstance(next_cursor, int) and next_cursor >= 0, "CURSOR_INVALID")
    if next_cursor <= current_cursor:
        raise CursorRecoveryError(
            f"run={run_id} next_cursor={next_cursor} must exceed current_cursor={current_cursor}"
        )
    return {"run_id": run_id, "cursor": next_cursor, "ok": True}


def recover_cursor(
    *,
    run_id: str,
    saved_cursor: int | None,
    observed_cursor: int | None,
) -> dict[str, Any]:
    """Recover a run cursor after restart (C9).

    Fail-closed on unknown state: neither saved nor observed cursor -> error.
    An observed cursor higher than the saved cursor is evidence of effects past
    the saved point -> fail-closed (unknown effects).
    """
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
    if saved_cursor is None and observed_cursor is None:
        raise CursorRecoveryError(f"run={run_id} no cursor evidence — unknown state")
    if saved_cursor is not None and observed_cursor is not None and observed_cursor > saved_cursor:
        raise CursorRecoveryError(
            f"run={run_id} observed_cursor={observed_cursor} exceeds saved_cursor={saved_cursor}"
        )
    cursor = saved_cursor if saved_cursor is not None else observed_cursor
    return {"run_id": run_id, "cursor": cursor, "ok": True}


def restart_run(
    *,
    run_id: str,
    mode: str,
    plan_digest: str,
    restart_from_cursor: int,
) -> dict[str, Any]:
    """Typed control receipt for retry/rerun/replan/restart (C9).

    No-rewrite invariant: every restart mode returns NO_REWRITE and never
    mutates the plan lineage. REPLAN must reference a new revision digest.
    """
    mode = str(mode).upper()
    _require(mode in RESTART_MODES, "RESTART_MODE_UNKNOWN", mode)
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
    _require(isinstance(plan_digest, str) and plan_digest.startswith("sha256:"), "PLAN_DIGEST_INVALID")
    _require(isinstance(restart_from_cursor, int) and restart_from_cursor >= 0, "CURSOR_INVALID")
    return {
        "run_id": run_id,
        "mode": mode,
        "plan_digest": plan_digest,
        "restart_from_cursor": restart_from_cursor,
        "effect": "NO_REWRITE",
        "receipt": _sha256_digest("restart", run_id, mode, plan_digest, restart_from_cursor),
    }


def detect_drift(
    *,
    run_id: str,
    expected_plan_digest: str,
    observed_plan_digest: str,
    enforce: bool = False,
) -> dict[str, Any]:
    """Detect RuntimePlan drift (C9): expected vs observed digest mismatch.

    Unknown-effect safety: when enforced, a mismatch raises a typed DriftError
    before any effect so an unexpected plan cannot silently advance.
    """
    _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
    no_drift = expected_plan_digest == observed_plan_digest
    decision = "NO_DRIFT" if no_drift else "DRIFT"
    if enforce and not no_drift:
        raise DriftError(
            f"run={run_id} expected={expected_plan_digest} observed={observed_plan_digest}"
        )
    return {
        "run_id": run_id,
        "expected_plan_digest": expected_plan_digest,
        "observed_plan_digest": observed_plan_digest,
        "no_drift": no_drift,
        "drift_decision": decision,
    }


def freeze_plan_at_g1_exit(
    *,
    plan: PlanRevision,
    lifecycle_position: str = "G1",
) -> dict[str, Any]:
    """Freeze the immutable RuntimePlan revision at successful G1 exit (Notion §9).

    After G1 the plan revision for G2–G6 (plus the compiled child topology) is
    immutable. Material drift later must produce a NEW revision, never mutate
    this one. Fail-closed if the plan is not a valid digest-bound revision.
    """
    _require(isinstance(plan, PlanRevision), "PLAN_REQUIRED")
    _require(isinstance(plan.revision, int) and plan.revision >= 1, "PLAN_REVISION_INVALID", str(plan.revision))
    if not validate_plan_digest(plan):
        raise PlanFrozenError(
            f"run={plan.run_id} revision={plan.revision} digest invalid — cannot freeze"
        )
    return {
        "run_id": plan.run_id,
        "revision": plan.revision,
        "plan_digest": plan.digest,
        "frozen_at": "G1_EXIT",
        "frozen_lifecycle_position": str(lifecycle_position),
        "immutable": True,
        "freeze_receipt": _sha256_digest("plan-freeze", plan.run_id, plan.revision, plan.digest),
        "plan": plan,
    }


def assert_plan_mutation_allowed(
    *,
    frozen: Mapping[str, Any] | None,
    lifecycle_position: str,
) -> dict[str, Any]:
    """Guard post-G1 plan mutation (Notion §9).

    While no frozen revision exists (G0/G1 bootstrap/planning) mutation is
    allowed. Once a plan is frozen at G1 exit, any G2–G6 mutation attempt
    fail-closes with a typed PlanFrozenError; the correct path is a new
    immutable revision via replan_after_drift().
    """
    pos = str(lifecycle_position).upper()
    if frozen is None:
        return {"ok": True, "lifecycle_position": pos, "plan_digest": None, "reason_code": "PRE_FREEZE_ALLOWED"}
    frozen_digest = frozen.get("plan_digest")
    if pos in ("G2", "G3", "G4", "G5", "G6"):
        raise PlanFrozenError(
            f"run={frozen.get('run_id')} plan frozen at G1 exit (digest={frozen_digest}); "
            f"mutation at {pos} must create a new revision"
        )
    return {"ok": True, "lifecycle_position": pos, "plan_digest": frozen_digest, "reason_code": "PRE_FREEZE_ALLOWED"}


def propagate_plan_digest_to_child(
    *,
    parent_plan: PlanRevision,
    child_run_id: str,
    invoking_node_allocation_ref: str,
) -> dict[str, Any]:
    """Propagate the parent RuntimePlan digest to a Child Run's G0 binding (Notion §9).

    The parent plan REFERENCES child plans: the child receives the exact parent
    revision digest it was compiled against, plus the invoking node allocation.
    Fail-closed when the parent digest is not a valid digest-bound revision.
    """
    _require(isinstance(parent_plan, PlanRevision), "PLAN_PREVIOUS_REQUIRED")
    _require(isinstance(child_run_id, str) and child_run_id.strip(), "RUN_ID_INVALID", "child_run_id")
    _require(
        isinstance(invoking_node_allocation_ref, str) and invoking_node_allocation_ref.strip(),
        "INVOKING_NODE_ALLOCATION_REF_INVALID",
    )
    if not validate_plan_digest(parent_plan):
        raise PlanArchitectureError(
            "PLAN_PARENT_DIGEST_INVALID", f"run={parent_plan.run_id} revision={parent_plan.revision}"
        )
    return {
        "parent_run_id": parent_plan.run_id,
        "parent_plan_digest": parent_plan.digest,
        "parent_plan_revision": parent_plan.revision,
        "child_run_id": child_run_id,
        "invoking_node_allocation_ref": invoking_node_allocation_ref,
        "binding_digest": _compute_binding_digest(
            parent_run_id=parent_plan.run_id, parent_digest=parent_plan.digest,
            child_run_id=child_run_id, invoking_node_allocation_ref=invoking_node_allocation_ref,
        ),
    }


def validate_child_plan_binding(
    *,
    parent_plan: PlanRevision,
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a child plan binding against the parent revision (Notion §9).

    Fail-closed (ok=False, typed reason code) when the parent plan has drifted
    away from the digest the child was bound to, or when the binding digest is
    tampered with. It never raises on drift so callers can branch on the result.
    """
    _require(isinstance(parent_plan, PlanRevision), "PLAN_PREVIOUS_REQUIRED")
    _require(isinstance(binding, Mapping), "PLAN_BINDING_REQUIRED")
    expected_parent = binding.get("parent_plan_digest")
    child_run_id = binding.get("child_run_id")
    invoking = binding.get("invoking_node_allocation_ref")
    recomputed = _compute_binding_digest(
        parent_run_id=str(binding.get("parent_run_id")),
        parent_digest=str(expected_parent),
        child_run_id=str(child_run_id),
        invoking_node_allocation_ref=str(invoking),
    )
    if binding.get("binding_digest") != recomputed:
        return {
            "ok": False,
            "reason_code": "CHILD_PLAN_BINDING_DIGEST_INVALID",
            "child_run_id": child_run_id,
            "parent_plan_digest": parent_plan.digest,
        }
    if expected_parent != parent_plan.digest:
        return {
            "ok": False,
            "reason_code": "CHILD_PLAN_PARENT_DIGEST_DRIFT",
            "child_run_id": child_run_id,
            "expected_parent_digest": expected_parent,
            "parent_plan_digest": parent_plan.digest,
        }
    return {
        "ok": True,
        "reason_code": "CHILD_PLAN_BINDING_VALID",
        "child_run_id": child_run_id,
        "parent_plan_digest": parent_plan.digest,
    }


def create_child_plan_revision(
    *,
    parent_plan: PlanRevision,
    child_run_id: str,
    revision: int,
    target_contract_ref: str,
    invoking_node_allocation_ref: str,
    node_allocations: list[str] | tuple[str, ...],
) -> ChildPlan:
    """Create an immutable Child Run plan revision bound to the parent digest (Notion §9).

    The parent plan REFERENCES (does not embed) the child plan; the child
    revision carries parent_run_id + parent_plan_digest as provenance.
    """
    _require(isinstance(parent_plan, PlanRevision), "PLAN_PREVIOUS_REQUIRED")
    _require(isinstance(child_run_id, str) and child_run_id.strip(), "RUN_ID_INVALID", "child_run_id")
    _require(isinstance(revision, int) and revision >= 1, "PLAN_REVISION_INVALID", str(revision))
    _require(isinstance(target_contract_ref, str) and target_contract_ref.strip(), "TARGET_CONTRACT_REF_INVALID")
    _require(
        isinstance(invoking_node_allocation_ref, str) and invoking_node_allocation_ref.strip(),
        "INVOKING_NODE_ALLOCATION_REF_INVALID",
    )
    nodes = tuple(sorted(set(node_allocations or [])))
    _require(len(nodes) > 0, "PLAN_NODE_ALLOCATIONS_EMPTY")
    if not validate_plan_digest(parent_plan):
        raise PlanArchitectureError(
            "PLAN_PARENT_DIGEST_INVALID", f"run={parent_plan.run_id} revision={parent_plan.revision}"
        )
    digest = _compute_child_digest(
        run_id=child_run_id, revision=revision, target_contract_ref=target_contract_ref,
        node_allocations=nodes, previous_digest=None,
        parent_run_id=parent_plan.run_id, parent_digest=parent_plan.digest,
        invoking_node_allocation_ref=invoking_node_allocation_ref,
    )
    return ChildPlan(
        run_id=child_run_id, revision=revision, target_contract_ref=target_contract_ref,
        node_allocations=nodes, previous_digest=None,
        parent_run_id=parent_plan.run_id, parent_digest=parent_plan.digest,
        invoking_node_allocation_ref=invoking_node_allocation_ref, digest=digest,
    )


def replan_after_drift(
    *,
    frozen: Mapping[str, Any],
    target_contract_ref: str,
    node_allocations: list[str] | tuple[str, ...],
    drift_reason: str,
) -> PlanRevision:
    """Create a NEW immutable revision after material drift (Notion §9).

    Immutable Replan: material drift after G1 produces a new immutable revision
    with provenance (previous_digest -> frozen digest); it never mutates the
    frozen revision. Non-material drift is refused (no silent churn).
    """
    _require(isinstance(frozen, Mapping), "PLAN_FREEZE_REQUIRED")
    plan = frozen.get("plan")
    _require(isinstance(plan, PlanRevision), "PLAN_FREEZE_REQUIRED")
    reason = str(drift_reason).upper()
    if reason not in MATERIAL_DRIFT_REASONS:
        raise PlanFrozenError(
            f"run={plan.run_id} drift_reason={drift_reason} is not material; "
            "refusing to create a new revision (no silent churn)"
        )
    nodes = tuple(sorted(set(node_allocations or [])))
    _require(len(nodes) > 0, "PLAN_NODE_ALLOCATIONS_EMPTY")
    new_revision = plan.revision + 1
    digest = _compute_digest(
        run_id=plan.run_id, revision=new_revision, target_contract_ref=target_contract_ref,
        node_allocations=nodes, previous_digest=plan.digest,
    )
    return RuntimePlan(
        run_id=plan.run_id, revision=new_revision, target_contract_ref=target_contract_ref,
        node_allocations=nodes, previous_digest=plan.digest, digest=digest,
    )


class ReplanAuditError(PlanArchitectureError):
    """Typed error when the replan audit log has a gap or is inconsistent (hardening GAP 3)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("REPLAN_AUDIT_GAP", detail)


class ReplanAuditLog:
    """Append-only immutable replan audit log (hardening GAP 3).

    Each entry is a digest-bound immutable snapshot (from_digest -> to_revision with
    drift_reason). Appending never mutates prior entries. Fail-closed on a revision
    gap (next to_revision must continue from the last entry's to_revision).
    """

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def append(
        self,
        *,
        run_id: str,
        from_digest: str,
        to_revision: int,
        drift_reason: str,
    ) -> dict[str, Any]:
        _require(isinstance(run_id, str) and run_id.strip(), "RUN_ID_INVALID", "run_id")
        _require(isinstance(from_digest, str) and from_digest.startswith("sha256:"), "PLAN_DIGEST_INVALID")
        _require(isinstance(to_revision, int) and to_revision >= 1, "PLAN_REVISION_INVALID", str(to_revision))
        _require(isinstance(drift_reason, str) and drift_reason.strip(), "DRIFT_REASON_INVALID")
        if self._entries:
            last = self._entries[-1]
            if to_revision != last["to_revision"] + 1:
                raise ReplanAuditError(
                    f"run={run_id} to_revision={to_revision} must continue from {last['to_revision']}"
                )
        entry = {
            "run_id": run_id,
            "from_digest": from_digest,
            "to_revision": to_revision,
            "drift_reason": drift_reason,
            "digest": _sha256_digest("replan-audit", run_id, from_digest, to_revision, drift_reason),
        }
        self._entries.append(entry)
        return entry

    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)



__all__ = [
    "ChildPlan",
    "CursorRecoveryError",
    "DriftError",
    "MATERIAL_DRIFT_REASONS",
    "PlanArchitectureError",
    "PlanFrozenError",
    "PlanRevision",
    "ReplanAuditError",
    "ReplanAuditLog",
    "RESTART_MODES",
    "RuntimePlan",
    "advance_cursor",
    "assert_plan_mutation_allowed",
    "create_child_plan_revision",
    "create_plan_revision",
    "create_runtime_plan",
    "detect_drift",
    "freeze_plan_at_g1_exit",
    "propagate_plan_digest_to_child",
    "recover_cursor",
    "replan_after_drift",
    "restart_run",
    "validate_child_plan_binding",
    "validate_plan_digest",
]
