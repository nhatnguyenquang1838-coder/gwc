from __future__ import annotations


def test_universal_v2_kernel_uses_explicit_ur_gate_namespace():
    from tools.node_architect import universal_run_kernel

    assert universal_run_kernel.GATES == tuple(f"UR.G{index}" for index in range(7))
    assert universal_run_kernel.UNIVERSAL_PROFILE == {
        "id": "gwc.universal-run.v2",
        "version": 2,
    }


def test_universal_lifecycle_schemas_use_ur_gates_and_v2_profile():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    expected_gates = [f"UR.G{index}" for index in range(7)]
    schemas = root / "schemas/node-architect/universal-run"
    transition = json.loads((schemas / "lifecycle-transition.schema.json").read_text())
    state = json.loads((schemas / "run-state-record.schema.json").read_text())

    assert transition["properties"]["current_gate"]["enum"] == expected_gates
    assert transition["properties"]["next_gate"]["enum"] == expected_gates
    assert transition["properties"]["lifecycle_profile"]["properties"]["id"]["const"] == "gwc.universal-run.v2"
    assert transition["properties"]["lifecycle_profile"]["properties"]["version"]["const"] == 2
    assert state["properties"]["active_gate"]["enum"] == expected_gates
    assert state["properties"]["gate_states"]["required"] == expected_gates
    assert state["properties"]["lifecycle_profile"]["properties"]["id"]["const"] == "gwc.universal-run.v2"
    assert state["properties"]["lifecycle_profile"]["properties"]["version"]["const"] == 2


def test_q0_profile_is_explicit_universal_v2_and_fail_closed():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    profile = json.loads((root / "core/node-architect/q0-live-qualification-profile.json").read_text())
    schema = json.loads((root / "schemas/q0-live-qualification-profile.schema.json").read_text())

    assert profile["profile_id"] == "gwc.q0-live-qualification.v2"
    assert profile["revision"] == "2.0"
    assert profile["runtime_profile"] == {"id": "gwc.universal-run.v2", "version": 2}
    assert schema["properties"]["runtime_profile"]["const"] == {"id": "gwc.universal-run.v2", "version": 2}
    assert profile["legacy_fallback"] is False


def test_q0_gate_advance_uses_ur_namespaced_kernel_transitions():
    from tools.node_architect.q0_qualification import advance_qualification_gate

    transition = advance_qualification_gate(
        current_gate="UR.G0",
        current_state="ACTIVE",
        evidence={"UNDERSTANDING_RECEIPT": {"receipt_digest": "sha256:" + "a" * 64}},
        sequence=8,
        run_id="scrum781-q0-20260920T074727Z",
        runtime_plan_digest="sha256:" + "b" * 64,
    )

    assert transition["current_gate"] == "UR.G0"
    assert transition["next_gate"] == "UR.G1"



def test_cli_missing_universal_assignment_fails_without_legacy_fallback(tmp_path, monkeypatch, capsys):
    import json
    from tools.node_architect import agent_runtime_cli

    class TestProvider:
        name = "test-provider"

    manifest = tmp_path / "missing-universal-assignment.json"
    manifest.write_text(json.dumps({"event": {}, "provider_name": "test-provider"}))
    legacy_calls = []
    monkeypatch.setattr(agent_runtime_cli, "_load_factory", lambda _spec: lambda: TestProvider())
    monkeypatch.setattr(agent_runtime_cli, "_prepare_event", lambda _manifest, _provider: {})
    monkeypatch.setattr(
        agent_runtime_cli,
        "run_agent_runtime_loop",
        lambda *_args, **_kwargs: legacy_calls.append("called") or {"status": "SEMANTIC_NODE_COMPLETE"},
        raising=False,
    )

    exit_code = agent_runtime_cli.main([
        "--manifest", str(manifest), "--provider-factory", "ignored:factory"
    ])
    result = json.loads(capsys.readouterr().out.splitlines()[-1])

    assert exit_code != 0
    assert legacy_calls == []
    assert result["reason_code"] == "GWC_RUNTIME_DEFECT"
    assert result["runtime_family"] == "UNIVERSAL_V2"


def test_machine_readable_runtime_profile_is_v2_only_and_fail_closed():
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    profile_path = root / "core/node-architect/universal-runtime-default-profile.json"
    schema_path = root / "schemas/node-architect/universal-runtime-default-profile.schema.json"
    assert profile_path.is_file()
    assert schema_path.is_file()

    profile = json.loads(profile_path.read_text())
    schema = json.loads(schema_path.read_text())
    import jsonschema
    jsonschema.validate(profile, schema)
    body = {key: value for key, value in profile.items() if key != "profile_digest"}
    digest = "sha256:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()

    assert profile["runtime_family"] == "UNIVERSAL_V2"
    assert profile["runtime_protocol"] == "gwc.universal.controller/v2"
    assert profile["lifecycle_gates"] == [f"UR.G{index}" for index in range(7)]
    assert profile["legacy_gwc_v1"]["load_by_default"] is False
    assert profile["legacy_gwc_v1"]["fallback"] == "GWC_RUNTIME_DEFECT"
    assert profile["profile_digest"] == digest


def test_all_active_universal_run_schemas_are_v2_and_ur_namespaced():
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    schema_paths = sorted((root / "schemas/node-architect/universal-run").glob("*.schema.json"))
    assert len(schema_paths) == 15
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert "/universal-run/v2/" in schema["$id"], path.name
        schema_id = schema.get("properties", {}).get("schema_id", {}).get("const")
        if isinstance(schema_id, str) and schema_id.startswith("gwc.universal-run."):
            assert schema_id.endswith(".v2"), (path.name, schema_id)
        def walk(value):
            if isinstance(value, dict):
                if isinstance(value.get("enum"), list):
                    assert not any(re.fullmatch(r"G[0-6](_[A-Z_]+)?", str(item)) for item in value["enum"]), path.name
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(schema)


