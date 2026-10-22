from __future__ import annotations

from pathlib import Path

import pytest

from tools.node_architect.checkpoint_store import load_store
from tools.node_architect.universal_run_node import RecursiveRunDag, NodeArchitectureError
from tools.node_architect.universal_run_topology import create_node_allocation, create_run_manifest_revision

TS = "2026-10-22T00:00:00Z"
ACTOR = {"kind": "agent", "id": "c4-test"}
GATES = ["G0", "G1", "G2", "G3", "G4", "G5", "G6"]
SCOPE = "sha256:" + "a" * 64


def root():
    return create_run_manifest_revision(record_id="root", run_id="persistent-root", revision=1,
        run_kind="ROOT", created_at=TS, created_by=ACTOR, source_refs=["fixture"])


def spec():
    return {"child_run_id": "persistent-child", "node_allocation": create_node_allocation(
        record_id="allocation", run_id="persistent-root", node_allocation_id="work-node",
        kind="WORK", requirement="REQUIRED", created_at=TS, created_by=ACTOR)}


def host_for(calls):
    def host(**kw):
        calls.append((kw["run_id"], kw["gate"]))
        return {"status": "COMPLETED", "evidence": {"digest": f"ev:{kw['run_id']}:{kw['gate']}"},
            "target_readback": {"status": "VERIFIED", "digest": f"rb:{kw['run_id']}:{kw['gate']}"},
            "g6_receipt": {"status": "ACCEPTED", "receipt_id": f"g6:{kw['run_id']}"} if kw["gate"] == "G6" else None}
    return host


def kwargs(path: Path, **overrides):
    return {"root_manifest": root(), "child_node_allocations": [spec()], "authority": {},
        "canonical_state": {}, "store_path": path, "task_id": "COMMAND-191",
        "repository": "org/repo", "branch": "feature/c4", "base_sha": "b" * 40,
        "head_sha": "c" * 40, "scope_hash": SCOPE, "lease_owner": "worker-a",
        "lease_id": "lease-a", "fencing_token": 7, "lease_expires_at": "2099-01-01T00:00:00Z",
        **overrides}


def test_file_backed_run_reloads_and_replays_receipts_without_rerunning_prefix(tmp_path):
    path = tmp_path / "checkpoint.json"
    calls = []
    first = RecursiveRunDag(runtime_event=host_for(calls)).execute_persistent(**kwargs(path))
    assert first["status"] == "COMPLETED"
    assert [gate for run, gate in calls if run == "persistent-child"] == GATES
    store = load_store(path)
    assert store["revision"] >= 1
    assert store["store_digest"].startswith("sha256:")
    audit = [event for event in store["events"] if event.get("event_type") == "recursive_run.audit"]
    assert {gate for event in audit for gate in event["gate_receipt_digests"]} == set(GATES)
    assert {gate for event in audit for gate in event["gate_readback_digests"]} == set(GATES)
    assert all(event.get("fencing_token") == 7 and event.get("checkpoint_revision") for event in audit)

    restarted_calls = []
    replay = RecursiveRunDag(runtime_event=host_for(restarted_calls)).execute_persistent(**kwargs(path))
    assert replay["status"] == "COMPLETED"
    assert restarted_calls == []
    assert replay["children"][0]["g6_receipt"]["status"] == "ACCEPTED"
    assert all(not any(secret in str(event) for secret in ("password", "token-value", "credential"))
               for event in store["events"])


def test_file_backed_run_rejects_changed_binding_and_fencing_before_effects(tmp_path):
    path = tmp_path / "checkpoint.json"
    calls = []
    dag = RecursiveRunDag(runtime_event=host_for(calls))
    dag.execute_persistent(**kwargs(path))
    calls.clear()
    with pytest.raises(NodeArchitectureError):
        RecursiveRunDag(runtime_event=host_for(calls)).execute_persistent(**kwargs(path, head_sha="d" * 40))
    assert calls == []
    with pytest.raises(NodeArchitectureError):
        RecursiveRunDag(runtime_event=host_for(calls)).execute_persistent(**kwargs(path, fencing_token=8))
    assert calls == []
    with pytest.raises(NodeArchitectureError, match="DAG_PERSISTENCE_INPUT_MISMATCH"):
        RecursiveRunDag(runtime_event=host_for(calls)).execute_persistent(
            **kwargs(path, child_node_allocations=[]))
    assert calls == []


