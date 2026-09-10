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


__all__ = [
    "CursorRecoveryError",
    "DriftError",
    "PlanArchitectureError",
    "PlanRevision",
    "RESTART_MODES",
    "RuntimePlan",
    "advance_cursor",
    "create_plan_revision",
    "create_runtime_plan",
    "detect_drift",
    "recover_cursor",
    "restart_run",
    "validate_plan_digest",
]
