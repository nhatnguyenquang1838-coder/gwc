from tools.node_architect.observation_event import build_observation_event, observation_event_digest
from tools.node_architect.universal_run_state import create_run_state_record


def _state():
    return create_run_state_record(
        record_id="R1:state:1", run_id="R1",
        lifecycle_profile={"id":"gwc.universal-run.v2","version":2},
        run_manifest_ref="manifest:R1", run_manifest_digest="a"*64,
        state_revision=1, predecessor_state_ref=None, predecessor_state_digest=None,
        sequence=0, active_gate="UR.G0",
        gate_states={"UR.G0":"ACTIVE","UR.G1":"NOT_STARTED","UR.G2":"NOT_STARTED","UR.G3":"NOT_STARTED","UR.G4":"NOT_STARTED","UR.G5":"NOT_STARTED","UR.G6":"NOT_STARTED"},
        terminal_state="OPEN",
        execution_refs={"runtime_plan_ref":"plan:R1","runtime_plan_digest":"b"*64,"cursor_ref":"cursor:R1"},
        future_contract_refs={"target_contract_ref":None,"closure_receipt_ref":None,"handoff_receipt_ref":None},
        created_at="2026-11-03T07:00:00Z",
        created_by={"type":"agent","id":"unit"},
        provenance={"predecessor_refs":[],"source_refs":["gwc://R1/state/1"]},
    )


def test_builds_native_v2_event_from_verified_state():
    event = build_observation_event(
        _state(), source_repository="nhatnguyenquang1838-coder/gwc",
        source_sha="1"*40, runtime_epoch="UNIVERSAL_V2_DEVELOPMENT",
    )
    assert event["schema_id"] == "gwc.observation-event/v2"
    assert event["event_id"] == "R1:state:1"
    assert event["occurred_at"] == "2026-11-03T07:00:00Z"
    assert event["runtime"]["gate"] == "UR.G0"
    assert event["runtime"]["state"] == "ACTIVE"
    assert event["authority_ref"] is None
    assert observation_event_digest(event).startswith("sha256:")


def test_rejects_noncanonical_source_record():
    import pytest
    broken = dict(_state())
    broken["created_at"] = ""
    with pytest.raises(ValueError):
        build_observation_event(
            broken, source_repository="nhatnguyenquang1838-coder/gwc",
            source_sha="1"*40, runtime_epoch="UNIVERSAL_V2_DEVELOPMENT",
        )