def test_tampered_state_and_store_digest_fail_closed_before_effects(tmp_path):
    path = tmp_path / "checkpoint.json"
    RecursiveRunDag(runtime_event=host_for([])).execute_persistent(**kwargs(path))
    store = load_store(path)
    latest = max(store["checkpoints"].values(), key=lambda record: record["revision"])
    latest["state"]["gates"] = {"forged": {"G6": {"g6_receipt": {"status": "ACCEPTED"}}}}
    path.write_text(__import__("json").dumps(store), encoding="utf-8")
    calls = []
    with pytest.raises(NodeArchitectureError, match="DAG_PERSISTENCE_STORE_TAMPERED"):
        RecursiveRunDag(runtime_event=host_for(calls)).execute_persistent(**kwargs(path))
    assert calls == []


def test_process_restart_resumes_from_sealed_child_gate_cursor(tmp_path):
    path = tmp_path / "checkpoint.json"
    calls = []
    interrupted = False

    def host(**kw):
        nonlocal interrupted
        calls.append((kw["run_id"], kw["gate"]))
        if kw["run_id"] == "persistent-child" and kw["gate"] == "G3" and not interrupted:
            interrupted = True
            raise RuntimeError("simulated process interruption")
        return host_for([])(**kw)

    with pytest.raises(RuntimeError, match="interruption"):
        RecursiveRunDag(runtime_event=host).execute_persistent(**kwargs(path))
    assert [gate for run, gate in calls if run == "persistent-child"] == GATES[:4]

    resumed_calls = []
    result = RecursiveRunDag(runtime_event=host_for(resumed_calls)).execute_persistent(**kwargs(path))
    assert result["status"] == "COMPLETED"
    assert [gate for run, gate in resumed_calls if run == "persistent-child"] == GATES[3:]
    assert [gate for run, gate in resumed_calls if run == "persistent-root"] == GATES[3:]


def test_waiting_lease_interrupt_keeps_generation_resumable_and_sibling_runs(tmp_path):
    path = tmp_path / "checkpoint.json"
    child_calls = []
    held = True

    def host(**kw):
        nonlocal held
        child_calls.append((kw["run_id"], kw["gate"]))
        if kw["run_id"] == "persistent-child" and kw["gate"] == "G2" and held:
            return {"status": "WAITING", "reason_code": "LEASE_REVOKED"}
        return host_for([])(**kw)

    specs = [spec(), {"child_run_id": "sibling", "node_allocation": create_node_allocation(
        record_id="allocation-sibling", run_id="persistent-root", node_allocation_id="sibling-node",
        kind="WORK", requirement="REQUIRED", created_at=TS, created_by=ACTOR)}]
    first = RecursiveRunDag(runtime_event=host).execute_persistent(
        **kwargs(path, child_node_allocations=specs))
    assert first["status"] == "WAITING"
    assert any(run == "sibling" for run, _ in child_calls)
    saved = load_store(path)
    latest = max(saved["checkpoints"].values(), key=lambda record: record["revision"])
    assert latest["state"]["generations"]["persistent-root:work-node"][0]["terminal_state"] == "OPEN"

    held = False
    resumed_calls = []
    second = RecursiveRunDag(runtime_event=host_for(resumed_calls)).execute_persistent(
        **kwargs(path, child_node_allocations=specs))
    assert second["status"] == "COMPLETED"
    assert [gate for run, gate in resumed_calls if run == "persistent-child"] == GATES[2:]
    assert [gate for run, gate in resumed_calls if run == "sibling"] == []


def test_unknown_checkpoint_write_outcome_fails_closed_without_retry(tmp_path, monkeypatch):
    from tools.node_architect import checkpoint_store

    path = tmp_path / "checkpoint.json"
    calls = []

    def unknown_write(*args, **kwargs):
        raise OSError("simulated ambiguous write result")

    monkeypatch.setattr(checkpoint_store, "persist_to_file", unknown_write)
    with pytest.raises(NodeArchitectureError, match="DAG_PERSISTENCE_OUTCOME_UNKNOWN"):
        RecursiveRunDag(runtime_event=host_for(calls)).execute_persistent(**kwargs(path))
    assert calls == [("persistent-root", "G0")]