def _make_v2_binding():
    import hashlib
    import json

    from tools.node_architect.q0_qualification import q0_qualification_profile
    from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile
    from tools.node_architect.universal_run_topology import create_node_allocation

    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    digest = lambda value: "sha256:" + hashlib.sha256(canonical(value)).hexdigest()
    profile = load_universal_v2_default_profile()
    q0 = q0_qualification_profile()
    run_id = "test-universal-v2-run"
    node_id = "q0.qualification-campaign"
    allocation_id = f"{run_id}:{node_id}:r3"
    plan_body = {
        "schema_id": "gwc.universal-run.runtime-plan.v2",
        "schema_version": 2,
        "run_id": run_id,
        "revision": 3,
        "target_contract_ref": "test-controller-contract",
        "node_allocations": [allocation_id],
        "runtime_epoch": profile["runtime_epoch"],
        "runtime_profile_ref": "core/node-architect/universal-runtime-default-profile.json",
        "runtime_default_profile_digest": profile["profile_digest"],
        "qualification_profile_ref": "core/node-architect/q0-live-qualification-profile.json",
        "qualification_profile_digest": q0["profile_digest"],
        "previous_digest": "sha256:" + "a" * 64,
        "source_binding": {
            "repository": "nhatnguyenquang1838-coder/gwc",
            "branch": "fix/SCRUM-781-q0-canonical",
            "pre_head_sha": "6e753f48344918d9141f9721a005695f2b4a9bea",
        },
    }
    plan = {**plan_body, "digest": digest(plan_body)}
    allocation = create_node_allocation(
        record_id=f"NA-{run_id}-r3",
        run_id=run_id,
        node_allocation_id=allocation_id,
        kind="WORK",
        requirement="REQUIRED",
        created_at="2026-10-03T00:00:00Z",
        created_by={"profile": "test"},
        source_refs=[node_id],
        predecessor_refs=[plan["previous_digest"]],
    )
    state_body = {
        "schema_id": "gwc.universal-run.run-state.v2",
        "schema_version": 2,
        "run_id": run_id,
        "sequence": 8,
        "predecessor_sequence": 7,
        "active_gate": "UR.G2",
        "runtime_epoch": profile["runtime_epoch"],
        "execution_refs": {
            "branch": plan["source_binding"]["branch"],
            "node_allocation_id": allocation_id,
            "node_allocation_ref": "q0-c93/node-allocation-q0-universal-v2-r3.json#record_id=" + allocation["record_id"],
            "base_sha": "414002f92d48083e7133236346b26e3a2a047e33",
            "candidate_sha": plan["source_binding"]["pre_head_sha"],
            "qualification_profile_digest": q0["profile_digest"],
            "runtime_plan_digest": plan["digest"],
            "cursor_ref": f"{run_id}:UR.G2:seq8",
        },
        "gate_evidence": {},
        "typed_next": "EXECUTE_UNIVERSAL_ACTION",
        "next_owner": "EXECUTOR",
        "evidence_gap": ["EXECUTION_RECEIPT"],
        "consumed_receipts": [],
    }
    state = {**state_body, "state_digest": digest(state_body)}
    return profile, plan, state, allocation


def _make_controller_owned_g4_binding():
    import hashlib
    import json

    profile, plan, state, allocation = _make_v2_binding()
    state_body = {key: value for key, value in state.items() if key != "state_digest"}
    state_body.update({
        "sequence": 10,
        "predecessor_sequence": 9,
        "predecessor_state_digest": state["state_digest"],
        "active_gate": "UR.G4",
        "typed_next": "CONTINUE_UNIVERSAL_LANE_REMEDIATION",
        "next_owner": "CONTROLLER",
        "evidence_gap": ["INTEGRATION_RECEIPT", "integration_outcome"],
    })
    refs = dict(state_body["execution_refs"])
    refs["cursor_ref"] = f"{state['run_id']}:UR.G4:seq10"
    state_body["execution_refs"] = refs
    state = {
        **state_body,
        "state_digest": "sha256:" + hashlib.sha256(
            json.dumps(state_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
    }
    return profile, plan, state, allocation


def test_controller_owned_g4_does_not_emit_executor_assignment():
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)

    action = controller.assign_current_action()

    assert action["actor"] == "CONTROLLER"
    assert action["next_owner"] == "CONTROLLER"
    assert action["typed_next"] == "CONTINUE_UNIVERSAL_LANE_REMEDIATION"
    assert action["action"] == "q0_integrate_candidate"
    assert action["effect_authority"] == "NONE"
    assert action["executed_effects"] == []
    assert action["schema_id"] == "gwc.universal-run.controller-local-action.v2"


def test_assign_current_action_honors_runstate_next_owner():
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_v2_binding()
    executor = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    assert executor.assign_current_action()["actor"] == "EXECUTOR"

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    assert controller.assign_current_action()["actor"] == "CONTROLLER"


def test_controller_owned_g4_in_place_completes_without_integration_receipt():
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller.assign_current_action()

    decision = controller.complete_controller_owned_gate(evidence={"integration_outcome": "IN_PLACE"})
    successor = decision["successor_run_state"]

    assert decision["gate_advanced"] is True
    assert decision["next_gate"] == "UR.G5"
    assert decision["next_owner"] == successor["next_owner"]
    assert decision["idempotent_replay"] is False
    assert successor["sequence"] == 11
    assert successor["active_gate"] == "UR.G5"
    assert successor["gate_evidence"] == {"integration_outcome": "IN_PLACE"}
    assert successor["evidence_gap"] == ["TARGET_VALIDATION_RECEIPT"]
    assert "INTEGRATION_RECEIPT" not in successor["gate_evidence"]
    assert successor["consumed_receipts"] == state["consumed_receipts"]
    assert state["active_gate"] == "UR.G4" and state["sequence"] == 10
    assert decision["authority_granted"] is False
    assert decision["executed_effects"] == []


def test_controller_owned_g4_in_place_uses_canonical_complete_q0_gate():
    import json
    from pathlib import Path
    import jsonschema

    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller.assign_current_action()
    decision = controller.complete_controller_owned_gate(evidence={"integration_outcome": "IN_PLACE"})
    transition = decision["transition_receipt"]
    schema_path = Path(__file__).resolve().parents[1] / "schemas/node-architect/universal-run/controller-transition-receipt.schema.json"
    jsonschema.validate(transition, json.loads(schema_path.read_text()))

    assert transition["from_gate"] == "UR.G4"
    assert transition["to_gate"] == "UR.G5"
    assert transition["kernel_completion_receipt"]["explicit_outcome"] == "IN_PLACE"
    assert transition["authority_granted"] is False
    assert transition["executed_effects"] == []


def test_controller_owned_g4_transition_is_persisted_and_exactly_once(tmp_path):
    import hashlib
    import json
    from tools.node_architect.universal_run_controller import UniversalController
    from tools.node_architect.universal_run_persistence import (
        materialize_controller_successor_snapshot,
        materialize_successor_bound_transition_receipt,
    )

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller.assign_current_action()
    decision = controller.complete_controller_owned_gate(evidence={"integration_outcome": "IN_PLACE"})
    path = tmp_path / "controller-local-g4-transition.json"
    snapshot = materialize_controller_successor_snapshot(
        successor_run_state=decision["successor_run_state"],
        runtime_plan_digest=plan["digest"],
        candidate_sha=plan["source_binding"]["pre_head_sha"],
        transition_ref=decision["transition_receipt"]["transition_ref"],
        path=tmp_path / "controller-local-g4-successor.json",
    )

    materialized = materialize_successor_bound_transition_receipt(
        transition=decision["transition_receipt"], snapshot=snapshot, path=path
    )
    readback = path.read_bytes()
    persisted = json.loads(readback)

    assert persisted == materialized["transition"]
    assert persisted["successor_state_digest"] == decision["successor_run_state"]["state_digest"]
    assert hashlib.sha256(readback).hexdigest() == materialized["file_sha256"]
    assert materialized["idempotent_replay"] is False
    assert decision["successor_run_state"]["controller_local_completion_ledger"]


def test_duplicate_controller_local_completion_is_idempotent():
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller.assign_current_action()
    first = controller.complete_controller_owned_gate(evidence={"integration_outcome": "IN_PLACE"})
    restarted = UniversalController(
        profile=profile, runtime_plan=plan,
        run_state=first["successor_run_state"], node_allocation=allocation,
    )

    replay = restarted.complete_controller_owned_gate(
        evidence={"integration_outcome": "IN_PLACE"}, expected_sequence=10
    )

    assert replay["idempotent_replay"] is True
    assert replay["gate_advanced"] is False
    assert replay["transition_ref"] == first["transition_receipt"]["transition_ref"]
    assert replay["consumed_receipt_digest"] == first["controller_local_completion_receipt"]["receipt_digest"]
    assert restarted.run_state["sequence"] == 11
    assert restarted.run_state["active_gate"] == "UR.G5"


def test_conflicting_same_identity_controller_local_completion_fails_closed():
    import pytest
    from tools.node_architect.universal_run_controller import UniversalController, UniversalControllerError

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller.assign_current_action()
    first = controller.complete_controller_owned_gate(evidence={"integration_outcome": "IN_PLACE"})
    restarted = UniversalController(
        profile=profile, runtime_plan=plan,
        run_state=first["successor_run_state"], node_allocation=allocation,
    )

    with pytest.raises(UniversalControllerError, match="CONTROLLER_LOCAL_COMPLETION_IDEMPOTENCY_CONFLICT"):
        restarted.complete_controller_owned_gate(
            evidence={"integration_outcome": "INTEGRATED"}, expected_sequence=10
        )

    assert restarted.run_state["sequence"] == 11
    assert restarted.run_state["active_gate"] == "UR.G5"


def test_controller_owned_g4_rejects_conflicting_live_executor_assignment():
    import pytest
    from tools.node_architect.universal_run_controller import UniversalController, UniversalControllerError

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller._assignment = {"actor": "EXECUTOR", "gate": "UR.G4", "sequence": 10}

    with pytest.raises(UniversalControllerError, match="CONTROLLER_LOCAL_GATE_EXECUTOR_ASSIGNMENT_CONFLICT"):
        controller.complete_controller_owned_gate(evidence={"integration_outcome": "IN_PLACE"})


def test_controller_owned_g4_completion_requires_controller_local_action_assignment():
    import pytest
    from tools.node_architect.universal_run_controller import UniversalController, UniversalControllerError

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)

    with pytest.raises(UniversalControllerError, match="CONTROLLER_LOCAL_ACTION_NOT_ISSUED"):
        controller.complete_controller_owned_gate(evidence={"integration_outcome": "IN_PLACE"})


