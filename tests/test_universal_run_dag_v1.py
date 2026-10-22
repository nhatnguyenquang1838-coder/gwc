from __future__ import annotations

import hashlib

import pytest

from tools.node_architect.universal_run_node import RecursiveRunDag, NodeArchitectureError, _canonical_json_bytes
from tools.node_architect.universal_run_topology import (
    create_node_allocation,
    create_run_manifest_revision,
)

TS = "2026-10-22T00:00:00Z"
ACTOR = {"kind": "agent", "id": "c1-test"}
GATES = ["G0", "G1", "G2", "G3", "G4", "G5", "G6"]


def contract_for(run_id, child_ids, allocation_ids, *, parent_contract=None,
                 parent_run_id=None, parent_contract_digest=None,
                 invoking_allocation_ref=None, node_allocation_id=None,
                 node_allocation_record_id=None, target_id="generic-target",
                 strict=True):
    """Build an exact, self-digested TargetContract for a run."""
    body = {
        "schema_version": "1.0",
        "run_id": run_id,
        "target_id": target_id,
        "required_children": list(child_ids),
        "required_child_allocations": list(allocation_ids),
    }
    if strict and len(body["required_children"]) != len(set(body["required_children"])):
        raise ValueError("required_children must be unique in strict mode")
    if parent_contract is not None:
        body["parent_run_id"] = parent_run_id
        body["parent_contract_digest"] = parent_contract["contract_digest"]
        body["invoking_node_allocation_ref"] = invoking_allocation_ref
        body["node_allocation_id"] = node_allocation_id
        body["node_allocation_record_id"] = node_allocation_record_id
    body["contract_digest"] = "sha256:" + hashlib.sha256(
        _canonical_json_bytes(body)).hexdigest()
    return body


def route_context(contract):
    return {"route_context": {"context": {"target_contract": contract}}}


def root_contract(child_specs):
    return contract_for("generic-root-191",
                        [s["child_run_id"] for s in child_specs],
                        [s["node_allocation"]["node_allocation_id"] for s in child_specs],
                        strict=False)


def child_contract_for(spec, parent_contract):
    children = spec.get("children", [])
    alloc = spec["node_allocation"]
    return contract_for(
        spec["child_run_id"],
        [c["child_run_id"] for c in children],
        [c["node_allocation"]["node_allocation_id"] for c in children],
        parent_contract=parent_contract,
        parent_run_id="generic-root-191",
        parent_contract_digest=parent_contract["contract_digest"],
        invoking_allocation_ref=alloc["record_id"],
        node_allocation_id=alloc["node_allocation_id"],
        node_allocation_record_id=alloc["record_id"])


def with_contracts(specs, **extra):
    """Attach the validated root TargetContract; children are derived by the DAG."""
    return dict(root_manifest=root(), child_node_allocations=list(specs),
                **route_context(root_contract(specs)), **extra)


def root():
    return create_run_manifest_revision(
        record_id="rm-root", run_id="generic-root-191", revision=1,
        run_kind="ROOT", created_at=TS, created_by=ACTOR,
        source_refs=["generic-consumer:fixture"],
    )


def allocation(run_id, allocation_id):
    return create_node_allocation(
        record_id=f"na-{allocation_id}", run_id=run_id,
        node_allocation_id=allocation_id, kind="WORK", requirement="REQUIRED",
        created_at=TS, created_by=ACTOR,
    )


def spec(run_id, child_id, allocation_id, **extra):
    return {
        "child_run_id": child_id,
        "node_allocation": allocation(run_id, allocation_id),
        **extra,
    }


def event_result(run_id, gate):
    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "gate": gate,
        "evidence": {"artifact_type": "gate-evidence", "digest": f"evidence:{run_id}:{gate}"},
        "target_readback": {"status": "VERIFIED", "digest": f"readback:{run_id}:{gate}"},
        "g6_receipt": ({"status": "ACCEPTED", "receipt_id": f"g6:{run_id}"} if gate == "G6" else None),
    }


