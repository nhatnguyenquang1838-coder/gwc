from tools.node_architect.observation_event import (
    build_controller_decision_observation_event,
    canonical_digest,
)
from tools.node_architect import observation_publisher


def _decision():
    successor = {
        "schema_id": "gwc.universal-run.run-state.v2",
        "schema_version": 2,
        "run_id": "R2",
        "sequence": 2,
        "active_gate": "UR.G1",
        "typed_next": "CONTINUE_UNIVERSAL_LANE_REMEDIATION",
        "next_owner": "CONTROLLER",
        "runtime_epoch": "UNIVERSAL_V2_DEVELOPMENT",
    }
    successor["state_digest"] = canonical_digest(successor)
    transition = {
        "schema_id": "gwc.universal-run.controller-transition-receipt.v2",
        "schema_version": 2,
        "run_id": "R2",
        "runtime_plan_digest": "sha256:" + "1" * 64,
        "candidate_sha": "2" * 40,
        "from_gate": "UR.G0",
        "to_gate": "UR.G1",
        "transition_ref": "R2:transition:1-2",
        "pre_state": {"sequence": 1, "state_digest": "sha256:" + "3" * 64},
        "consumed_receipt_digest": "sha256:" + "4" * 64,
        "idempotency_key": "evt:1",
        "post_state": {"sequence": 2, "state_digest": successor["state_digest"]},
        "kernel_completion_receipt": {},
        "kernel_transition_receipt": {},
        "authority_granted": False,
        "executed_effects": [],
    }
    transition["transition_digest"] = canonical_digest(transition)
    return {
        "schema_id": "gwc.universal-run.controller-decision.v2",
        "successor_run_state": successor,
        "transition_receipt": transition,
        "consumed_receipt_digest": transition["consumed_receipt_digest"],
        "gate_advanced": True,
        "idempotent_replay": False,
        "decision_subject": {"run_id": "R2"},
    }


def test_controller_decision_projection_is_source_bound():
    event = build_controller_decision_observation_event(
        _decision(),
        source_repository="nhatnguyenquang1838-coder/gwc",
        source_sha="2" * 40,
        runtime_epoch="UNIVERSAL_V2_DEVELOPMENT",
        emitted_at="2026-11-03T08:30:00Z",
        node_id="q0.qualification-campaign",
    )
    assert event["event_id"] == "R2:transition:1-2"
    assert event["sequence"] == 2
    assert event["runtime"]["gate"] == "UR.G1"
    assert event["runtime"]["typed_next"] == "CONTINUE_UNIVERSAL_LANE_REMEDIATION"
    assert event["payload"]["time_basis"] == "OBSERVATION_EVENT_EMITTED_AT"
    assert event["source_digest"] == _decision()["successor_run_state"]["state_digest"]
    assert event["authority_ref"] is None


def test_observer_is_disabled_without_runtime_config(monkeypatch):
    for name in (
        "GWC_DWO_OBSERVATION_ENDPOINT",
        "GWC_DWO_MACHINE_SECRET",
        "GWC_DWO_KEY_ID",
        "GWC_DWO_SOURCE_ID",
        "GWC_DWO_OUTBOX_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    result = observation_publisher.observe_controller_decision_from_env(
        decision=_decision(),
        runtime_plan={"source_binding": {"repository": "x/y", "pre_head_sha": "2" * 40}},
        runtime_epoch="UNIVERSAL_V2_DEVELOPMENT",
        node_id=None,
    )
    assert result["status"] == "DISABLED"
    assert result["authority_granted"] is False
    assert result["executed_effects"] == []


def test_projection_failure_never_owns_universal_cursor(monkeypatch, tmp_path):
    values = {
        "GWC_DWO_OBSERVATION_ENDPOINT": "https://dwo.invalid/ingest",
        "GWC_DWO_MACHINE_SECRET": "x" * 32,
        "GWC_DWO_KEY_ID": "test-key",
        "GWC_DWO_SOURCE_ID": "test-source",
        "GWC_DWO_OUTBOX_PATH": str(tmp_path / "outbox.sqlite"),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    def explode(**_kwargs):
        raise RuntimeError("receiver unavailable")

    monkeypatch.setattr(observation_publisher, "publish_controller_decision", explode)
    result = observation_publisher.observe_controller_decision_from_env(
        decision=_decision(),
        runtime_plan={"source_binding": {"repository": "x/y", "pre_head_sha": "2" * 40}},
        runtime_epoch="UNIVERSAL_V2_DEVELOPMENT",
        node_id=None,
    )
    assert result["status"] == "DEGRADED"
    assert result["reason_code"] == "DWO_OBSERVATION_PROJECTION_FAILED"
    assert result["authority_granted"] is False
    assert result["executed_effects"] == []



def test_restart_drainer_uses_runtime_config_without_authority(monkeypatch, tmp_path):
    from tools.node_architect import observation_publisher

    values = {
        "GWC_DWO_OBSERVATION_ENDPOINT": "https://dwo.example/ingest",
        "GWC_DWO_MACHINE_SECRET": "x" * 32,
        "GWC_DWO_KEY_ID": "dev-key",
        "GWC_DWO_SOURCE_ID": "gwc-main",
        "GWC_DWO_OUTBOX_PATH": str(tmp_path / "outbox.sqlite"),
        "GWC_DWO_WORKER_ID": "unit-worker",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    seen = {}
    monkeypatch.setattr(
        observation_publisher,
        "drain_observation_outbox",
        lambda **kwargs: seen.update(kwargs) or {"status": "DRAINED", "attempted": 1, "results": []},
    )
    result = observation_publisher.drain_observation_outbox_from_env(max_items=7)

    assert seen["worker_id"] == "unit-worker"
    assert seen["max_items"] == 7
    assert seen["source_id"] == "gwc-main"
    assert result["status"] == "DRAINED"
    assert result["authority_granted"] is False
    assert result["executed_effects"] == []