def test_executor_cannot_advance_controller_owned_g4():
    import pytest
    from tools.node_architect.universal_run_controller import UniversalController, UniversalControllerError

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    assignment = controller.assign_current_action()
    receipt = _g2_executor_receipt(profile, assignment)

    with pytest.raises(UniversalControllerError, match="CONTROLLER_OWNER_EXECUTOR_RECEIPT_FORBIDDEN"):
        controller.consume_executor_receipt(receipt)

    assert controller.run_state["sequence"] == 10
    assert controller.run_state["active_gate"] == "UR.G4"


def test_ur_g2_executor_receipt_flow_remains_green():
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_v2_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    assignment = controller.assign_current_action()
    decision = controller.consume_executor_receipt(_g2_executor_receipt(profile, assignment))

    assert assignment["actor"] == "EXECUTOR"
    assert decision["next_gate"] == "UR.G3"
    assert decision["next_owner"] == "EXECUTOR"
    assert decision["gate_advanced"] is True


def test_continuation_does_not_build_executor_assignment_for_controller_owner():
    from tools.node_architect.universal_run_continuation import continue_from_native_state

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    decision = continue_from_native_state(
        profile=profile,
        runtime_plan=plan,
        run_state=state,
        node_allocation=allocation,
    )

    assert decision["next_owner"] == "CONTROLLER"
    assert decision["typed_next"] == "CONTINUE_UNIVERSAL_LANE_REMEDIATION"
    assert decision["assignment"]["actor"] == "CONTROLLER"
    assert decision["assignment"]["action"] == "q0_integrate_candidate"


def test_universal_controller_assigns_native_ur_action_without_mailbox_cursor():
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_v2_binding()
    controller = UniversalController(
        profile=profile,
        runtime_plan=plan,
        run_state=state,
        node_allocation=allocation,
    )

    assignment = controller.assign_current_action()

    assert assignment["runtime_protocol"] == "gwc.universal.controller/v2"
    assert assignment["run_id"] == state["run_id"]
    assert assignment["gate"] == "UR.G2"
    assert assignment["action"] == "q0_execute_probe"
    assert assignment["idempotency_key"]
    assert "expected_executor_seq" not in assignment
    assert "typed_next" not in assignment
    assert state["sequence"] == 8


def test_q0_g2_accepts_only_native_v2_executor_receipt():
    import hashlib
    import json

    from tools.node_architect.q0_qualification import complete_q0_gate, q0_qualification_profile

    profile, plan, state, allocation = _make_v2_binding()
    node_id = q0_qualification_profile()["qualification_nodes"]["UR.G2"]["node_id"]
    body = {
        "schema_id": "gwc.universal-run.executor-action-receipt.v2",
        "schema_version": 2,
        "artifact_type": "executor-action-receipt",
        "runtime_protocol": profile["runtime_protocol"],
        "runtime_epoch": profile["runtime_epoch"],
        "runtime_profile_digest": profile["profile_digest"],
        "route_id": "UNIVERSAL_RUN_NEW_RUNTIME",
        "run_id": state["run_id"],
        "sequence": state["sequence"],
        "gate": "UR.G2",
        "action": "q0_execute_probe",
        "node_id": node_id,
        "node_allocation_id": allocation["node_allocation_id"],
        "runtime_plan_digest": plan["digest"],
        "assignment_digest": "sha256:" + "c" * 64,
        "event_id": state["run_id"] + ":UR.G2:seq8",
        "host_status": "ACTION_COMPLETE",
        "host_result_digest": "sha256:" + "d" * 64,
        "evidence_refs": {"executor_receipt": "q0-c93/evidence/executor-receipt.json"},
        "authority_granted": False,
        "executed_effects": [],
    }
    receipt = {
        **body,
        "receipt_digest": "sha256:" + hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
    }

    completion = complete_q0_gate(
        gate="UR.G2",
        evidence={"EXECUTION_RECEIPT": receipt},
        run_id=state["run_id"],
        runtime_plan_digest=plan["digest"],
    )

    assert completion["gate_state"] == "PASSED"


