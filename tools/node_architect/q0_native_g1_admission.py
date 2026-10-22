"""Fail-closed, non-authorizing admission contract for native UR.G1 plans."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


class Q0NativeG1AdmissionError(ValueError):
    """Stable error code for invalid native UR.G1 admission evidence."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code


def _fail(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise Q0NativeG1AdmissionError(code, detail)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _seal(body: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()


def _allocation_digest(allocation: Mapping[str, Any]) -> str | None:
    content_digest = allocation.get("content_digest")
    if isinstance(content_digest, Mapping):
        return content_digest.get("value")
    return allocation.get("digest")


def _dag_order(runtime_plan: Mapping[str, Any]) -> tuple[str, ...]:
    dag = runtime_plan.get("dag")
    _fail(isinstance(dag, Mapping) and isinstance(dag.get("nodes"), list), "PLAN_DAG_INVALID")
    nodes: dict[str, set[str]] = {}
    for node in dag["nodes"]:
        _fail(isinstance(node, Mapping) and isinstance(node.get("id"), str), "PLAN_DAG_INVALID")
        node_id = node["id"]
        _fail(node_id not in nodes, "PLAN_DAG_INVALID", "duplicate node")
        predecessors = node.get("predecessors", [])
        _fail(isinstance(predecessors, list) and all(isinstance(p, str) for p in predecessors), "PLAN_DAG_INVALID")
        nodes[node_id] = set(predecessors)
    _fail(set(nodes) >= {f"W{i}" for i in range(1, 7)}, "PLAN_DAG_INVALID", "W1..W6 absent")
    _fail(all(f"W{i-1}" in nodes[f"W{i}"] for i in range(2, 7)), "WORK_ORDER_INVALID")
    _fail(all(pred in nodes for preds in nodes.values() for pred in preds), "PLAN_DAG_INVALID", "unknown predecessor")
    remaining = {name: set(preds) for name, preds in nodes.items()}
    ordered: list[str] = []
    while remaining:
        ready = sorted(name for name, preds in remaining.items() if not preds)
        _fail(bool(ready), "PLAN_DAG_INVALID", "cycle")
        for name in ready:
            ordered.append(name)
            remaining.pop(name)
        for preds in remaining.values():
            preds.difference_update(ready)
    w_order = tuple(name for name in ordered if name in {f"W{i}" for i in range(1, 7)})
    _fail(w_order == tuple(f"W{i}" for i in range(1, 7)), "WORK_ORDER_INVALID")
    return w_order


_RECEIPT_KEYS = {
    "schema_id", "schema_version", "artifact_type", "run_id", "runtime_plan_digest",
    "candidate_sha", "source_head", "node_allocation_id", "node_allocation_digest",
    "work_id", "work_order", "qualification_entries", "provenance_ref", "decision_ref",
    "authority_granted", "effect_authority_granted", "consumed", "receipt_digest",
}


def validate_native_g1_plan_receipt(
    receipt: Any, *, run_id: str, runtime_plan_digest: str, candidate_sha: str,
    node_allocation: Mapping[str, Any], runtime_plan: Mapping[str, Any], source_head: str,
) -> dict[str, Any]:
    """Validate a digest-sealed native plan-evidence receipt; never grants authority."""
    _fail(isinstance(receipt, Mapping), "RECEIPT_TYPE_INVALID")
    value = dict(receipt)
    _fail(set(value) == _RECEIPT_KEYS, "RECEIPT_KEYS_INVALID")
    _fail(value.get("schema_id") == "gwc.q0.native-g1-plan-receipt.v1" and value.get("schema_version") == 1 and value.get("artifact_type") == "native-g1-plan-receipt", "RECEIPT_SCHEMA_INVALID")
    digest = value.get("receipt_digest")
    body = {key: item for key, item in value.items() if key != "receipt_digest"}
    _fail(isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest) and digest == _seal(body), "RECEIPT_SEAL_INVALID")
    _fail(isinstance(run_id, str) and bool(run_id.strip()) and value.get("run_id") == run_id, "RUN_ID_MISMATCH")
    _fail(isinstance(runtime_plan_digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", runtime_plan_digest) and runtime_plan.get("digest") == runtime_plan_digest == value.get("runtime_plan_digest"), "PLAN_DIGEST_MISMATCH")
    _fail(isinstance(candidate_sha, str) and re.fullmatch(r"[0-9a-f]{40}", candidate_sha) and value.get("candidate_sha") == candidate_sha == source_head and value.get("source_head") == source_head, "SOURCE_SHA_MISMATCH")
    plan_source = runtime_plan.get("source_binding", {})
    if isinstance(plan_source, Mapping) and plan_source.get("pre_head_sha") is not None:
        _fail(plan_source.get("pre_head_sha") == source_head, "SOURCE_SHA_MISMATCH")
    _fail(isinstance(node_allocation, Mapping), "NODE_ALLOCATION_MISMATCH")
    alloc_id = node_allocation.get("node_allocation_id")
    alloc_digest = _allocation_digest(node_allocation)
    _fail(isinstance(alloc_id, str) and bool(alloc_id.strip()) and isinstance(alloc_digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", alloc_digest), "NODE_ALLOCATION_MISMATCH")
    _fail(value.get("node_allocation_id") == alloc_id and value.get("node_allocation_digest") == alloc_digest, "NODE_ALLOCATION_MISMATCH")
    _fail(isinstance(runtime_plan.get("node_allocations"), list) and alloc_id in runtime_plan["node_allocations"], "NODE_ALLOCATION_MISMATCH")
    _dag_order(runtime_plan)
    dag_ids = {node.get("id") for node in runtime_plan["dag"]["nodes"] if isinstance(node, Mapping)}
    _fail(value.get("work_id") in dag_ids, "WORK_NOT_IN_PLAN_DAG")
    _fail(value.get("work_order") == [f"W{i}" for i in range(1, 7)], "WORK_ORDER_INVALID")
    from tools.node_architect.q0_qualification import MANDATORY_QUALIFICATION_ENTRIES
    entries = value.get("qualification_entries")
    _fail(isinstance(entries, Mapping) and set(entries) == set(MANDATORY_QUALIFICATION_ENTRIES) and all(entries[k] == "PASS" for k in MANDATORY_QUALIFICATION_ENTRIES), "QUALIFICATION_ENTRIES_INCOMPLETE")
    _fail(isinstance(value.get("provenance_ref"), str) and bool(value["provenance_ref"].strip()), "PROVENANCE_REF_REQUIRED")
    _fail(isinstance(value.get("decision_ref"), str) and bool(value["decision_ref"].strip()), "DECISION_REF_REQUIRED")
    _fail(value.get("authority_granted") is False and value.get("effect_authority_granted") is False and value.get("consumed") is False, "AUTHORITY_FIELDS_INVALID")
    return {"valid": True, "receipt_digest": digest, "run_id": run_id,
            "runtime_plan_digest": runtime_plan_digest, "node_allocation_id": alloc_id,
            "authority_granted": False, "effect_authority_granted": False, "consumed": False}


def build_native_g1_plan_receipt(
    *, run_id: str = "cmd163-canonical-run", runtime_plan_digest: str = "sha256:" + "a" * 64,
    candidate_sha: str = "b" * 40, node_allocation: Mapping[str, Any] | None = None,
    runtime_plan: Mapping[str, Any] | None = None, source_head: str | None = None,
    provenance_ref: str = "evidence:native-g1/provenance", decision_ref: str = "decision:native-g1/plan",
) -> dict[str, Any]:
    """Build a canonical receipt from explicit bindings (or a synthetic unit fixture)."""
    source_head = candidate_sha if source_head is None else source_head
    node_allocation = node_allocation or {"node_allocation_id": "alloc-1", "content_digest": {"value": "sha256:" + "c" * 64}}
    if runtime_plan is None:
        runtime_plan = {
            "digest": runtime_plan_digest, "source_binding": {"pre_head_sha": source_head},
            "node_allocations": [node_allocation.get("node_allocation_id")],
            "dag": {"nodes": [{"id": f"W{i}", "predecessors": [] if i == 1 else [f"W{i-1}"]} for i in range(1, 7)]},
        }
    from tools.node_architect.q0_qualification import MANDATORY_QUALIFICATION_ENTRIES
    body = {
        "schema_id": "gwc.q0.native-g1-plan-receipt.v1", "schema_version": 1,
        "artifact_type": "native-g1-plan-receipt", "run_id": run_id,
        "runtime_plan_digest": runtime_plan_digest, "candidate_sha": candidate_sha,
        "source_head": source_head, "node_allocation_id": node_allocation.get("node_allocation_id"),
        "node_allocation_digest": _allocation_digest(node_allocation), "work_id": "W6",
        "work_order": [f"W{i}" for i in range(1, 7)],
        "qualification_entries": {name: "PASS" for name in MANDATORY_QUALIFICATION_ENTRIES},
        "provenance_ref": provenance_ref, "decision_ref": decision_ref,
        "authority_granted": False, "effect_authority_granted": False, "consumed": False,
    }
    return {**body, "receipt_digest": _seal(body)}


def materialize_native_g1_genesis(
    receipt: Any, *, worktree_root: str | Path, sandbox_dir: str | Path,
    runtime_plan: Mapping[str, Any] | None = None,
    node_allocation: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Write one idempotent non-authorizing genesis JSON artifact inside sandbox_dir."""
    _fail(isinstance(runtime_plan, Mapping) and isinstance(node_allocation, Mapping), "PLAN_BINDING_REQUIRED")
    _fail(isinstance(receipt, Mapping), "RECEIPT_TYPE_INVALID")
    root = Path(worktree_root).resolve()
    sandbox_input = Path(sandbox_dir)
    _fail(".." not in sandbox_input.parts, "SANDBOX_PATH_INVALID")
    sandbox = sandbox_input.resolve()
    _fail(sandbox != root and ".gwc" not in sandbox.parts and "checkpoints" not in sandbox.parts, "SANDBOX_PATH_INVALID")
    receipt_digest = receipt.get("receipt_digest")
    _fail(isinstance(receipt_digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", receipt_digest), "RECEIPT_SEAL_INVALID")
    candidate_sha = receipt.get("candidate_sha")
    plan_digest = runtime_plan.get("digest") if isinstance(runtime_plan, Mapping) else None
    validate_native_g1_plan_receipt(
        receipt, run_id=receipt.get("run_id"), runtime_plan_digest=plan_digest,
        candidate_sha=candidate_sha, node_allocation=node_allocation, runtime_plan=runtime_plan,
        source_head=receipt.get("source_head"),
    )
    sandbox.mkdir(parents=True, exist_ok=True)
    artifact = (sandbox / f"native-g1-genesis-{receipt_digest.split(':', 1)[1]}.json").resolve()
    _fail(artifact.parent == sandbox, "SANDBOX_PATH_INVALID")
    content = {"artifact_type": "native-g1-genesis", "receipt_digest": receipt_digest,
               "authority_granted": False, "effect_authority_granted": False, "consumed": False}
    raw = _canonical(content) + b"\n"
    if artifact.exists():
        _fail(artifact.read_bytes() == raw, "GENESIS_CONTENT_MISMATCH")
    else:
        artifact.write_bytes(raw)
    return {"ref": str(artifact), "digest": "sha256:" + hashlib.sha256(raw).hexdigest()}


__all__ = ["Q0NativeG1AdmissionError", "build_native_g1_plan_receipt",
           "materialize_native_g1_genesis", "validate_native_g1_plan_receipt"]
