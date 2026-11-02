from tools.node_architect.q0_qualification import (
    Q0QualificationError,
    recover_child_before_parent_g1,
)


def test_child_before_parent_g1_replans_materializes_and_accepts_exact_readback():
    calls = []
    parent = {"run_id": "parent-1", "exists": True, "goal_contract": None, "runtime_plan": None}
    children = [{"run_id": "child-1", "result_ref": "results/child-1.json"}]

    def plan(**kwargs):
        calls.append(("plan", kwargs["idempotency_key"]))
        return {"run_id": "parent-1", "revision": 2, "goal_contract": {"goal": "deliver"},
                "runtime_plan": {"digest": "sha256:" + "a" * 64,
                                 "dag": {"nodes": [{"id": "child-1", "predecessors": []}]}},
                "validator_evidence": {"status": "PASS", "ref": "evidence/g1.json"},
                "parent_bindings": {"run_id": "parent-1"},
                "child_bindings": [{"run_id": "child-1"}], "dependency_dag": {"nodes": [{"id": "child-1", "predecessors": []}]}}

    def materialize(**kwargs):
        calls.append(("materialize", kwargs["revision"]))
        return {"durable": True, "stored_digest": "sha256:" + "d" * 64, **kwargs["plan"]}

    def readback(**kwargs):
        return kwargs["expected"]

    def reconcile(**kwargs):
        return {"status": "PASS", "children": kwargs["children"]}

    result = recover_child_before_parent_g1(
        parent=parent, children=children, canonical_planner=plan,
        materializer=materialize, readback=readback,
        reconcile_children=reconcile, m2_status="CHANGES_REQUIRED",
        g2_is_execution_predecessor=True,
    )
    assert result["disposition"] == "REPLAN_PARENT_G1"
    assert result["event"] == "Q0_PARENT_G1_BINDING_ACCEPTED"
    assert result["g1_status"] == "PASS" and result["m2_status"] == "CHANGES_REQUIRED"
    assert result["g2_status"] == "BLOCKED"
    assert result["readback_status"] == "PASS"
    assert calls[0][0] == "plan" and calls[1][0] == "materialize"


def test_engineering_m2_recovers_parent_gap_but_keeps_g2_blocked(tmp_path):
    from test_engineering_m1_m7_workflow import binding, capabilities
    from tools.node_architect.task_m1_m7_runner import run_task_workflow

    context = binding(tmp_path)
    context["engineering"]["parent_g1_recovery"] = {
        "parent": {"run_id": "parent-1", "exists": True, "goal_contract": None, "runtime_plan": None},
        "children": [{"run_id": "child-1"}], "m2_status": "CHANGES_REQUIRED",
        "g2_is_execution_predecessor": True,
    }
    plan = {"run_id": "parent-1", "revision": 2, "goal_contract": {"goal": "deliver"},
            "runtime_plan": {"digest": "sha256:" + "a" * 64,
                             "dag": {"nodes": [{"id": "child-1", "predecessors": []}]}},
            "validator_evidence": {"status": "PASS", "ref": "evidence/g1.json"},
            "parent_bindings": {"run_id": "parent-1"},
            "child_bindings": [{"run_id": "child-1"}],
            "dependency_dag": {"nodes": [{"id": "child-1", "predecessors": []}]}}
    caps = capabilities(context, {"read": 0, "execute": 0})
    caps.update({"q0.parent_g1.canonical_planner": lambda **_: plan,
                 "q0.parent_g1.materializer": lambda **kwargs: {
                     "durable": True, "stored_digest": "sha256:" + "d" * 64},
                 "q0.parent_g1.readback": lambda **kwargs: kwargs["expected"],
                 "q0.parent_g1.reconcile_children": lambda **kwargs: {"status": "PASS", "children": kwargs["children"]}})
    result = run_task_workflow(context, host_capabilities=caps, invocation_key="parent-gap")
    recovery = result["activity_results"]["M2"]["parent_g1_recovery"]
    assert recovery["event"] == "Q0_PARENT_G1_BINDING_ACCEPTED"
    assert recovery["g1_status"] == "PASS" and recovery["g2_status"] == "BLOCKED"
    assert result["verdict"]["reason_code"] == "M2_EXACT_HEAD_ACCEPTANCE_REQUIRED"


def test_parent_g1_recovery_rejects_noncanonical_readback_without_acceptance():
    parent = {"run_id": "parent-1", "exists": True, "goal_contract": None, "runtime_plan": None}
    plan = {"run_id": "parent-1", "revision": 2, "goal_contract": {"goal": "deliver"},
            "runtime_plan": {"digest": "sha256:" + "a" * 64,
                             "dag": {"nodes": [{"id": "child-1", "predecessors": []}]}},
            "validator_evidence": {"status": "PASS", "ref": "evidence/g1.json"},
            "parent_bindings": {"run_id": "parent-1"},
            "child_bindings": [{"run_id": "child-1"}],
            "dependency_dag": {"nodes": [{"id": "child-1", "predecessors": []}]}}
    try:
        recover_child_before_parent_g1(
            parent=parent, children=[{"run_id": "child-1"}],
            canonical_planner=lambda **_: plan,
            materializer=lambda **kwargs: {"durable": True, "stored_digest": "sha256:" + "d" * 64, **kwargs["plan"]},
            readback=lambda **kwargs: {**kwargs["expected"], "runtime_plan": {"digest": "wrong"}},
            reconcile_children=lambda **_: {"status": "PASS"},
            m2_status="PASS", g2_is_execution_predecessor=True,
        )
    except Q0QualificationError as exc:
        assert exc.code == "PARENT_G1_READBACK_MISMATCH"
    else:
        raise AssertionError("noncanonical parent plan readback must be rejected")