def _g2_executor_receipt(profile, assignment):
    import hashlib
    import json

    body = {
        "schema_id": "gwc.universal-run.executor-action-receipt.v2",
        "schema_version": 2,
        "artifact_type": "executor-action-receipt",
        "runtime_protocol": profile["runtime_protocol"],
        "runtime_epoch": profile["runtime_epoch"],
        "runtime_profile_digest": profile["profile_digest"],
        "route_id": "UNIVERSAL_RUN_NEW_RUNTIME",
        "run_id": assignment["run_id"],
        "sequence": assignment["sequence"],
        "gate": assignment["gate"],
        "action": assignment["action"],
        "actor": "EXECUTOR",
        "node_id": assignment["node_id"],
        "node_allocation_id": assignment["node_allocation_id"],
        "runtime_plan_digest": assignment["runtime_plan_digest"],
        "assignment_digest": assignment["assignment_digest"],
        "event_id": assignment["idempotency_key"],
        "host_status": "ACTION_COMPLETE",
        "host_result_digest": "sha256:" + "d" * 64,
        "evidence_refs": {"executor_receipt": "q0-c96/evidence/executor-receipt.json"},
        "authority_granted": False,
        "executed_effects": [],
    }
    return {
        **body,
        "receipt_digest": "sha256:" + hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
    }


def test_controller_consumes_receipt_with_durable_transition_binding_and_g3_next():
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_v2_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    assignment = controller.assign_current_action()
    receipt = _g2_executor_receipt(profile, assignment)

    decision = controller.consume_executor_receipt(receipt)
    successor = decision["successor_run_state"]
    transition = decision["transition_receipt"]

    assert "typed_next" not in receipt
    assert decision["typed_next"] == "MATERIALIZE_UR_G3_VERIFICATION_RECEIPT"
    assert decision["next_owner"] == "EXECUTOR"
    assert decision["idempotent_replay"] is False
    assert successor["active_gate"] == "UR.G3"
    assert successor["sequence"] == 9
    assert successor["typed_next"] == "MATERIALIZE_UR_G3_VERIFICATION_RECEIPT"
    assert successor["evidence_gap"] == ["VERIFICATION_RECEIPT"]
    assert transition["from_gate"] == "UR.G2"
    assert transition["to_gate"] == "UR.G3"
    assert transition["pre_state"]["sequence"] == 8
    assert transition["pre_state"]["state_digest"] == state["state_digest"]
    assert transition["consumed_receipt_digest"] == receipt["receipt_digest"]
    assert transition["post_state"]["sequence"] == 9
    assert transition["post_state"]["state_digest"] == successor["state_digest"]
    assert transition["authority_granted"] is False
    assert transition["executed_effects"] == []
    assert state["active_gate"] == "UR.G2" and state["sequence"] == 8
    assert controller.run_state["state_digest"] == successor["state_digest"]


