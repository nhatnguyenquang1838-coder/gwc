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
from tools.node_architect.universal_run_lifecycle import TRANSFER_OUTCOME_KINDS, TransferOutcome
from tools.node_architect.universal_run_topology import create_run_manifest_revision, materialize_child_run

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


class CompositionVerificationError(NodeArchitectureError):
    """Typed error for parent-G3 composition verification violations (Notion §3)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code, detail)


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


def verify_parent_composition(
    *,
    parent_run_id: str,
    acceptance_contract_ref: str,
    required_child_run_ids: list[str] | tuple[str, ...],
    child_results: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """Notion design §3: Parent.G3 verifies the COMPOSITION/aggregate of accepted
    child outputs; child-local PASS is never sufficient proof.

    Fail-closed (no exception leaking partial state) when a required child is
    missing, not ACCEPTED, or lacks an output digest. On success returns a
    deterministic composition digest over the accepted required child outputs,
    order-independent, so the same accepted inputs always yield the same
    aggregate binding.
    """
    if not (isinstance(parent_run_id, str) and parent_run_id.strip()):
        raise CompositionVerificationError("PARENT_RUN_ID_INVALID", str(parent_run_id))
    if not (isinstance(acceptance_contract_ref, str) and acceptance_contract_ref.strip()):
        raise CompositionVerificationError(
            "ACCEPTANCE_CONTRACT_REF_INVALID", str(acceptance_contract_ref)
        )

    required = [str(c) for c in (required_child_run_ids or [])]
    by_child: dict[str, Mapping[str, Any]] = {}
    for res in (child_results or []):
        if isinstance(res, Mapping) and res.get("child_run_id") is not None:
            by_child[str(res["child_run_id"])] = res

    unaccepted: list[str] = []
    missing_digest: list[str] = []
    accepted_pairs: list[tuple[str, str]] = []

    for child_id in required:
        res = by_child.get(child_id)
        state = str(res.get("terminal_state")) if res else None
        if res is None or state != "ACCEPTED":
            unaccepted.append(child_id)
            continue
        output_digest = res.get("output_digest")
        if not (isinstance(output_digest, str) and output_digest.strip()):
            missing_digest.append(child_id)
            continue
        accepted_pairs.append((child_id, output_digest))

    if unaccepted:
        return {
            "ok": False,
            "reason_code": "COMPOSITION_CHILD_NOT_ACCEPTED",
            "parent_run_id": parent_run_id,
            "acceptance_contract_ref": acceptance_contract_ref,
            "unaccepted_child_run_ids": sorted(unaccepted),
            "missing_output_digest_child_run_ids": sorted(missing_digest),
            "composition_digest": None,
        }
    if missing_digest:
        return {
            "ok": False,
            "reason_code": "COMPOSITION_OUTPUT_DIGEST_MISSING",
            "parent_run_id": parent_run_id,
            "acceptance_contract_ref": acceptance_contract_ref,
            "unaccepted_child_run_ids": [],
            "missing_output_digest_child_run_ids": sorted(missing_digest),
            "composition_digest": None,
        }

    # Deterministic, order-independent aggregate over accepted required outputs.
    ordered = tuple(sorted(accepted_pairs, key=lambda p: p[0]))
    composition_digest = _sha256_digest(
        "parent-g3-composition", parent_run_id, acceptance_contract_ref, ordered
    )
    return {
        "ok": True,
        "reason_code": "COMPOSITION_VERIFIED",
        "parent_run_id": parent_run_id,
        "acceptance_contract_ref": acceptance_contract_ref,
        "accepted_child_run_ids": [c for c, _ in ordered],
        "unaccepted_child_run_ids": [],
        "missing_output_digest_child_run_ids": [],
        "composition_digest": composition_digest,
    }


class RecursiveRunDag:
    """Execute recursive ChildRuns through the canonical Agent Host event seam.

    Specs contain a sealed ``node_allocation``, a distinct ``child_run_id``,
    optional ``depends_on`` IDs and nested ``children``. ``checkpoint`` is a
    caller-owned in-memory checkpoint mapping prototype for gate receipts,
    generations and run receipts; it is NOT disk/process-crash durable. C4 owns
    persistence, sealed receipts, replay preconditions and CAS.
    """

    def __init__(self, *, runtime_event: Any | None = None, max_depth: int = 16, max_nodes: int = 256):
        if not isinstance(max_depth, int) or max_depth < 1 or not isinstance(max_nodes, int) or max_nodes < 1:
            raise NodeArchitectureError("DAG_BUDGET_INVALID")
        self._uses_host_defaults = runtime_event is None
        if runtime_event is None:
            from tools.node_architect.agent_runtime_entrypoint import LiveRuntimeState, run_agent_runtime_event
            runtime_event = run_agent_runtime_event
            self._state_factory = LiveRuntimeState
        else:
            self._state_factory = None
        if not callable(runtime_event):
            raise NodeArchitectureError("RUNTIME_EVENT_REQUIRED")
        self.runtime_event = runtime_event
        self.max_depth = max_depth
        self.max_nodes = max_nodes

    def _host_gate(self, gate: str) -> str:
        # COMMAND #193 F2: universal G4/G5/G6 are INTEGRATE / VALIDATE-IN-TARGET /
        # ACCEPT-HANDOFF. They must NEVER default to a protected domain effect
        # (G4_MERGE / G5_DEPLOY / G6_PRODUCTION_DATA) — that requires a separately
        # resolved canonical route, scope and exact authenticated authority.
        if not self._uses_host_defaults:
            return gate
        return {
            "G0": "G0_CONTEXT", "G1": "G1_ALIGNMENT", "G2": "G2_EXECUTION",
            "G3": "G3_REVIEW", "G4": "G4_INTEGRATE", "G5": "G5_VALIDATE_TARGET",
            "G6": "G6_ACCEPT_HANDOFF",
        }[gate]

    @staticmethod
    def _ordered(specs: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        by_id = {str(item.get("child_run_id", "")): item for item in specs}
        if len(by_id) != len(specs):
            raise NodeArchitectureError("CHILD_RUN_ID_DUPLICATE")
        ordered: list[Mapping[str, Any]] = []
        pending = dict(by_id)
        while pending:
            done = {str(item["child_run_id"]) for item in ordered}
            ready = sorted(key for key, item in pending.items()
                           if set(map(str, item.get("depends_on", ()))) <= done)
            if not ready:
                raise NodeArchitectureError("DAG_CYCLE_OR_DEPENDENCY_UNKNOWN")
            for key in ready:
                ordered.append(pending.pop(key))
        return ordered

    def execute_persistent(self, *, store_path: Any, task_id: str, repository: str,
                           branch: str, base_sha: str, head_sha: str, scope_hash: str,
                           lease_id: str, fencing_token: int, lease_expires_at: str,
                           root_manifest: Mapping[str, Any],
                           child_node_allocations: list[Mapping[str, Any]],
                           authority: Mapping[str, Any] | None,
                           canonical_state: Mapping[str, Any],
                           lease_owner: str = "recursive-run-dag", **event_context: Any) -> dict[str, Any]:
        """Execute against the canonical file-backed checkpoint store.

        The caller supplies exact repository/run and fencing authority. A new DAG
        instance can reload the sealed gate cursor from ``store_path`` after a
        process restart. This is the durable path; ``execute(checkpoint=dict)``
        remains an in-memory test prototype.
        """
        import copy
        from datetime import datetime, timezone
        from pathlib import Path
        from tools.node_architect import checkpoint_store as durable

        path = Path(store_path)
        root_id = str(root_manifest.get("run_id", "")) if isinstance(root_manifest, Mapping) else ""
        if (not all(isinstance(value, str) and value.strip() for value in
                    (task_id, repository, branch, base_sha, head_sha, scope_hash, lease_id, lease_owner))
                or not scope_hash.startswith("sha256:")
                or not isinstance(fencing_token, int) or isinstance(fencing_token, bool) or fencing_token < 0):
            raise NodeArchitectureError("DAG_PERSISTENCE_BINDING_INVALID")
        try:
            expiry = datetime.fromisoformat(lease_expires_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            raise NodeArchitectureError("DAG_LEASE_INVALID") from None
        now = datetime.now(timezone.utc)
        if expiry.tzinfo is None or expiry <= now:
            raise NodeArchitectureError("DAG_LEASE_EXPIRED")
        if not root_id:
            raise NodeArchitectureError("ROOT_RUN_MANIFEST_INVALID")

        store = durable.load_store(path)
        expected_binding = {"task_id": task_id, "repository": repository, "branch": branch,
                            "base_sha": base_sha, "head_sha": head_sha, "scope_hash": scope_hash}
        binding = store.get("binding")
        if isinstance(binding, Mapping):
            if any(binding.get(key) != value for key, value in expected_binding.items()):
                raise NodeArchitectureError("DAG_PERSISTENCE_BINDING_MISMATCH")
        input_digest = durable.digest_payload({
            "root_manifest": root_manifest, "child_node_allocations": child_node_allocations,
            "authority": authority, "canonical_state": canonical_state,
        })
        lease = store.get("lease_binding")
        if isinstance(lease, Mapping):
            if (lease.get("lease_owner") != lease_owner or lease.get("lease_token") != lease_id
                    or lease.get("fencing_token") != fencing_token):
                raise NodeArchitectureError("DAG_LEASE_FENCING_MISMATCH")
            try:
                stored_expiry = datetime.fromisoformat(str(lease.get("lease_expires_at", "")).replace("Z", "+00:00"))
            except ValueError:
                raise NodeArchitectureError("DAG_LEASE_INVALID") from None
            if stored_expiry.tzinfo is None or stored_expiry <= now:
                raise NodeArchitectureError("DAG_LEASE_EXPIRED")
            if lease.get("lease_expires_at") != lease_expires_at:
                raise NodeArchitectureError("DAG_LEASE_BINDING_MISMATCH")
        if int(store.get("revision", 0)) > 0:
            digest = store.get("store_digest")
            expected_digest = durable.digest_payload({
                "revision": store.get("revision", 0), "binding": store.get("binding"),
                "lease_binding": store.get("lease_binding"), "events": store.get("events", []),
                "checkpoints": store.get("checkpoints", {}), "effects": store.get("effects", {}),
            })
            if digest != expected_digest:
                raise NodeArchitectureError("DAG_PERSISTENCE_STORE_TAMPERED")

        last_item: list[Any] = [None]
        def persist_progress(current: dict[str, Any], *, run_id: str, node_id: str) -> None:
            safe_state = copy.deepcopy({key: value for key, value in current.items()
                                        if key not in {"runtime_states", "leases", "schema_version", "artifact_type",
                                                       "revision", "events", "checkpoints", "effects", "binding",
                                                       "lease_binding", "store_digest"}})
            revision = int(current.get("revision", 0))
            item = durable.CheckpointInput(
                task_id=task_id, run_id=root_id, node_id=f"recursive-dag:{revision + 1}:{run_id}:{node_id}",
                repository=repository, branch=branch, base_sha=base_sha, head_sha=head_sha,
                scope_hash=scope_hash, state=safe_state, expected_revision=revision,
                graph_revision="recursive-run-dag-v1", lease_id=lease_id,
                fencing_token=fencing_token,
                cas_context={"lease_owner": lease_owner, "lease_expires_at": lease_expires_at},
            )
            last_item[0] = item
            try:
                saved = durable.persist_to_file(path, item)
            except Exception as exc:
                observed = durable.load_store(path)
                decision = durable.reconcile_unknown_outcome(observed, item)
                raise NodeArchitectureError("DAG_PERSISTENCE_OUTCOME_UNKNOWN", str(decision)) from exc
            saved.setdefault("binding", {}).update(expected_binding)
            saved["store_digest"] = durable.digest_payload({
                "revision": saved["revision"], "binding": saved.get("binding"),
                "lease_binding": saved.get("lease_binding"), "events": saved["events"],
                "checkpoints": saved["checkpoints"], "effects": saved.get("effects", {}),
            })
            audit_event = {
                "schema_version": "1.0", "artifact_type": "runtime-event",
                "event_type": "recursive_run.audit", "run_id": run_id,
                "node_id": node_id, "decision": "CHECKPOINT_SEALED",
                "checkpoint_revision": saved["revision"],
                "lease_owner": lease_owner, "fencing_token": fencing_token,
                "gate_receipt_digests": {
                    gate: durable.digest_payload({"evidence": receipt.get("evidence"),
                                                 "g6_receipt": receipt.get("g6_receipt")})
                    for gates in safe_state.get("gates", {}).values()
                    if isinstance(gates, Mapping)
                    for gate, receipt in gates.items() if isinstance(receipt, Mapping)
                },
                "gate_readback_digests": {
                    gate: durable.digest_payload(receipt.get("target_readback"))
                    for gates in safe_state.get("gates", {}).values()
                    if isinstance(gates, Mapping)
                    for gate, receipt in gates.items() if isinstance(receipt, Mapping)
                },
                "occurred_at": durable._now(),
            }
            audit_event["event_digest"] = durable.digest_payload(audit_event)
            saved["events"].append(audit_event)
            saved["store_digest"] = durable.digest_payload({
                "revision": saved["revision"], "binding": saved.get("binding"),
                "lease_binding": saved.get("lease_binding"), "events": saved["events"],
                "checkpoints": saved["checkpoints"], "effects": saved.get("effects", {}),
            })
            durable.write_store(path, saved)
            for key in ("schema_version", "artifact_type", "revision", "events", "checkpoints",
                        "effects", "binding", "lease_binding", "store_digest"):
                if key in saved:
                    current[key] = saved[key]

        # Recover only the DAG's sealed state from the latest canonical record.
        if int(store.get("revision", 0)):
            records = [record for record in store.get("checkpoints", {}).values()
                       if isinstance(record, Mapping) and record.get("run_id") == root_id
                       and str(record.get("node_id", "")).startswith("recursive-dag:")]
            if not records:
                raise NodeArchitectureError("DAG_PERSISTENCE_CHECKPOINT_MISSING")
            record = max(records, key=lambda value: int(value.get("revision", 0)))
            state = record.get("state")
            if not isinstance(state, Mapping):
                raise NodeArchitectureError("DAG_PERSISTENCE_STATE_INVALID")
            if durable.digest_payload(state) != record.get("state_digest"):
                raise NodeArchitectureError("DAG_PERSISTENCE_STATE_TAMPERED")
            store.update({key: copy.deepcopy(value) for key, value in state.items()
                          if key not in {"schema_version", "artifact_type", "revision", "events", "checkpoints",
                                         "effects", "binding", "lease_binding", "store_digest"}})
            prior_input_digest = store.get("dag_input_digest")
            if prior_input_digest is not None and prior_input_digest != input_digest:
                raise NodeArchitectureError("DAG_PERSISTENCE_INPUT_MISMATCH")
            last_item[0] = durable.CheckpointInput(
                task_id=task_id, run_id=root_id, node_id=str(record.get("node_id")),
                repository=repository, branch=branch, base_sha=base_sha, head_sha=head_sha,
                scope_hash=scope_hash, state=copy.deepcopy(dict(state)),
                expected_revision=int(record.get("previous_revision", 0)),
                graph_revision="recursive-run-dag-v1", lease_id=lease_id, fencing_token=fencing_token,
                cas_context={"lease_owner": lease_owner, "lease_expires_at": lease_expires_at},
            )
        store["dag_input_digest"] = input_digest
        result = self.execute(root_manifest=root_manifest,
                              child_node_allocations=child_node_allocations,
                              authority=authority, canonical_state=canonical_state,
                              checkpoint=store, lease_owner=lease_owner,
                              _persist_hook=persist_progress, **event_context)
        final = durable.load_store(path)
        item = last_item[0]
        if item is None:
            raise NodeArchitectureError("DAG_PERSISTENCE_CHECKPOINT_MISSING")
        reconciliation = durable.reconcile_unknown_outcome(final, item)
        if reconciliation.get("outcome") != "KNOWN_STATE":
            raise NodeArchitectureError("DAG_PERSISTENCE_OUTCOME_UNKNOWN", str(reconciliation))
        readback = durable.validate_readback(final, item)
        if readback.get("outcome") != "PASS":
            raise NodeArchitectureError("DAG_PERSISTENCE_READBACK_FAILED")
        result["persistence"] = {"revision": readback["revision"],
                                  "state_digest": readback["state_digest"],
                                  "store_digest": final.get("store_digest"),
                                  "readback": "PASS"}
        return result

    def execute(self, *, root_manifest: Mapping[str, Any],
                child_node_allocations: list[Mapping[str, Any]],
                authority: Mapping[str, Any] | None, canonical_state: Mapping[str, Any],
                checkpoint: dict[str, Any] | None = None,
                lease_owner: str = "recursive-run-dag", _persist_hook: Any = None,
                **event_context: Any) -> dict[str, Any]:
        from tools.node_architect.universal_run_kernel import GATES, verify_record_digest

        if (not isinstance(root_manifest, Mapping) or root_manifest.get("run_kind") != "ROOT"
                or root_manifest.get("parent_run_ref") is not None
                or root_manifest.get("invoking_node_allocation_ref") is not None
                or not verify_record_digest(root_manifest)):
            raise NodeArchitectureError("ROOT_RUN_MANIFEST_INVALID")
        if not isinstance(lease_owner, str) or not lease_owner.strip():
            raise NodeArchitectureError("DAG_LEASE_OWNER_INVALID")
        store = checkpoint if checkpoint is not None else {}
        leases = store.setdefault("leases", {})
        root_id = str(root_manifest["run_id"])
        if leases.get(root_id) not in (None, lease_owner):
            raise NodeArchitectureError("DAG_LEASE_HELD", root_id)
        leases[root_id] = lease_owner
        run_receipts = store.setdefault("run_receipts", {})
        try:
            visited: set[str] = set()
            active: set[str] = set()
            node_count = 1

            def run_one(run_id: str, specs: list[Mapping[str, Any]], depth: int,
                        run_outcomes: Mapping[str, Any] | None = None,
                        run_authority: Mapping[str, Any] | None = None,
                        run_state: Any = None,
                        run_canonical_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
                nonlocal node_count
                if run_canonical_state is None:
                    run_canonical_state = canonical_state
                if run_authority is None:
                    run_authority = authority
                if run_state is None:
                    run_state = event_context.get("state")
                if run_state is None and self._state_factory is not None:
                    run_state = store.setdefault("runtime_states", {}).setdefault(run_id, self._state_factory())
                if run_id in active:
                    raise NodeArchitectureError("DAG_CYCLE", run_id)
                if depth > self.max_depth:
                    raise NodeArchitectureError("DAG_MAX_DEPTH_EXCEEDED", run_id)
                if run_id in visited:
                    raise NodeArchitectureError("CHILD_RUN_ID_DUPLICATE", run_id)
                visited.add(run_id)
                active.add(run_id)
                cached = run_receipts.get(run_id)
                # Only accepted terminal receipts are replay-cached. FAILED/WAITING
                # attempts are recoverable from their gate cursor and may be retried.
                if isinstance(cached, Mapping) and cached.get("status") == "COMPLETED":
                    active.remove(run_id)
                    return copy.deepcopy(dict(cached))

                gate_store = store.setdefault("gates", {}).setdefault(run_id, {})
                evidence: dict[str, Any] = {}
                readbacks: dict[str, Any] = {}
                outcomes: dict[str, Any] = {}
                g6 = None
                failure = None
                waiting = False
                gate_sequence = GATES[:3] if specs else GATES
                for gate in gate_sequence:
                    saved = gate_store.get(gate)
                    if isinstance(saved, Mapping):
                        evidence[gate] = copy.deepcopy(saved.get("evidence"))
                        readbacks[gate] = copy.deepcopy(saved.get("target_readback"))
                        outcomes[gate] = copy.deepcopy(saved.get("outcome"))
                        if gate == "G6":
                            g6 = copy.deepcopy(saved.get("g6_receipt"))
                        continue
                    kwargs = dict(event_context)
                    kwargs.update({"canonical_state": run_canonical_state, "run_id": run_id,
                                   "gate": self._host_gate(gate), "requested_action": "RUN", "authority": run_authority,
                                   "state": run_state, "event_id": f"{run_id}:{gate}"})
                    response = self.runtime_event(**kwargs)
                    host_response: Mapping[str, Any] = response if isinstance(response, Mapping) else {}
                    semantic_host = host_response.get("status") in {
                        "SEMANTIC_NODE_COMPLETE", "SEMANTIC_NODE_BLOCKED", "SEMANTIC_NODE_NOT_APPLICABLE"
                    }
                    if semantic_host:
                        host_status = str(host_response.get("status"))
                        if host_status == "SEMANTIC_NODE_BLOCKED":
                            waiting = True
                            failure = str(host_response.get("reason_code") or "SEMANTIC_NODE_BLOCKED")
                            break
                        if host_status == "SEMANTIC_NODE_NOT_APPLICABLE":
                            applicability = host_response.get("applicability")
                            raw_outcome = host_response.get("transfer_outcome")
                            if (isinstance(applicability, Mapping)
                                    and applicability.get("decision") == "NOT_APPLICABLE"
                                    and isinstance(raw_outcome, Mapping)
                                    and raw_outcome.get("kind") in TRANSFER_OUTCOME_KINDS
                                    and isinstance(raw_outcome.get("reason"), str)
                                    and raw_outcome["reason"].strip()):
                                outcome = TransferOutcome(str(raw_outcome["kind"]), raw_outcome["reason"]).to_dict()
                                outcomes[gate] = outcome
                                gate_store[gate] = {"outcome": outcome}
                                continue
                            waiting = True
                            failure = "CANONICAL_NOT_APPLICABLE_OUTCOME_MISSING"
                            break
                        next_route = host_response.get("next_route")
                        readback = host_response.get("readback")
                        if (not isinstance(next_route, Mapping)
                                or next_route.get("disposition") != "stop"
                                or next_route.get("next_node") is not None
                                or next_route.get("next_action") is not None
                                or not next_route.get("next_gate")):
                            waiting = True
                            failure = "CANONICAL_NEXT_ROUTE_INVALID"
                            break
                        evidence_summary = host_response.get("evidence_summary")
                        if (not isinstance(readback, Mapping)
                                or readback.get("status") != "VERIFIED"
                                or host_response.get("canonical_readback_verified") is not True
                                or not isinstance(evidence_summary, Mapping)):
                            waiting = True
                            failure = "CANONICAL_GATE_READBACK_OR_EVIDENCE_MISSING"
                            break
                        response = {**dict(host_response), "evidence": {
                            "semantic_status": "SEMANTIC_NODE_COMPLETE",
                            "evidence_summary": dict(evidence_summary),
                            "readback": dict(readback),
                            "next_route": dict(next_route),
                        }, "target_readback": dict(readback)}
                    if isinstance(response, Mapping) and response.get("status") == "AGENT_RUNTIME_BLOCKED":
                        waiting = True
                        failure = str(response.get("reason_code") or "AGENT_RUNTIME_BLOCKED")
                        break
                    if not isinstance(response, Mapping) or response.get("status") not in {"COMPLETED", "PASSED", "SEMANTIC_NODE_COMPLETE"}:
                        response_status = str(response.get("status", "")).upper() if isinstance(response, Mapping) else ""
                        waiting = response_status in {"WAITING", "HOLD", "BLOCKED"}
                        failure = str(response.get("reason_code", "CHILD_EVENT_NOT_COMPLETED")) if isinstance(response, Mapping) else "CHILD_EVENT_INVALID"
                        break
                    if gate == "G3" and not isinstance(response.get("evidence"), Mapping):
                        failure = "CHILD_GATE_EVIDENCE_MISSING"
                        break
                    if gate in {"G4", "G5"} and (not isinstance(response.get("target_readback"), Mapping)
                                                   or response["target_readback"].get("status") != "VERIFIED"):
                        failure = "CHILD_TARGET_READBACK_MISSING"
                        break
                    raw_outcome = (run_outcomes or {}).get(gate)
                    outcome = None
                    if raw_outcome is not None:
                        if (not isinstance(raw_outcome, Mapping)
                                or raw_outcome.get("kind") not in TRANSFER_OUTCOME_KINDS
                                or not str(raw_outcome.get("reason", "")).strip()):
                            failure = "TRANSFER_OUTCOME_INVALID"
                            break
                        outcome = TransferOutcome(str(raw_outcome["kind"]), str(raw_outcome["reason"])).to_dict()
                    if gate == "G6":
                        candidate = response.get("g6_receipt")
                        if not isinstance(candidate, Mapping) or candidate.get("status") != "ACCEPTED" or not candidate.get("receipt_id"):
                            failure = ("G6_ACCEPTANCE_EVIDENCE_MISSING"
                                       if response.get("status") == "SEMANTIC_NODE_COMPLETE"
                                       else "CHILD_G6_NOT_ACCEPTED")
                            waiting = response.get("status") == "SEMANTIC_NODE_COMPLETE"
                            break
                        g6 = copy.deepcopy(dict(candidate))
                    evidence[gate] = copy.deepcopy(response.get("evidence"))
                    readbacks[gate] = copy.deepcopy(response.get("target_readback"))
                    outcomes[gate] = outcome
                    gate_store[gate] = {"evidence": evidence[gate], "target_readback": readbacks[gate],
                                        "outcome": outcome, "g6_receipt": g6}
                    if _persist_hook is not None:
                        _persist_hook(store, run_id=run_id, node_id=f"{run_id}:{gate}")

                children: list[dict[str, Any]] = []
                if not failure:
                    ordered = self._ordered(list(specs))
                    node_count += len(ordered)
                    if node_count > self.max_nodes:
                        raise NodeArchitectureError("DAG_BUDGET_EXCEEDED", str(node_count))
                    for spec in ordered:
                        child_id = str(spec.get("child_run_id", ""))
                        allocation = spec.get("node_allocation")
                        if not child_id or child_id == run_id:
                            raise NodeArchitectureError("CHILD_PARENT_SELF_LOOP", child_id)
                        if not isinstance(allocation, Mapping):
                            raise NodeArchitectureError("NODE_ALLOCATION_REQUIRED", child_id)
                        generation_key = f"{run_id}:{allocation.get('node_allocation_id')}"
                        generations = store.setdefault("generations", {}).setdefault(generation_key, [])
                        existing_state = next((state for state in generations
                                               if state.get("child_run_ref") == child_id), None)
                        existing_open = existing_state is not None and existing_state.get("terminal_state") == "OPEN"
                        materialization_key = f"{run_id}:{child_id}"
                        if existing_open:
                            materialization = store.setdefault("materializations", {}).get(materialization_key)
                            if not isinstance(materialization, Mapping):
                                raise NodeArchitectureError("CHILD_CHECKPOINT_INVALID", child_id)
                        elif existing_state is not None and existing_state.get("terminal_state") == "ACCEPTED":
                            # Accepted sibling generations are immutable and idempotently
                            # reused when a different sibling resumes from WAITING.
                            materialization = store.setdefault("materializations", {}).get(materialization_key)
                            cached_child = run_receipts.get(child_id)
                            if not isinstance(materialization, Mapping) or not isinstance(cached_child, Mapping):
                                raise NodeArchitectureError("CHILD_CHECKPOINT_INVALID", child_id)
                            children.append(copy.deepcopy(dict(cached_child)))
                            continue
                        else:
                            materialization = materialize_child_run(
                                record_id=f"materialization:{run_id}:{child_id}", parent_run_id=run_id,
                                child_run_id=child_id, node_allocation=allocation,
                                created_at=str(spec.get("created_at", "1970-01-01T00:00:00Z")),
                                created_by=spec.get("created_by", {"kind": "agent", "id": "recursive-run-dag"}),
                                generation_states=generations,
                                reason="RERUN_SUBTREE" if existing_state is not None else "INITIAL",
                            )
                            generations.append({"child_run_ref": child_id, "generation": materialization["generation"], "terminal_state": "OPEN"})
                            store.setdefault("materializations", {})[materialization_key] = copy.deepcopy(materialization)
                            if _persist_hook is not None:
                                _persist_hook(store, run_id=run_id, node_id=f"materialization:{child_id}")
                        child_manifest = create_run_manifest_revision(
                            record_id=f"manifest:{child_id}", run_id=child_id, revision=1,
                            run_kind="CHILD", created_at=str(spec.get("created_at", "1970-01-01T00:00:00Z")),
                            created_by=spec.get("created_by", {"kind": "agent", "id": "recursive-run-dag"}),
                            parent_run_ref=run_id,
                            invoking_node_allocation_ref=str(allocation.get("record_id", "")),
                        )
                        store.setdefault("child_manifests", {})[child_id] = copy.deepcopy(child_manifest)
                        if not verify_record_digest(child_manifest):
                            raise NodeArchitectureError("CHILD_RUN_MANIFEST_INVALID", child_id)
                        child_outcomes = spec.get("outcomes", {})
                        if not isinstance(child_outcomes, Mapping):
                            raise NodeArchitectureError("TRANSFER_OUTCOME_INVALID", child_id)
                        # COMMAND #193 F4: reject child-supplied authority or canonical
                        # context BEFORE dispatch. C2 may later supply a verified derived
                        # receipt through a separate typed path; arbitrary spec overrides
                        # are never authority.
                        if spec.get("authority") is not None:
                            raise NodeArchitectureError("CHILD_AUTHORITY_OVERRIDE_FORBIDDEN", child_id)
                        if spec.get("canonical_state") is not None:
                            raise NodeArchitectureError("CHILD_CANONICAL_STATE_OVERRIDE_FORBIDDEN", child_id)
                        child = run_one(child_id, list(spec.get("children", ())), depth + 1, child_outcomes,
                                        run_authority, run_state, run_canonical_state)
                        # COMMAND #193 F1: a failed/held child blocks parent G4/G5/G6,
                        # but does NOT stop independent siblings from making progress.
                        child_status = child.get("status")
                        child_accepted = (child.get("g6_receipt") or {}).get("status") == "ACCEPTED"
                        generations[-1]["terminal_state"] = (
                            "ACCEPTED" if child_accepted else "OPEN" if child_status == "WAITING" else "FAILED"
                        )
                        if not child_accepted and failure is None:
                            failure = "CHILD_G6_NOT_ACCEPTED"
                        if child_status == "WAITING":
                            waiting = True
                        child["run_manifest"] = child_manifest
                        child["materialization_receipt"] = materialization
                        children.append(child)

                if specs and not failure:
                    # Parent G3 (composition review) and G4-G6 run only after every
                    # required child has an ACCEPTED G6 receipt.
                    for gate in GATES[3:]:
                        saved = gate_store.get(gate)
                        if isinstance(saved, Mapping):
                            evidence[gate] = copy.deepcopy(saved.get("evidence"))
                            readbacks[gate] = copy.deepcopy(saved.get("target_readback"))
                            outcomes[gate] = copy.deepcopy(saved.get("outcome"))
                            if gate == "G6":
                                g6 = copy.deepcopy(saved.get("g6_receipt"))
                            continue
                        kwargs = dict(event_context)
                        kwargs.update({"canonical_state": run_canonical_state, "run_id": run_id,
                                       "gate": self._host_gate(gate), "requested_action": "RUN", "authority": run_authority,
                                       "state": run_state, "event_id": f"{run_id}:{gate}"})
                        response = self.runtime_event(**kwargs)
                        host_response: Mapping[str, Any] = response if isinstance(response, Mapping) else {}
                        if host_response.get("status") == "SEMANTIC_NODE_BLOCKED":
                            waiting = True
                            failure = str(host_response.get("reason_code") or "SEMANTIC_NODE_BLOCKED")
                            break
                        if host_response.get("status") == "SEMANTIC_NODE_NOT_APPLICABLE":
                            applicability = host_response.get("applicability")
                            raw_outcome = host_response.get("transfer_outcome")
                            if (isinstance(applicability, Mapping)
                                    and applicability.get("decision") == "NOT_APPLICABLE"
                                    and isinstance(raw_outcome, Mapping)
                                    and raw_outcome.get("kind") in TRANSFER_OUTCOME_KINDS
                                    and isinstance(raw_outcome.get("reason"), str)
                                    and raw_outcome["reason"].strip()):
                                outcome = TransferOutcome(str(raw_outcome["kind"]), raw_outcome["reason"]).to_dict()
                                outcomes[gate] = outcome
                                gate_store[gate] = {"outcome": outcome}
                                continue
                            waiting = True
                            failure = "CANONICAL_NOT_APPLICABLE_OUTCOME_MISSING"
                            break
                        if host_response.get("status") == "SEMANTIC_NODE_COMPLETE":
                            next_route = host_response.get("next_route")
                            readback = host_response.get("readback")
                            evidence_summary = host_response.get("evidence_summary")
                            if (not isinstance(next_route, Mapping)
                                    or next_route.get("disposition") != "stop"
                                    or next_route.get("next_node") is not None
                                    or next_route.get("next_action") is not None
                                    or not next_route.get("next_gate")):
                                waiting = True
                                failure = "CANONICAL_NEXT_ROUTE_INVALID"
                                break
                            if (not isinstance(readback, Mapping) or readback.get("status") != "VERIFIED"
                                    or host_response.get("canonical_readback_verified") is not True
                                    or not isinstance(evidence_summary, Mapping)):
                                waiting = True
                                failure = "CANONICAL_GATE_READBACK_OR_EVIDENCE_MISSING"
                                break
                            response = {**dict(host_response), "evidence": {
                                "semantic_status": "SEMANTIC_NODE_COMPLETE",
                                "evidence_summary": dict(evidence_summary),
                                "readback": dict(readback),
                                "next_route": dict(next_route),
                            }, "target_readback": dict(readback)}
                        if isinstance(response, Mapping) and response.get("status") == "AGENT_RUNTIME_BLOCKED":
                            waiting = True
                            failure = str(response.get("reason_code") or "AGENT_RUNTIME_BLOCKED")
                            break
                        if not isinstance(response, Mapping) or response.get("status") not in {"COMPLETED", "PASSED", "SEMANTIC_NODE_COMPLETE"}:
                            failure = str(response.get("reason_code", "CHILD_EVENT_NOT_COMPLETED")) if isinstance(response, Mapping) else "CHILD_EVENT_INVALID"
                            waiting = isinstance(response, Mapping) and response.get("status") in {"WAITING", "HOLD", "BLOCKED"}
                            break
                        if gate in {"G4", "G5"} and (not isinstance(response.get("target_readback"), Mapping)
                                                       or response["target_readback"].get("status") != "VERIFIED"):
                            failure = "CHILD_TARGET_READBACK_MISSING"
                            break
                        if gate == "G6":
                            candidate = response.get("g6_receipt")
                            if not isinstance(candidate, Mapping) or candidate.get("status") != "ACCEPTED" or not candidate.get("receipt_id"):
                                failure = ("G6_ACCEPTANCE_EVIDENCE_MISSING"
                                           if response.get("status") == "SEMANTIC_NODE_COMPLETE"
                                           else "CHILD_G6_NOT_ACCEPTED")
                                waiting = response.get("status") == "SEMANTIC_NODE_COMPLETE"
                                break
                            g6 = copy.deepcopy(dict(candidate))
                        evidence[gate] = copy.deepcopy(response.get("evidence"))
                        readbacks[gate] = copy.deepcopy(response.get("target_readback"))
                        outcomes[gate] = None
                        gate_store[gate] = {"evidence": evidence[gate], "target_readback": readbacks[gate],
                                            "outcome": None, "g6_receipt": g6}

                if not failure:
                    if not isinstance(g6, Mapping) or g6.get("status") != "ACCEPTED" or not g6.get("receipt_id"):
                        failure = "CHILD_G6_NOT_ACCEPTED"
                accepted_children = all((c.get("g6_receipt") or {}).get("status") == "ACCEPTED" for c in children)
                failed = bool(failure) or not accepted_children
                result = {
                    "run_id": run_id, "status": "WAITING" if waiting else "FAILED" if failed else "COMPLETED",
                    "failure_code": failure or ("CHILD_G6_NOT_ACCEPTED" if not accepted_children else None),
                    "c1_status": "INTEGRATION_PENDING",
                    "gate_evidence": evidence, "gate_readbacks": readbacks, "gate_outcomes": outcomes,
                    "children": children,
                    "g6_receipt": copy.deepcopy(dict(g6)) if isinstance(g6, Mapping) and g6.get("status") == "ACCEPTED" else None,
                    "parent_aggregation": {"g3": "EVIDENCE_BOUND" if "G3" in evidence else "FAILED",
                                           "g4": "INTEGRATED" if accepted_children and not failed else "FAILED",
                                           "g5": "VERIFIED" if accepted_children and not failed else "FAILED",
                                           "g6": "ACCEPTED" if not failed and g6 else "FAILED"},
                }
                if result["status"] == "COMPLETED":
                    run_receipts[run_id] = copy.deepcopy(result)
                else:
                    # Keep recoverable WAITING/FAILED state out of terminal cache;
                    # gate_store remains the resumable cursor for the next attempt.
                    run_receipts.pop(run_id, None)
                active.remove(run_id)
                if _persist_hook is not None:
                    _persist_hook(store, run_id=run_id, node_id=f"receipt:{run_id}")
                return result

            return run_one(root_id, list(child_node_allocations), 1)
        finally:
            if leases.get(root_id) == lease_owner:
                leases.pop(root_id, None)


__all__ = [
    "CHILD_INSTANCE_POLICY",
    "CompositionVerificationError",
    "DAGBudgetError",
    "NODE_KINDS",
    "NodeAllocation",
    "NodeArchitectureError",
    "NodeDefinition",
    "RecursiveRunDag",
    "REQUIREMENT_KINDS",
    "SingleActiveError",
    "allocate_node",
    "build_node_definition",
    "enforce_dag_budget",
    "promote_node",
    "resolve_single_active",
    "verify_parent_composition",
]
