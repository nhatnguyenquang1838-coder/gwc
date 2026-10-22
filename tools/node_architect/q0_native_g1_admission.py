"""Fail-closed, non-authorizing admission contract for native UR.G1 plans."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
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


def _validate_predecessor(predecessor: Any, successor_run_id: str, successor_digest: str) -> dict[str, Any]:
    _fail(predecessor is not None, "PREDECESSOR_BINDING_REQUIRED")
    keys = {"kind", "run_id", "runtime_plan_ref", "runtime_plan_digest", "checkpoint_ref",
            "context_digest", "owner_session_id", "source_head"}
    _fail(isinstance(predecessor, Mapping) and set(predecessor) == keys, "PREDECESSOR_BINDING_INVALID")
    value = dict(predecessor)
    _fail(all(isinstance(value[k], str) and bool(value[k].strip()) for k in keys), "PREDECESSOR_BINDING_INVALID")
    _fail(value["run_id"] != successor_run_id, "PREDECESSOR_SELF_REFERENCE")
    _fail(re.fullmatch(r"sha256:[0-9a-f]{64}", value["runtime_plan_digest"]) is not None,
          "PREDECESSOR_BINDING_INVALID")
    _fail(value["runtime_plan_digest"] != successor_digest, "PLAN_DIGEST_MISMATCH")
    try:
        plan_bytes = Path(value["runtime_plan_ref"]).read_bytes()
    except OSError as exc:
        raise Q0NativeG1AdmissionError("PREDECESSOR_PLAN_UNREADABLE") from exc
    _fail("sha256:" + hashlib.sha256(plan_bytes).hexdigest() == value["runtime_plan_digest"], "PLAN_DIGEST_MISMATCH")
    checkpoint = Path(value["checkpoint_ref"])
    _fail(checkpoint.is_file(), "PREDECESSOR_CHECKPOINT_UNBOUND")
    try:
        uri = checkpoint.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            row = db.execute("SELECT context_digest,state FROM engineering_workflow WHERE run=?",
                             (value["run_id"],)).fetchone()
    except (OSError, sqlite3.Error) as exc:
        raise Q0NativeG1AdmissionError("PREDECESSOR_CHECKPOINT_UNBOUND") from exc
    _fail(row is not None and row[0] == value["context_digest"], "PREDECESSOR_CONTEXT_MISMATCH")
    try:
        state = json.loads(row[1])
    except (TypeError, ValueError):
        state = {}
    recorded_session = state.get("executor", {}).get("session_id") if isinstance(state, Mapping) else None
    if recorded_session is not None:
        _fail(recorded_session == value["owner_session_id"], "PREDECESSOR_OWNER_MISMATCH")
    return value


def build_live_activation_effect_envelope(*, idempotency_key: str) -> dict[str, Any]:
    """Describe, but never execute, separately-authorized live activation effects."""
    _fail(isinstance(idempotency_key, str) and bool(idempotency_key.strip()), "IDEMPOTENCY_KEY_REQUIRED")
    return {"schema_id": "gwc.q0.live-activation-effect-envelope.v1",
            "kind": "LIVE_ACTIVATION_EFFECT_ENVELOPE",
            "api_entrypoint": "tools.node_architect.q0_m1_m7_integration.activate_successor_plan",
            "effects": [
                {"effect": "selector_write", "precondition": "separate_grant_and_successor_plan_valid"},
                {"effect": "checkpoint_write", "precondition": "selector_binding_and_checkpoint_cas_valid"},
                {"effect": "cursor_advance", "precondition": "checkpoint_readback_verified"}],
            "authority_required": "SEPARATE_HUMAN_OR_CONTROLLER_GRANT",
            "authority_granted": False, "executed": False,
            "idempotency_key": idempotency_key,
            "refusal_codes": ["LIVE_ACTIVATION_AUTHORITY_REQUIRED"]}


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
    "work_id", "work_order", "plan_coverage", "qualification_results", "provenance_ref", "decision_ref",
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
    _fail(value.get("schema_id") == "gwc.q0.native-g1-plan-receipt.v2" and value.get("schema_version") == 2 and value.get("artifact_type") == "native-g1-plan-receipt", "RECEIPT_SCHEMA_INVALID")
    digest = value.get("receipt_digest")
    body = {key: item for key, item in value.items() if key != "receipt_digest"}
    _fail(isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest) and digest == _seal(body), "RECEIPT_SEAL_INVALID")
    _fail(isinstance(run_id, str) and bool(run_id.strip()) and value.get("run_id") == run_id == runtime_plan.get("run_id"), "RUN_ID_MISMATCH")
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
    plan_coverage = value.get("plan_coverage")
    _fail(
        isinstance(plan_coverage, Mapping)
        and set(plan_coverage) == set(MANDATORY_QUALIFICATION_ENTRIES)
        and all(plan_coverage[name] == "PLANNED" for name in MANDATORY_QUALIFICATION_ENTRIES),
        "PLAN_COVERAGE_INVALID",
    )
    results = value.get("qualification_results")
    _fail(isinstance(results, Mapping), "QUALIFICATION_RESULT_INVALID")
    for entry, result in results.items():
        _fail(entry in MANDATORY_QUALIFICATION_ENTRIES, "QUALIFICATION_RESULT_INVALID")
        _fail(
            isinstance(result, Mapping)
            and set(result) == {"status", "evidence_ref"}
            and result.get("status") in {"PASS", "FAIL"}
            and isinstance(result.get("evidence_ref"), str)
            and bool(result["evidence_ref"].strip()),
            "QUALIFICATION_RESULT_INVALID",
        )
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
            "run_id": run_id,
            "digest": runtime_plan_digest, "source_binding": {"pre_head_sha": source_head},
            "node_allocations": [node_allocation.get("node_allocation_id")],
            "dag": {"nodes": [{"id": f"W{i}", "predecessors": [] if i == 1 else [f"W{i-1}"]} for i in range(1, 7)]},
        }
    from tools.node_architect.q0_qualification import MANDATORY_QUALIFICATION_ENTRIES
    body = {
        "schema_id": "gwc.q0.native-g1-plan-receipt.v2", "schema_version": 2,
        "artifact_type": "native-g1-plan-receipt", "run_id": run_id,
        "runtime_plan_digest": runtime_plan_digest, "candidate_sha": candidate_sha,
        "source_head": source_head, "node_allocation_id": node_allocation.get("node_allocation_id"),
        "node_allocation_digest": _allocation_digest(node_allocation), "work_id": "W6",
        "work_order": [f"W{i}" for i in range(1, 7)],
        "plan_coverage": {name: "PLANNED" for name in MANDATORY_QUALIFICATION_ENTRIES},
        "qualification_results": {},
        "provenance_ref": provenance_ref, "decision_ref": decision_ref,
        "authority_granted": False, "effect_authority_granted": False, "consumed": False,
    }
    return {**body, "receipt_digest": _seal(body)}


def materialize_native_g1_genesis(
    receipt: Any, *, worktree_root: str | Path, sandbox_dir: str | Path,
    runtime_plan: Mapping[str, Any] | None = None,
    node_allocation: Mapping[str, Any] | None = None,
    predecessor: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create and durably read back a canonical Universal v2 genesis RunState."""
    _fail(isinstance(runtime_plan, Mapping) and isinstance(node_allocation, Mapping), "PLAN_BINDING_REQUIRED")
    _fail(isinstance(receipt, Mapping), "RECEIPT_TYPE_INVALID")
    root = Path(worktree_root).resolve()
    sandbox_input = Path(sandbox_dir)
    _fail(".." not in sandbox_input.parts and not sandbox_input.is_symlink(), "SANDBOX_PATH_INVALID")
    sandbox = sandbox_input.resolve()
    _fail(sandbox != root and ".gwc" not in sandbox.parts and "checkpoints" not in sandbox.parts, "SANDBOX_PATH_INVALID")
    source_binding = runtime_plan.get("source_binding")
    _fail(isinstance(source_binding, Mapping), "PLAN_BINDING_INVALID")
    candidate_sha = source_binding.get("pre_head_sha")
    plan_digest = runtime_plan.get("digest")
    plan_run_id = runtime_plan.get("run_id")
    _fail(isinstance(plan_run_id, str) and bool(plan_run_id.strip()), "PLAN_IDENTITY_INVALID")
    _fail(isinstance(plan_digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", plan_digest), "PLAN_DIGEST_MISMATCH")
    validate_native_g1_plan_receipt(
        receipt, run_id=plan_run_id, runtime_plan_digest=plan_digest,
        candidate_sha=candidate_sha, node_allocation=node_allocation,
        runtime_plan=runtime_plan, source_head=candidate_sha,
    )
    predecessor_value = _validate_predecessor(predecessor, receipt["run_id"], plan_digest)
    sandbox.mkdir(parents=True, exist_ok=True)
    db_path = (sandbox / "native-g1-genesis.sqlite3").resolve()
    transition_path = (sandbox / "native-g1-transition-receipt.json").resolve()
    effect_envelope_path = (sandbox / "live-activation-effect-envelope.json").resolve()
    _fail(db_path.parent == sandbox and transition_path.parent == sandbox and
          effect_envelope_path.parent == sandbox, "SANDBOX_PATH_INVALID")
    receipt_digest = receipt["receipt_digest"]
    run_id = receipt["run_id"]
    node_id = "native-g1-genesis"
    from tools.node_architect.checkpoint_sqlite import read_checkpoint, write_checkpoint
    from tools.node_architect.universal_run_state import create_run_state_record, verify_run_state_record

    prior = read_checkpoint(db_path, task_id="SCRUM-781", run_id=run_id, node_id=node_id) if db_path.exists() else None
    if db_path.exists() and prior is None:
        import sqlite3
        with sqlite3.connect(str(db_path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM checkpoint_events").fetchone()[0]
        _fail(count == 0, "GENESIS_CONTENT_MISMATCH")
    if prior is not None:
        payload = prior["payload"]
        state = payload.get("run_state") if isinstance(payload, Mapping) else None
        _fail(isinstance(state, Mapping)
              and receipt_digest in state.get("provenance", {}).get("source_refs", [])
              and state.get("run_manifest_digest") == plan_digest.removeprefix("sha256:"),
              "GENESIS_CONTENT_MISMATCH")
        try:
            transition = json.loads(transition_path.read_text(encoding="utf-8")) if transition_path.is_file() else None
        except json.JSONDecodeError as exc:
            raise Q0NativeG1AdmissionError("GENESIS_CONTENT_MISMATCH") from exc
        _fail(isinstance(transition, Mapping) and transition.get("transition_digest") == _seal({k: v for k, v in transition.items() if k != "transition_digest"}), "GENESIS_CONTENT_MISMATCH")
        readback = read_back_genesis(db_path)
        return {"run_id": run_id, "state_digest": state["content_digest"]["value"],
                "transition_receipt_digest": transition["transition_digest"], "db_ref": str(db_path),
                "transition_receipt_ref": str(transition_path), "readback": readback}

    from datetime import datetime, timezone
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record_id = "RS-" + hashlib.sha256((receipt_digest + plan_digest).encode()).hexdigest()[:24]
    allocation_id = node_allocation["node_allocation_id"]
    gate_states = {f"UR.G{i}": ("PASSED" if i == 0 else "ACTIVE" if i == 1 else "NOT_STARTED") for i in range(7)}
    state = create_run_state_record(
        record_id=record_id, run_id=run_id,
        lifecycle_profile={"id": "gwc.universal-run.v2", "version": 2},
        run_manifest_ref=f"runtime-plan:{plan_run_id}", run_manifest_digest=plan_digest.removeprefix("sha256:"),
        state_revision=1, predecessor_state_ref=None, predecessor_state_digest=None,
        sequence=0, active_gate="UR.G1", gate_states=gate_states, terminal_state="OPEN",
        execution_refs={"runtime_plan_ref": f"runtime-plan:{plan_run_id}",
                        "runtime_plan_digest": plan_digest.removeprefix("sha256:"), "cursor_ref": str(db_path)},
        future_contract_refs={"target_contract_ref": None, "closure_receipt_ref": None,
                              "handoff_receipt_ref": None},
        created_at=created_at, created_by={"type": "system", "id": "q0-native-g1-admission"},
        provenance={"predecessor_refs": [f"runtime-plan:{plan_run_id}"],
                    "source_refs": [receipt_digest, f"node-allocation:{allocation_id}"]},
    )
    _fail(verify_run_state_record(state), "GENESIS_RUN_STATE_INVALID")
    envelope = build_live_activation_effect_envelope(
        idempotency_key=f"live-activation:{predecessor_value['run_id']}:{run_id}:{plan_digest}")
    transition_body = {
        "schema_id": "gwc.q0.native-g1-genesis-transition.v1", "schema_version": 1,
        "predecessor": {"identity": predecessor_value["run_id"],
                        "digest": predecessor_value["runtime_plan_digest"],
                        "checkpoint_ref": predecessor_value["checkpoint_ref"],
                        "context_digest": predecessor_value["context_digest"],
                        "owner_session_id": predecessor_value["owner_session_id"],
                        "source_head": predecessor_value["source_head"]},
        "successor": {"run_id": run_id, "runtime_plan_digest": plan_digest,
                      "node_allocation_id": allocation_id,
                      "node_allocation_digest": _allocation_digest(node_allocation),
                      "source_head": candidate_sha},
        "effect_envelope_ref": str(effect_envelope_path),
        "effect_envelope": envelope,
        "receipt_digest": receipt_digest, "authority_granted": False,
        "effect_authority_granted": False,
    }
    transition = {**transition_body, "transition_digest": _seal(transition_body)}
    transition_raw = (json.dumps(transition, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if transition_path.exists():
        _fail(transition_path.read_bytes() == transition_raw, "GENESIS_CONTENT_MISMATCH")
    else:
        transition_path.write_bytes(transition_raw)
    envelope_raw = (json.dumps(envelope, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if effect_envelope_path.exists():
        _fail(effect_envelope_path.read_bytes() == envelope_raw, "GENESIS_CONTENT_MISMATCH")
    else:
        effect_envelope_path.write_bytes(envelope_raw)
    write_checkpoint(
        db_path, task_id="SCRUM-781", run_id=run_id, node_id=node_id,
        idempotency_key=f"native-g1-genesis:{run_id}",
        payload={"run_state": state, "transition_receipt": transition},
        state_digest=state["content_digest"]["value"], record_digest=receipt_digest,
        occurred_at=created_at, expected_revision=0,
    )
    readback = read_back_genesis(db_path)
    _fail(readback == {"run_id": run_id, "state_digest": state["content_digest"]["value"]}, "GENESIS_READBACK_MISMATCH")
    return {"run_id": run_id, "state_digest": state["content_digest"]["value"],
            "transition_receipt_digest": transition["transition_digest"], "db_ref": str(db_path),
            "transition_receipt_ref": str(transition_path), "readback": readback}


def read_back_genesis(db_ref: str | Path) -> dict[str, str]:
    """Read persisted genesis through a newly opened SQLite connection."""
    from tools.node_architect.checkpoint_sqlite import read_checkpoint
    from tools.node_architect.universal_run_state import verify_run_state_record
    path = Path(db_ref)
    import sqlite3
    with sqlite3.connect(str(path)) as connection:
        row = connection.execute("SELECT task_id, run_id, node_id FROM checkpoint_events ORDER BY revision DESC LIMIT 1").fetchone()
    _fail(row is not None, "GENESIS_READBACK_MISSING")
    stored = read_checkpoint(path, task_id=row[0], run_id=row[1], node_id=row[2])
    _fail(stored is not None, "GENESIS_READBACK_MISSING")
    payload = stored["payload"]
    state = payload.get("run_state")
    transition = payload.get("transition_receipt")
    _fail(isinstance(state, Mapping) and verify_run_state_record(state), "GENESIS_RUN_STATE_INVALID")
    digest = state["content_digest"]["value"]
    _fail(isinstance(transition, Mapping), "GENESIS_TRANSITION_RECEIPT_INVALID")
    _fail(transition.get("transition_digest") == _seal({k: v for k, v in transition.items() if k != "transition_digest"}), "GENESIS_TRANSITION_RECEIPT_INVALID")
    successor = transition.get("successor", {})
    _fail(successor.get("run_id") == state["run_id"] and
          successor.get("runtime_plan_digest", "").removeprefix("sha256:") == state["run_manifest_digest"], "GENESIS_TRANSITION_RECEIPT_INVALID")
    _fail(isinstance(transition.get("predecessor", {}).get("identity"), str) and
          transition["predecessor"]["identity"] != successor.get("run_id"), "GENESIS_TRANSITION_RECEIPT_INVALID")
    _fail(transition.get("effect_authority_granted") is False and
          transition.get("effect_envelope", {}).get("executed") is False, "GENESIS_TRANSITION_RECEIPT_INVALID")
    _fail(stored.get("state_digest") == digest and stored.get("record_digest") in state.get("provenance", {}).get("source_refs", []), "GENESIS_READBACK_MISMATCH")
    return {"run_id": state["run_id"], "state_digest": digest}


__all__ = ["Q0NativeG1AdmissionError", "build_native_g1_plan_receipt",
           "materialize_native_g1_genesis", "read_back_genesis", "validate_native_g1_plan_receipt",
           "build_live_activation_effect_envelope"]