def test_ur_g3_verification_receipt_flow_remains_green():
    import json
    from tools.node_architect import q0_qualification
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_v2_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    g2_assignment = controller.assign_current_action()
    g2_receipt = _g2_executor_receipt(profile, g2_assignment)
    g2_decision = controller.consume_executor_receipt(g2_receipt)
    g3_state = g2_decision["successor_run_state"]
    g3_controller = UniversalController(profile=profile, runtime_plan=plan, run_state=g3_state, node_allocation=allocation)
    g3_assignment = g3_controller.assign_current_action()
    g3_executor_receipt = _g2_executor_receipt(profile, g3_assignment)
    candidate_sha = plan["source_binding"]["pre_head_sha"]
    g2_receipt_bytes = (json.dumps(g2_receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    verification_receipt = q0_qualification.create_q0_verification_receipt(
        run_id=g2_receipt["run_id"],
        runtime_plan_digest=plan["digest"],
        candidate_sha=candidate_sha,
        g2_execution_receipt=g2_receipt,
        g2_execution_receipt_ref="fixture/q0/g2-execution-receipt.json",
        g2_execution_receipt_bytes=g2_receipt_bytes,
        controller_transition_receipt=g2_decision["transition_receipt"],
        v2_isolation_evidence={
            "candidate_sha": candidate_sha,
            "result": "UNIVERSAL_V2_CORE_ISOLATED_GWC_V1_QUARANTINED",
            "evidence_ref": "fixture/q0/v2-isolation-evidence.json",
            "evidence_sha256": "a" * 64,
        },
        v1_quarantine_evidence={
            "manifest_ref": "legacy/gwc-v1/runtime-quarantine-manifest.json",
            "manifest_sha256": "b" * 64,
            "archived_sources_verified": 16,
            "fallback_forbidden": True,
        },
        regression_evidence={
            "candidate_sha": candidate_sha,
            "command": "pytest tests/test_universal_v2_core_isolation.py -q",
            "exit_code": 0,
            "tests_passed": 1,
            "result_sha256": "c" * 64,
        },
        created_at="2026-10-03T00:00:00Z",
    )

    decision = g3_controller.consume_executor_receipt(
        g3_executor_receipt,
        evidence_artifacts={"VERIFICATION_RECEIPT": verification_receipt},
    )

    assert decision["gate_advanced"] is True
    assert decision["from_gate"] == "UR.G3"
    assert decision["next_gate"] == "UR.G4"
    assert decision["next_owner"] == "CONTROLLER"
    assert decision["consumed_receipt_digest"] == g3_executor_receipt["receipt_digest"]
    assert decision["successor_run_state"]["gate_evidence"] == {"VERIFICATION_RECEIPT": verification_receipt}
    assert decision["successor_run_state"]["consumed_receipts"][-1] == g3_executor_receipt["receipt_digest"]
    assert decision["authority_granted"] is False
    assert decision["executed_effects"] == []


def test_controller_replays_exact_receipt_idempotently_after_reconstruction():
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_v2_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    assignment = controller.assign_current_action()
    receipt = _g2_executor_receipt(profile, assignment)
    first = controller.consume_executor_receipt(receipt)
    first_state = controller.run_state

    replay = controller.consume_executor_receipt(receipt)
    restarted = UniversalController(profile=profile, runtime_plan=plan, run_state=first_state, node_allocation=allocation)
    replay_after_restart = restarted.consume_executor_receipt(receipt)

    assert replay["idempotent_replay"] is True
    assert replay_after_restart["idempotent_replay"] is True
    assert replay["transition_ref"] == first["transition_receipt"]["transition_ref"]
    assert replay_after_restart["transition_ref"] == replay["transition_ref"]
    assert controller.run_state["sequence"] == 9
    assert restarted.run_state["state_digest"] == first_state["state_digest"]


def test_controller_rejects_different_receipt_under_consumed_idempotency_key():
    import hashlib
    import json
    import pytest

    from tools.node_architect.universal_run_controller import UniversalController, UniversalControllerError

    profile, plan, state, allocation = _make_v2_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    assignment = controller.assign_current_action()
    receipt = _g2_executor_receipt(profile, assignment)
    controller.consume_executor_receipt(receipt)
    conflicting_body = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    conflicting_body["host_result_digest"] = "sha256:" + "e" * 64
    conflicting = {
        **conflicting_body,
        "receipt_digest": "sha256:" + hashlib.sha256(
            json.dumps(conflicting_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
    }
    before = controller.run_state["state_digest"]

    with pytest.raises(UniversalControllerError, match="EXECUTOR_RECEIPT_IDEMPOTENCY_CONFLICT"):
        controller.consume_executor_receipt(conflicting)

    assert controller.run_state["state_digest"] == before
    assert controller.run_state["sequence"] == 9


def test_controller_transition_receipt_schema_and_materializer_are_exactly_once(tmp_path):
    import hashlib
    import json
    from pathlib import Path
    import pytest

    from tools.node_architect.universal_run_controller import (
        UniversalController,
        UniversalControllerError,
        materialize_controller_transition_receipt,
    )
    from tools.node_architect.universal_run_persistence import (
        materialize_controller_successor_snapshot,
        materialize_successor_bound_transition_receipt,
    )
    import jsonschema

    profile, plan, state, allocation = _make_v2_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    assignment = controller.assign_current_action()
    decision = controller.consume_executor_receipt(_g2_executor_receipt(profile, assignment))
    transition = decision["transition_receipt"]
    snapshot = materialize_controller_successor_snapshot(
        successor_run_state=decision["successor_run_state"],
        runtime_plan_digest=plan["digest"],
        candidate_sha=plan["source_binding"]["pre_head_sha"],
        transition_ref=transition["transition_ref"],
        path=tmp_path / "controller-g2-successor.json",
    )
    path = tmp_path / "controller-transition-receipt.json"
    bound_transition = materialize_successor_bound_transition_receipt(
        transition=transition, snapshot=snapshot, path=path
    )
    transition = bound_transition["transition"]
    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/node-architect/universal-run/controller-transition-receipt.schema.json").read_text())
    jsonschema.validate(transition, schema)
    reread = path.read_bytes()
    replay = materialize_controller_transition_receipt(receipt=transition, path=path)

    assert json.loads(reread) == transition
    assert bound_transition["file_sha256"] == hashlib.sha256(reread).hexdigest()
    assert bound_transition["transition_digest"] == transition["transition_digest"]
    assert bound_transition["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    conflicting_body = {key: value for key, value in transition.items() if key != "transition_digest"}
    conflicting_body["transition_ref"] += ":different"
    conflicting = {
        **conflicting_body,
        "transition_digest": "sha256:" + hashlib.sha256(
            json.dumps(conflicting_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
    }
    with pytest.raises(UniversalControllerError, match="CONTROLLER_TRANSITION_RECEIPT_CONFLICT"):
        materialize_controller_transition_receipt(receipt=conflicting, path=path)


def test_universal_executor_emits_actor_receipt_without_controller_fields(tmp_path):
    import json
    from pathlib import Path

    from tools.node_architect.universal_run_controller import UniversalController
    from tools.node_architect.universal_run_execution import UniversalExecutor

    class ReadOnlyProvider:
        name = "test-provider"

        def run(self, request):
            assert request["action"] == "q0_execute_probe"
            assert "typed_next" not in request
            return {"outcome": "PASS", "observations": ["fresh-process-ready"]}

    profile, plan, state, allocation = _make_v2_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    assignment = controller.assign_current_action()
    provider = ReadOnlyProvider()
    receipt = UniversalExecutor().execute(
        assignment=assignment,
        provider=provider,
        event={"event_id": "test-event"},
        evidence_root=tmp_path,
        max_iterations=1,
    )

    assert receipt["schema_id"] == "gwc.universal-run.executor-action-receipt.v2"
    assert receipt["host_status"] == "ACTION_COMPLETE"
    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/node-architect/universal-run/executor-action-receipt.schema.json").read_text())
    import jsonschema
    jsonschema.validate(receipt, schema)
    assert receipt["authority_granted"] is False
    assert receipt["executed_effects"] == []
    assert not any(key in receipt for key in ("typed_next", "successor_run_state", "controller_decision", "next_gate"))
    assert state["active_gate"] == "UR.G2" and state["sequence"] == 8
    assert (tmp_path / receipt["evidence_refs"]["executor_receipt"]).is_file()


def test_executor_receipt_schema_excludes_controller_fields():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    schema_path = root / "schemas/node-architect/universal-run/executor-action-receipt.schema.json"
    assert schema_path.is_file()
    schema = json.loads(schema_path.read_text())
    assert schema["additionalProperties"] is False
    assert "typed_next" not in schema["properties"]
    assert schema["properties"]["gate"]["enum"] == [f"UR.G{index}" for index in range(7)]


def test_cli_executes_bound_v2_manifest_through_controller_and_executor(tmp_path, capsys):
    import json
    from pathlib import Path

    from tools.node_architect import agent_runtime_cli

    profile, plan, state, allocation = _make_v2_binding()
    provider_module = tmp_path / "provider.py"
    provider_module.write_text(
        "class Provider:\n"
        "    name = 'test-provider'\n"
        "    def run(self, request):\n"
        "        return {'outcome': 'PASS', 'observations': ['v2-cli-probe']}\n"
        "def build(): return Provider()\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "provider_name": "test-provider",
        "event": {"event_id": "v2-cli-event"},
        "universal_run": {
            "runtime_plan": plan,
            "run_state": state,
            "node_allocation": allocation,
            "evidence_root": str(tmp_path / "receipts"),
        },
    }), encoding="utf-8")

    exit_code = agent_runtime_cli.main([
        "--manifest", str(manifest), "--provider-factory", f"{provider_module}:build"
    ])
    result = json.loads(capsys.readouterr().out.splitlines()[-1])

    assert exit_code == 0, result
    assert result["status"] == "UNIVERSAL_RUN_NODE_COMPLETE"
    assert result["controller_decision"]["next_gate"] == "UR.G3"
    assert "typed_next" not in result["executor_receipt"]
    assert result["authority_granted"] is False


def test_default_v2_import_graph_excludes_legacy_runtime_and_governance():
    import ast
    import json
    from pathlib import Path
    from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile

    root = Path(__file__).resolve().parents[1]
    profile = load_universal_v2_default_profile()
    entries = [profile["default_entrypoint"].split(":", 1)[0], profile["controller_entrypoint"].split(":", 1)[0], profile["executor_entrypoint"].split(":", 1)[0]]
    forbidden = {
        "agent_runtime_entrypoint", "live_runtime_bridge", "universal_run_continuation",
        "universal_run_legacy", "approval_token_generation", "generate_resume_token",
        "resume_token_validation", "slack_task_controller",
    }
    queue = list(entries)
    visited = set()
    while queue:
        module_name = queue.pop()
        if module_name in visited:
            continue
        visited.add(module_name)
        path = root / (module_name.replace(".", "/") + ".py")
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = module_name.rpartition(".")[0]
                    imported.append(base + ("." + node.module if node.module else ""))
                elif node.module:
                    imported.append(node.module)
        for dependency in imported:
            if not dependency.startswith("tools.node_architect"):
                continue
            leaf = dependency.rsplit(".", 1)[-1]
            assert leaf not in forbidden, f"V2 boot graph reached quarantined module: {dependency}"
            queue.append(dependency)

    assert set(entries) <= visited
    assert "tools.node_architect.universal_runtime_profile" in visited
    assert "tools.node_architect.universal_run_controller" in visited
    assert "tools.node_architect.universal_run_execution" in visited


def test_root_q0_boot_points_to_consumed_machine_runtime_profile():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    instructions = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "core/node-architect/universal-runtime-default-profile.json" in instructions
    assert "tools/node_architect/universal_runtime_profile.py" in instructions


def test_gwc_v1_runtime_is_manifest_quarantined_and_not_authoritative():
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "legacy/gwc-v1/runtime-quarantine-manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["load_by_default"] is False
    assert manifest["runtime_authority"] == "NONE"
    assert manifest["fallback"] == "GWC_RUNTIME_DEFECT"
    assert manifest["replay_policy"] == "EXPLICIT_HISTORICAL_PROFILE_ONLY"
    source_paths = {item["source_path"] for item in manifest["quarantined_sources"]}
    assert {
        "tools/node_architect/agent_runtime_entrypoint.py",
        "tools/node_architect/live_runtime_bridge.py",
        "tools/node_architect/universal_run_continuation.py",
        "tools/node_architect/universal_run_legacy.py",
    } <= source_paths
    for item in manifest["quarantined_sources"]:
        archived = root / item["archive_path"]
        assert archived.is_file()
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == item["sha256"]


def test_legacy_runtime_entrypoint_fails_closed_without_v1_execution():
    from tools.node_architect.universal_run_legacy import LegacyRuntimeQuarantined, load_legacy_runtime

    try:
        load_legacy_runtime()
    except LegacyRuntimeQuarantined as exc:
        assert exc.code == "GWC_RUNTIME_DEFECT"
    else:
        raise AssertionError("quarantined GWC v1 runtime was executable")




def test_transport_adapters_do_not_change_native_decision_digest():
    import hashlib
    import json

    from tools.node_architect.universal_runtime_transport import (
        InProcessTransportAdapter,
        MailboxProjectionAdapter,
        project_controller_decision,
    )

    subject = {
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
        "actor": "CONTROLLER",
        "typed_next": "CONTINUE_UNIVERSAL_LANE_REMEDIATION",
        "run_id": "test-universal-v2-run",
        "sequence": 9,
    }
    decision = {
        "decision_subject": subject,
        "decision_digest": "sha256:" + hashlib.sha256(
            json.dumps(subject, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
    }
    local = project_controller_decision(decision, InProcessTransportAdapter())
    mailbox = project_controller_decision(decision, MailboxProjectionAdapter())

    assert local["decision_digest"] == mailbox["decision_digest"] == decision["decision_digest"]
    assert local["transport_receipt"]["transport"] != mailbox["transport_receipt"]["transport"]
    assert local["decision_subject"] == mailbox["decision_subject"] == subject


def test_c91_replay_is_opaque_historical_evidence_not_controller_authority():
    import copy
    import hashlib
    from pathlib import Path

    from tools.node_architect.universal_run_controller import UniversalController

    root = Path(__file__).resolve().parents[1]
    raw_body = (root / "tests/fixtures/legacy/gwc-v1/c91-controller-comment.md").read_bytes()
    expected_sha256 = "6f65171fda1b723d9e42efb886fceeac2e26c56236fe3f3635394b8f97458dcd"
    assert hashlib.sha256(raw_body).hexdigest() == expected_sha256
    profile, plan, state, allocation = _make_v2_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    before = copy.deepcopy(controller.run_state)

    replay = controller.record_historical_controller_evidence(raw_body, expected_sha256=expected_sha256)

    assert replay["classification"] == "HISTORICAL_LEGACY_INCIDENT_EVIDENCE"
    assert replay["authority_effect"] is False
    assert replay["runtime_state_changed"] is False
    assert controller.run_state == before
    assert "typed_next" not in replay and "wait_state" not in replay and "hitl_decision" not in replay


def test_active_continuation_is_native_and_mailbox_independent():
    from tools.node_architect import universal_run_continuation

    profile, plan, state, allocation = _make_v2_binding()
    result = universal_run_continuation.continue_from_native_state(
        profile=profile,
        runtime_plan=plan,
        run_state=state,
        node_allocation=allocation,
    )

    assert result["next_owner"] == "EXECUTOR"
    assert result["typed_next"] == "EXECUTE_UNIVERSAL_ACTION"
    assert result["assignment"]["gate"] == "UR.G2"
    assert not any(key in result for key in ("expected_executor_seq", "mailbox_expected_executor_seq", "history_controller"))


def test_live_runtime_bridge_has_only_ur_gate_namespace():
    import pytest
    from tools.node_architect.live_runtime_bridge import GATES, build_live_runtime_event

    assert GATES == tuple(f"UR.G{index}" for index in range(7))
    with pytest.raises(ValueError, match="UNIVERSAL_GATE_INVALID"):
        build_live_runtime_event(
            canonical_state={"task_id": "SCRUM-781", "source_kind": "canonical_agent_gate_state"},
            event_id="test-legacy-gate",
            run_id="test-universal-v2-run",
            gate="G0_CONTEXT",
            requested_action="q0_execute_probe",
            scenario="test",
            input_payload={"workflow_mode": "q0_live_qualification", "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT"},
        )











def test_universal_node_allocation_materializes_v2_profile_and_schema():
    _, _, _, allocation = _make_v2_binding()

    assert allocation["schema_id"] == "gwc.universal-run.node-allocation.v2"
    assert allocation["schema_version"] == 2
    assert allocation["lifecycle_profile"] == {"id": "gwc.universal-run.v2", "version": 2}


def test_native_run_state_record_materializes_v2_schema_and_ur_gates():
    import json
    from pathlib import Path
    import jsonschema

    from tools.node_architect.universal_run_kernel import GATES, UNIVERSAL_PROFILE
    from tools.node_architect.universal_run_state import create_run_state_record, verify_run_state_record

    record = create_run_state_record(
        record_id="RS-SCRUM781-V2-1",
        run_id="test-universal-v2-run",
        lifecycle_profile=UNIVERSAL_PROFILE,
        run_manifest_ref="RM-test-universal-v2-run",
        run_manifest_digest="a" * 64,
        state_revision=1,
        predecessor_state_ref=None,
        predecessor_state_digest=None,
        sequence=0,
        active_gate="UR.G0",
        gate_states={gate: ("ACTIVE" if gate == "UR.G0" else "NOT_STARTED") for gate in GATES},
        terminal_state="OPEN",
        execution_refs={"runtime_plan_ref": None, "runtime_plan_digest": None, "cursor_ref": None},
        future_contract_refs={"target_contract_ref": None, "closure_receipt_ref": None, "handoff_receipt_ref": None},
        created_at="2026-10-03T00:00:00Z",
        created_by={"kind": "agent", "id": "DWA"},
        provenance={"predecessor_refs": [], "source_refs": ["C93"]},
    )

    assert record["schema_id"] == "gwc.universal-run.run-state-record.v2"
    assert record["schema_version"] == 2
    assert verify_run_state_record(record) is True
    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/node-architect/universal-run/run-state-record.schema.json").read_text())
    jsonschema.validate(record, schema)


def test_universal_node_allocation_rejects_legacy_schema_without_digest_masking():
    from tools.node_architect.universal_run_kernel import UniversalRunKernelError
    from tools.node_architect.universal_run_topology import validate_node_allocation

    _, _, _, allocation = _make_v2_binding()
    legacy = dict(allocation)
    legacy.pop("content_digest")
    legacy["schema_id"] = "gwc.universal-run.node-allocation"
    legacy["schema_version"] = 1
    legacy["lifecycle_profile"] = {"id": "gwc.universal-run", "version": 1}

    try:
        validate_node_allocation(legacy)
    except UniversalRunKernelError as exc:
        assert exc.code == "NODE_ALLOCATION_SCHEMA_MISMATCH"
    else:
        raise AssertionError("legacy NodeAllocation schema was accepted by the V2 validator")


def test_fresh_process_cli_boots_v2_and_never_imports_legacy(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    _, plan, state, allocation = _make_v2_binding()
    provider = tmp_path / "fresh_provider.py"
    provider.write_text(
        "class Provider:\n"
        "    name = 'fresh-v2-provider'\n"
        "    def run(self, request):\n"
        "        return {'outcome': 'PASS', 'observations': ['fresh-process-v2-boot']}\n"
        "def build(): return Provider()\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "fresh_manifest.json"
    manifest.write_text(json.dumps({
        "provider_name": "fresh-v2-provider",
        "event": {"event_id": "fresh-process-v2-event"},
        "universal_run": {
            "runtime_plan": plan,
            "run_state": state,
            "node_allocation": allocation,
            "evidence_root": str(tmp_path / "fresh_receipts"),
        },
    }), encoding="utf-8")
    args = ["--manifest", str(manifest), "--provider-factory", f"{provider}:build"]
    forbidden = [
        "tools.node_architect.semantic_agent_runtime",
        "tools.node_architect.agent_runtime_entrypoint",
        "tools.node_architect.live_runtime_bridge",
        "tools.node_architect.universal_run_legacy",
        "tools.node_architect.approval_token_generation",
        "tools.node_architect.slack_task_controller",
    ]
    runner = (
        f"import sys; sys.path.insert(0, {str(root)!r}); "
        "from tools.node_architect.agent_runtime_cli import main; "
        f"code = main({args!r}); "
        f"assert not any(name in sys.modules for name in {forbidden!r}), "
        "'fresh V2 process imported a quarantined legacy module'; "
        "raise SystemExit(code)"
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-c", runner], cwd=root, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr + result.stdout
    output = json.loads(result.stdout.splitlines()[-1])
    assert output["status"] == "UNIVERSAL_RUN_NODE_COMPLETE"
    assert output["runtime_family"] == "UNIVERSAL_V2"
    assert output["runtime_protocol"] == "gwc.universal.controller/v2"
    assert output["authority_granted"] is False
    assert output["executed_effects"] == []


def test_controller_owned_g4_rejects_extra_control_fields_in_gate_evidence():
    import pytest
    from tools.node_architect.universal_run_controller import UniversalController, UniversalControllerError

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller.assign_current_action()
    with pytest.raises(UniversalControllerError, match="CONTROLLER_LOCAL_GATE_EVIDENCE_NONCANONICAL"):
        controller.complete_controller_owned_gate(evidence={
            "integration_outcome": "IN_PLACE",
            "candidate_sha": plan["source_binding"]["pre_head_sha"],
            "assignment_digest": "sha256:" + "a" * 64,
        })


def test_controller_local_idempotency_key_binds_canonical_evidence_digest():
    import hashlib
    import json
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller.assign_current_action()
    evidence = {"integration_outcome": "IN_PLACE"}
    decision = controller.complete_controller_owned_gate(evidence=evidence)
    receipt = decision["controller_local_completion_receipt"]
    evidence_digest = "sha256:" + hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    identity = {
        "run_id": state["run_id"],
        "runtime_plan_digest": plan["digest"],
        "candidate_sha": plan["source_binding"]["pre_head_sha"],
        "gate": "UR.G4",
        "sequence": state["sequence"],
        "action": "complete_controller_owned_gate",
        "actor": "CONTROLLER",
        "evidence_digest": evidence_digest,
        "completion_metadata_digest": "sha256:" + hashlib.sha256(b"{}").hexdigest(),
    }
    expected = "sha256:" + hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert receipt["idempotency_key"] == expected


def test_controller_owned_g4_keeps_provenance_outside_gate_evidence():
    from tools.node_architect.universal_run_controller import UniversalController

    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller.assign_current_action()
    decision = controller.complete_controller_owned_gate(
        evidence={"integration_outcome": "IN_PLACE"},
        completion_metadata={
            "controller_seq": 106,
            "controller_body_sha256": "a" * 64,
            "assignment_digest": "sha256:" + "b" * 64,
        },
    )
    local_receipt = decision["controller_local_completion_receipt"]
    assert decision["successor_run_state"]["gate_evidence"] == {"integration_outcome": "IN_PLACE"}
    assert local_receipt["evidence"] == {"integration_outcome": "IN_PLACE"}
    assert local_receipt["completion_metadata"]["controller_seq"] == 106
    assert local_receipt["evidence_digest"] != local_receipt["completion_metadata_digest"]
    assert decision["authority_granted"] is False and decision["executed_effects"] == []


def _make_recovery_replan_inputs():
    import copy
    import hashlib
    import json

    from tools.node_architect.q0_qualification import q0_qualification_profile
    from tools.node_architect.universal_run_controller import _digest
    from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile

    profile, plan, _state, allocation = _make_v2_binding()
    plan = copy.deepcopy(plan)
    plan["revision"] = 7
    plan["source_binding"]["pre_head_sha"] = "2508dbd9877141e67816db5480300ed36c1184e5"
    plan.pop("digest", None)
    plan["digest"] = _digest(plan, "digest")
    allocation = copy.deepcopy(allocation)
    receipt = {
        "schema_id": "gwc.universal-run.replan-control-receipt.v2",
        "schema_version": 2,
        "receipt_type": "IMMUTABLE_INTEGRITY_RECOVERY_REPLAN",
        "recovery_strategy": "IMMUTABLE_INTEGRITY_RECOVERY_REPLAN",
        "run_id": plan["run_id"],
        "to_plan": {"digest": plan["digest"], "revision": 7},
        "new_candidate_sha": plan["source_binding"]["pre_head_sha"],
        "activation_status": "NOT_ACTIVATED",
        "authority_granted": False,
        "executed_effects": [],
    }
    receipt["receipt_digest"] = _digest(receipt, "receipt_digest")
    invalidation = {
        "schema_id": "gwc.universal-run.invalidated-evidence-manifest.v2",
        "schema_version": 2,
        "run_id": plan["run_id"],
        "to_plan": {"digest": plan["digest"], "candidate_sha": plan["source_binding"]["pre_head_sha"], "revision": 7},
        "invalidated_for_r7_qualification_only": [{"evidence_key": "R6_G5_READINESS_PROJECTION", "gate": "UR.G5"}],
    }
    invalidation["manifest_digest"] = _digest(invalidation, "manifest_digest")
    incident = {
        "run_id": plan["run_id"],
        "sequence": 14,
        "active_gate": "UR.G5",
        "checkpoint_file_sha256": "4e7988c188c3eb7fc7705610ada702f2be909addd5cb872c4d37b359e73221bb",
    }
    provenance = {"activation_id": "test-recovery-activation", "source": "typed-controller-command"}
    return profile, plan, allocation, receipt, invalidation, incident, provenance


def test_recovery_replan_cursor_binds_exact_r7_candidate_and_starts_ur_g2():
    from tools.node_architect.universal_run_controller import create_recovery_replan_cursor_state

    profile, plan, allocation, receipt, invalidation, incident, provenance = _make_recovery_replan_inputs()
    state = create_recovery_replan_cursor_state(
        runtime_plan=plan,
        node_allocation=allocation,
        recovery_replan_receipt=receipt,
        stale_evidence_invalidation_record=invalidation,
        incident_checkpoint_identity=incident,
        requested_restart_gate="UR.G2",
        recovery_provenance=provenance,
    )

    assert state["run_id"] == plan["run_id"]
    assert state["runtime_plan_digest"] == plan["digest"]
    assert state["execution_refs"]["candidate_sha"] == plan["source_binding"]["pre_head_sha"]
    assert state["sequence"] == 15
    assert state["active_gate"] == "UR.G2"
    assert state["next_owner"] == "EXECUTOR"
    assert state["typed_next"] == "EXECUTE_Q0_R7_UR_G2_REPLAY_PROBE"


def test_recovery_replan_cursor_sequence_is_incident_plus_one():
    from tools.node_architect.universal_run_controller import create_recovery_replan_cursor_state

    _profile, plan, allocation, receipt, invalidation, incident, provenance = _make_recovery_replan_inputs()
    state = create_recovery_replan_cursor_state(
        runtime_plan=plan, node_allocation=allocation, recovery_replan_receipt=receipt,
        stale_evidence_invalidation_record=invalidation, incident_checkpoint_identity=incident,
        requested_restart_gate="UR.G2", recovery_provenance=provenance,
    )
    assert state["sequence"] == incident["sequence"] + 1 == 15


def test_recovery_replan_cursor_does_not_trust_corrupt_seq14_state_digest():
    from tools.node_architect.universal_run_controller import create_recovery_replan_cursor_state

    _profile, plan, allocation, receipt, invalidation, incident, provenance = _make_recovery_replan_inputs()
    incident.update({"stored_state_digest": "sha256:" + "9" * 64, "recomputed_state_digest": "sha256:" + "8" * 64})
    state = create_recovery_replan_cursor_state(
        runtime_plan=plan, node_allocation=allocation, recovery_replan_receipt=receipt,
        stale_evidence_invalidation_record=invalidation, incident_checkpoint_identity=incident,
        requested_restart_gate="UR.G2", recovery_provenance=provenance,
    )
    assert state.get("predecessor_state_digest") is None
    assert state["recovery_provenance"]["incident_checkpoint_file_sha256"] == incident["checkpoint_file_sha256"]


def test_recovery_replan_cursor_drops_stale_r6_gate_and_receipt_evidence():
    from tools.node_architect.universal_run_controller import create_recovery_replan_cursor_state

    _profile, plan, allocation, receipt, invalidation, incident, provenance = _make_recovery_replan_inputs()
    state = create_recovery_replan_cursor_state(
        runtime_plan=plan, node_allocation=allocation, recovery_replan_receipt=receipt,
        stale_evidence_invalidation_record=invalidation, incident_checkpoint_identity=incident,
        requested_restart_gate="UR.G2", recovery_provenance=provenance,
    )
    assert state["gate_evidence"] == {}
    assert state["consumed_receipts"] == []


def test_recovery_replan_cursor_has_no_inherited_g5_or_effect_authority():
    from tools.node_architect.universal_run_controller import create_recovery_replan_cursor_state

    _profile, plan, allocation, receipt, invalidation, incident, provenance = _make_recovery_replan_inputs()
    state = create_recovery_replan_cursor_state(
        runtime_plan=plan, node_allocation=allocation, recovery_replan_receipt=receipt,
        stale_evidence_invalidation_record=invalidation, incident_checkpoint_identity=incident,
        requested_restart_gate="UR.G2", recovery_provenance=provenance,
    )
    assert state["authority_granted"] is False
    assert state["executed_effects"] == []
    assert state["evidence_gap"] == ["EXECUTION_RECEIPT"]
    assert not any("g5" in key.lower() or "certif" in key.lower() for key in state)


def test_recovery_replan_cursor_validates_with_universal_controller():
    from tools.node_architect.universal_run_controller import UniversalController, create_recovery_replan_cursor_state
    from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile

    _profile, plan, allocation, receipt, invalidation, incident, provenance = _make_recovery_replan_inputs()
    state = create_recovery_replan_cursor_state(
        runtime_plan=plan, node_allocation=allocation, recovery_replan_receipt=receipt,
        stale_evidence_invalidation_record=invalidation, incident_checkpoint_identity=incident,
        requested_restart_gate="UR.G2", recovery_provenance=provenance,
    )
    controller = UniversalController(
        profile=load_universal_v2_default_profile(), runtime_plan=plan,
        run_state=state, node_allocation=allocation,
    )
    assignment = controller.assign_current_action()
    assert assignment["actor"] == "EXECUTOR"
    assert assignment["gate"] == "UR.G2"
    assert state["typed_next"] == "EXECUTE_Q0_R7_UR_G2_REPLAY_PROBE"