def test_generic_root_manifest_has_distinct_identity_and_q0_consumer_edge():
    from pathlib import Path
    from tools.node_architect.universal_run_kernel import verify_record_digest
    path = Path(__file__).resolve().parents[1] / "core/node-architect/universal-v2-recursive-authority-root-r1.json"
    manifest = __import__("json").loads(path.read_text(encoding="utf-8"))
    assert verify_record_digest(manifest)
    assert manifest["run_kind"] == "ROOT"
    assert manifest["run_id"] == "universal-v2-recursive-authority-r1"
    assert manifest["parent_run_ref"] is None
    assert manifest["invoking_node_allocation_ref"] is None
    assert "run:scrum781-q0-fresh-20261010-r1" in manifest["provenance"]["source_refs"]


def test_recursive_children_run_all_gates_through_host_and_parent_waits_for_receipts():
    calls = []

    def host(**kwargs):
        calls.append(kwargs)
        return event_result(kwargs["run_id"], kwargs["gate"])

    dag = RecursiveRunDag(runtime_event=host, max_depth=4, max_nodes=8)
    result = dag.execute(**with_contracts([
        spec("generic-root-191", "child-a", "node-a", children=[
            spec("child-a", "grandchild-a", "node-grandchild")
        ])
    ], authority={"authority_ref": "existing-authority"}, canonical_state={"fixture": True}))

    assert [c["gate"] for c in calls if c["run_id"] == "generic-root-191"] == GATES
    assert [c["gate"] for c in calls if c["run_id"] == "child-a"] == GATES
    assert [c["gate"] for c in calls if c["run_id"] == "grandchild-a"] == GATES
    assert calls.index(next(c for c in calls if c["run_id"] == "generic-root-191" and c["gate"] == "G6")) > calls.index(next(c for c in calls if c["run_id"] == "child-a" and c["gate"] == "G6"))
    assert all(c["requested_action"] == "RUN" for c in calls)
    assert result["status"] == "COMPLETED"
    assert result["children"][0]["g6_receipt"]["status"] == "ACCEPTED"
    assert result["children"][0]["children"][0]["g6_receipt"]["status"] == "ACCEPTED"
    assert result["parent_aggregation"]["g4"] == "INTEGRATED"
    assert result["parent_aggregation"]["g5"] == "VERIFIED"


def test_failed_child_receipt_fails_parent_aggregation_but_sibling_runs():
    calls = []

    def host(**kwargs):
        calls.append(kwargs)
        response = event_result(kwargs["run_id"], kwargs["gate"])
        if kwargs["run_id"] == "child-b" and kwargs["gate"] == "G6":
            response["g6_receipt"] = {"status": "REJECTED", "receipt_id": "g6:child-b"}
        return response

    result = RecursiveRunDag(runtime_event=host).execute(**with_contracts([
        spec("generic-root-191", "child-b", "node-b"),
        spec("generic-root-191", "child-c", "node-c"),
    ], authority={"authority_ref": "existing-authority"}, canonical_state={}))
    assert "child-c" in {call["run_id"] for call in calls}
    # A rejected required child blocks parent composition before G3/G4/G5/G6.
    assert not any(call["run_id"] == "generic-root-191" and call["gate"] in GATES[3:]
                   for call in calls)
    assert result["status"] == "FAILED"
    assert result["parent_aggregation"]["g3"] == "FAILED"
    assert result["parent_aggregation"]["g4"] == "FAILED"
    assert result["parent_aggregation"]["g5"] == "FAILED"


def test_generic_gates_never_default_to_protected_domain_effects():
    dag = RecursiveRunDag()
    assert dag._host_gate("G4") == "G4_INTEGRATE"
    assert dag._host_gate("G5") == "G5_VALIDATE_TARGET"
    assert dag._host_gate("G6") == "G6_ACCEPT_HANDOFF"
    assert "G4_MERGE" not in {dag._host_gate(g) for g in ("G4", "G5", "G6")}
    assert "G5_DEPLOY" not in {dag._host_gate(g) for g in ("G4", "G5", "G6")}
    assert "G6_PRODUCTION_DATA" not in {dag._host_gate(g) for g in ("G4", "G5", "G6")}


