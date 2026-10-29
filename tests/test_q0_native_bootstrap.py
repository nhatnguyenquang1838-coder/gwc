"""Synthetic bootstrap regressions, never campaign acceptance evidence."""
import copy
import json
from pathlib import Path

import pytest


def _inputs():
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json").read_text())
    plan["run_id"] = "scrum781-q0-unit-bootstrap"
    plan["branch"] = "fix/SCRUM-781-q0-unit-bootstrap"
    return dict(execution_plan=plan, execution_plan_ref="unit:verified-execution-plan",
                candidate_sha="b" * 40, base_sha="a" * 40,
                dag={"nodes": [{"id": f"W{i}", "predecessors": [] if i == 1 else [f"W{i-1}"]} for i in range(1, 7)]},
                created_at="2026-10-25T00:00:00Z", created_by={"profile": "unit-test"})


def test_bootstrap_starts_at_unpassed_g0_without_copying_projected_g2():
    from tools.node_architect.q0_native_bootstrap import build_native_q0_bootstrap
    from tools.node_architect.universal_run_controller import UniversalController
    binding = build_native_q0_bootstrap(**_inputs())
    state = binding["run_state"]
    assert state["sequence"] == 1 and state["active_gate"] == "UR.G0"
    assert state["consumed_receipts"] == [] and state["gate_evidence"] == {}
    assert state["terminal_state"] == "OPEN"
    assert state["bootstrap_provenance"]["execution_plan_projected_gate"] == "UR.G2"
    controller = UniversalController.from_manifest(profile=binding["profile"], manifest=binding)
    assert controller.assign_current_action()["gate"] == "UR.G0"
    assert state["authority_granted"] is False and state["executed_effects"] == []


@pytest.mark.parametrize("field,value", [("run_id", "foreign-run"), ("runtime_epoch", "LEGACY"), ("contract_mode", "PLAN")])
def test_bootstrap_rejects_wrong_lane_contract(field, value):
    from tools.node_architect.q0_native_bootstrap import build_native_q0_bootstrap
    args = _inputs()
    args["execution_plan"][field] = value
    with pytest.raises(ValueError):
        build_native_q0_bootstrap(**args)


def test_bootstrap_materialization_is_immutable_and_source_bound(tmp_path):
    from tools.node_architect.q0_native_bootstrap import build_native_q0_bootstrap, materialize_native_q0_bootstrap
    binding = build_native_q0_bootstrap(**_inputs())
    path = tmp_path / "native-genesis.json"
    first = materialize_native_q0_bootstrap(binding=binding, path=path)
    original = path.read_bytes()
    assert json.loads(original)["run_state"] == binding["run_state"]
    assert materialize_native_q0_bootstrap(binding=binding, path=path)["idempotent_replay"] is True
    other = copy.deepcopy(binding)
    other["run_state"]["sequence"] = 2
    with pytest.raises(ValueError):
        materialize_native_q0_bootstrap(binding=other, path=path)
    assert path.read_bytes() == original
    assert first["idempotent_replay"] is False


def test_real_g0_g1_continuation_assigns_g2_to_executor(tmp_path):
    from tools.node_architect.q0_native_bootstrap import build_native_q0_bootstrap
    from tools.node_architect.q0_native_g1_admission import build_native_g1_plan_receipt
    from tools.node_architect.universal_run_controller import UniversalController
    from tools.node_architect.universal_run_execution import UniversalExecutor

    class UnitProvider:
        name = "unit-understanding"

        def run(self, request):
            return {"outcome": "PASS", "source": "synthetic unit understanding"}

    binding = build_native_q0_bootstrap(**_inputs())
    controller = UniversalController.from_manifest(profile=binding["profile"], manifest=binding)
    assignment = controller.assign_current_action()
    receipt = UniversalExecutor().execute(assignment=assignment, provider=UnitProvider(), event={}, evidence_root=tmp_path)
    g0 = controller.consume_executor_receipt(receipt, evidence_artifacts={"UNDERSTANDING_RECEIPT": {"ref": "unit:understood"}})
    assert g0["next_gate"] == "UR.G1"
    controller.assign_current_action()
    plan = binding["runtime_plan"]
    g1_receipt = build_native_g1_plan_receipt(
        run_id=plan["run_id"], runtime_plan_digest=plan["digest"], candidate_sha="b" * 40,
        source_head="b" * 40, runtime_plan=plan, node_allocation=binding["node_allocation"],
        provenance_ref="unit:plan", decision_ref="unit:decomposed",
    )
    g1 = controller.complete_controller_owned_gate(evidence={"PLAN_RECEIPT": g1_receipt})
    assert g1["next_gate"] == "UR.G2"
    assert g1["next_owner"] == "EXECUTOR"
    assert controller.assign_current_action()["actor"] == "EXECUTOR"
