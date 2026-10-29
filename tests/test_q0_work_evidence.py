"""Derivative-contract engineering tests, never live self-fix/qualification proof."""
import copy
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    from tools.node_architect.q0_native_bootstrap import build_native_q0_bootstrap

    execution = json.loads((ROOT / "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json").read_text())
    execution["run_id"] = "scrum781-q0-unit-work-evidence"
    execution["branch"] = "fix/SCRUM-781-q0-unit-work-evidence"
    dag = {"nodes": [{"id": "NATIVE-PLAN-ACTIVATION", "predecessors": []}] + [
        {"id": f"W{i}", "predecessors": ["NATIVE-PLAN-ACTIVATION" if i == 1 else f"W{i-1}"]}
        for i in range(1, 7)
    ]}
    binding = build_native_q0_bootstrap(
        execution_plan=execution, execution_plan_ref="unit:execution-plan",
        candidate_sha="b" * 40, base_sha="a" * 40, dag=dag,
        created_at="2026-10-25T00:00:00Z", created_by={"profile": "unit"},
    )
    frontier = json.loads((ROOT / "core/node-architect/q0-native-successor-frontier-proposal-r1.json").read_text())
    return dict(native_binding=binding, execution_plan=execution, work_frontier=frontier,
                source_head="b" * 40, decision_ref="unit:noncircular-contract-decision")


def test_real_plan_producer_roundtrip_preserves_two_axes_and_inputs():
    from tools.node_architect.q0_work_evidence import build_cf_work_contract, validate_cf_work_contract

    args = _inputs()
    before = copy.deepcopy(args)
    contract = build_cf_work_contract(**args)
    result = validate_cf_work_contract(contract, **args)
    assert result["contract_valid"] is True
    assert result["qualification_accepted"] is False
    assert contract["qualification_prerequisites"] == ["NATIVE-PLAN-ACTIVATION", "W1", "W2", "W3", "W4"]
    assert contract["milestones"] == {"W5": "NOT_YET_DUE", "W6": "NOT_YET_DUE"}
    assert len(contract["leaves"]) == 6
    assert contract["qualification_results"] == {}
    assert set(contract["completion_axes"]) == {
        "engineering_prerequisites_complete", "qualification_ready",
        "certification_complete", "human_handoff_accepted",
    }
    assert all(value is None for value in contract["completion_axes"].values())
    assert contract["authority_granted"] is False
    assert args == before


def _reseal(contract):
    from tools.node_architect.q0_native_g1_admission import _seal
    contract["contract_digest"] = _seal({k: v for k, v in contract.items() if k != "contract_digest"})
    return contract


@pytest.mark.parametrize("mutation", ["missing_leaf", "duplicate_leaf", "edge", "objective", "milestone_cycle", "source_head", "allocation"])
def test_resealed_derivative_drift_is_rejected_against_external_inputs(mutation):
    from tools.node_architect.q0_work_evidence import build_cf_work_contract, validate_cf_work_contract, Q0WorkEvidenceError
    args = _inputs()
    contract = build_cf_work_contract(**args)
    if mutation == "missing_leaf":
        contract["leaves"].pop()
    elif mutation == "duplicate_leaf":
        contract["leaves"].append(copy.deepcopy(contract["leaves"][0]))
    elif mutation == "edge":
        contract["leaves"][2]["cf_predecessors"] = []
    elif mutation == "objective":
        contract["objectives"]["W4"] = "An injected test is enough"
    elif mutation == "milestone_cycle":
        contract["qualification_prerequisites"].extend(["W5", "W6"])
    elif mutation == "source_head":
        contract["source_bindings"]["analysis_source_head"] = "c" * 40
    else:
        contract["source_bindings"]["node_allocation_digest"] = "sha256:" + "c" * 64
    with pytest.raises(Q0WorkEvidenceError, match="CF_CONTRACT_BINDING_MISMATCH"):
        validate_cf_work_contract(_reseal(contract), **args)


def test_source_skipped_cf_predecessor_is_rejected_before_contract_generation():
    from tools.node_architect.q0_work_evidence import build_cf_work_contract, Q0WorkEvidenceError
    args = _inputs()
    args["execution_plan"]["recursive_plan"]["children"][1]["children"][1]["depends_on"] = []
    with pytest.raises(Q0WorkEvidenceError, match="CF_PREDECESSOR_INVALID"):
        build_cf_work_contract(**args)


def test_duplicate_source_work_objective_is_not_silently_overwritten():
    from tools.node_architect.q0_work_evidence import build_cf_work_contract, Q0WorkEvidenceError
    args = _inputs()
    args["work_frontier"]["items"].append(copy.deepcopy(args["work_frontier"]["items"][1]))
    with pytest.raises(Q0WorkEvidenceError, match="WORK_OBJECTIVES_INVALID"):
        build_cf_work_contract(**args)


def test_analysis_head_refresh_does_not_rebind_historical_native_candidate():
    from tools.node_architect.q0_work_evidence import build_cf_work_contract, validate_cf_work_contract, Q0WorkEvidenceError
    args = _inputs()
    old = build_cf_work_contract(**args)
    args["source_head"] = "c" * 40
    with pytest.raises(Q0WorkEvidenceError, match="CF_CONTRACT_BINDING_MISMATCH"):
        validate_cf_work_contract(old, **args)
    current = build_cf_work_contract(**args)
    assert current["source_bindings"]["analysis_source_head"] == "c" * 40
    assert current["source_bindings"]["native_candidate_sha"] == "b" * 40
    assert validate_cf_work_contract(current, **args)["qualification_accepted"] is False