def test_child_cannot_inject_authority_or_cross_run_canonical_state():
    calls = []
    def host(**kwargs):
        calls.append(kwargs)
        return event_result(kwargs["run_id"], kwargs["gate"])
    dag = RecursiveRunDag(runtime_event=host)
    for override, code in [
        ({"authority": {"authority_ref": "forged"}}, "CHILD_AUTHORITY_OVERRIDE_FORBIDDEN"),
        ({"canonical_state": {"run_id": "other-run"}}, "CHILD_CANONICAL_STATE_OVERRIDE_FORBIDDEN"),
    ]:
        calls.clear()
        with pytest.raises(NodeArchitectureError, match=code):
            dag.execute(**with_contracts([
                spec("generic-root-191", "child-inject", "node-inject", **override)
            ], authority={"authority_ref": "parent"}, canonical_state={"run_id": "generic-root-191"}))
        assert not any(call["run_id"] == "child-inject" for call in calls)
        assert not any(call["run_id"] == "generic-root-191" and call["gate"] in GATES[3:]
                       for call in calls)


def test_waiting_child_is_recoverable_and_siblings_continue():
    calls = []
    released = False
    def host(**kwargs):
        nonlocal released
        calls.append((kwargs["run_id"], kwargs["gate"]))
        if kwargs["run_id"] == "child-wait" and kwargs["gate"] == "G2" and not released:
            return {"status": "WAITING", "reason_code": "EFFECT_HOLD"}
        return event_result(kwargs["run_id"], kwargs["gate"])
    dag = RecursiveRunDag(runtime_event=host)
    checkpoint = {}
    kwargs = dict(authority={}, canonical_state={}, checkpoint=checkpoint)
    first = dag.execute(**with_contracts([
        spec("generic-root-191", "child-wait", "node-wait"),
        spec("generic-root-191", "child-sibling", "node-sibling"),
    ], **kwargs))
    assert first["status"] == "WAITING"
    assert any(run_id == "child-sibling" for run_id, _ in calls)
    assert not any(run_id == "generic-root-191" and gate in GATES[3:] for run_id, gate in calls)
    assert checkpoint["generations"]["generic-root-191:node-wait"][0]["terminal_state"] == "OPEN"
    released = True
    second = dag.execute(**with_contracts([
        spec("generic-root-191", "child-wait", "node-wait"),
        spec("generic-root-191", "child-sibling", "node-sibling"),
    ], **kwargs))
    assert second["status"] == "COMPLETED"
    assert checkpoint["generations"]["generic-root-191:node-wait"][0]["terminal_state"] == "ACCEPTED"


def test_dag_rejects_cycles_duplicate_ids_self_parent_and_depth_budget():
    host = lambda **kw: event_result(kw["run_id"], kw["gate"])
    dag = RecursiveRunDag(runtime_event=host, max_depth=2)
    with pytest.raises(NodeArchitectureError, match="DAG_CYCLE"):
        dag.execute(**with_contracts([
            spec("generic-root-191", "child-x", "node-x", children=[
                spec("child-x", "generic-root-191", "node-back")
            ])
        ], authority={}, canonical_state={}))
    with pytest.raises(NodeArchitectureError, match="CHILD_RUN_ID_DUPLICATE"):
        dag.execute(**with_contracts([
            spec("generic-root-191", "child-x", "node-x"),
            spec("generic-root-191", "child-x", "node-y"),
        ], authority={}, canonical_state={}))
    with pytest.raises(NodeArchitectureError, match="CHILD_PARENT_SELF_LOOP"):
        dag.execute(**with_contracts([
            spec("generic-root-191", "generic-root-191", "node-self")
        ], authority={}, canonical_state={}))
    with pytest.raises(NodeArchitectureError, match="DAG_MAX_DEPTH_EXCEEDED"):
        dag.execute(**with_contracts([
            spec("generic-root-191", "child-x", "node-x", children=[
                spec("child-x", "grandchild-x", "node-g")
            ])
        ], authority={}, canonical_state={}))


def test_typed_noop_is_explicit_and_checkpoint_replay_is_idempotent():
    calls = []

    def host(**kwargs):
        calls.append((kwargs["run_id"], kwargs["gate"]))
        return event_result(kwargs["run_id"], kwargs["gate"])

    checkpoint = {}
    dag = RecursiveRunDag(runtime_event=host)
    kwargs = dict(authority={}, canonical_state={}, checkpoint=checkpoint,
                  lease_owner="worker-a")
    first = dag.execute(**with_contracts([
        spec("generic-root-191", "child-resume", "node-resume", outcomes={
            "G2": {"kind": "NO_TRANSFER_REQUIRED", "reason": "read-only atomic run"}
        })
    ], **kwargs))
    call_count = len(calls)
    replay = dag.execute(**with_contracts([
        spec("generic-root-191", "child-resume", "node-resume", outcomes={
            "G2": {"kind": "NO_TRANSFER_REQUIRED", "reason": "read-only atomic run"}
        })
    ], **kwargs))
    assert len(calls) == call_count
    assert first == replay
    assert first["children"][0]["gate_outcomes"]["G2"]["kind"] == "NO_TRANSFER_REQUIRED"
    assert first["children"][0]["g6_receipt"]["status"] == "ACCEPTED"
    checkpoint["leases"] = {"generic-root-191": "worker-a"}
    with pytest.raises(NodeArchitectureError, match="DAG_LEASE_HELD"):
        dag.execute(**with_contracts([
            spec("generic-root-191", "child-resume", "node-resume", outcomes={
                "G2": {"kind": "NO_TRANSFER_REQUIRED", "reason": "read-only atomic run"}
            })
        ], **{**kwargs, "lease_owner": "worker-b"}))


def test_interrupted_child_resumes_from_last_gate_without_replaying_prefix():
    calls = []
    interrupted = False

    def host(**kwargs):
        nonlocal interrupted
        calls.append((kwargs["run_id"], kwargs["gate"]))
        if kwargs["run_id"] == "child-restart" and kwargs["gate"] == "G4" and not interrupted:
            interrupted = True
            raise RuntimeError("simulated process interruption")
        return event_result(kwargs["run_id"], kwargs["gate"])

    checkpoint = {}
    dag = RecursiveRunDag(runtime_event=host)
    kwargs = dict(authority={}, canonical_state={}, checkpoint=checkpoint)
    with pytest.raises(RuntimeError, match="interruption"):
        dag.execute(**with_contracts([
            spec("generic-root-191", "child-restart", "node-restart")
        ], **kwargs))
    child_prefix_calls = [gate for run_id, gate in calls if run_id == "child-restart"]
    assert child_prefix_calls == GATES[:5]

    result = dag.execute(**with_contracts([
        spec("generic-root-191", "child-restart", "node-restart")
    ], **kwargs))
    resumed_child_calls = [gate for run_id, gate in calls if run_id == "child-restart"]
    assert resumed_child_calls == GATES[:5] + GATES[4:]
    assert result["status"] == "COMPLETED"
    assert len(checkpoint["generations"]["generic-root-191:node-restart"]) == 1


def test_every_child_receipt_requires_gate_evidence_readback_and_g6_acceptance():
    def incomplete(**kwargs):
        response = event_result(kwargs["run_id"], kwargs["gate"])
        if kwargs["run_id"] == "child-bad" and kwargs["gate"] == "G3":
            response.pop("evidence")
        return response

    result = RecursiveRunDag(runtime_event=incomplete).execute(**with_contracts([
        spec("generic-root-191", "child-bad", "node-bad")
    ], authority={}, canonical_state={}))
    assert result["status"] == "FAILED"
    assert result["children"][0]["failure_code"] == "CHILD_GATE_EVIDENCE_MISSING"
    assert "LOAD_PROOF" not in repr(result)
    assert "PASS" not in repr(result)
