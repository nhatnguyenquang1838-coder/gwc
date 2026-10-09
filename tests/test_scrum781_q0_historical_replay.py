"""Historical C91/E52 semantic replay is not the DWO login end-to-end certification."""
from tools.node_architect.universal_run_epoch import (
    resolve_runtime_epoch,replay_c91_incident,
)

def test_scrum781_fresh_boot_is_universal_v2_not_legacy():
    epoch=resolve_runtime_epoch(
        task_id="SCRUM-781",
        branch="fix/SCRUM-781-q0-fresh-20261010-r1",
    )
    assert epoch["runtime_epoch"]=="UNIVERSAL_V2_DEVELOPMENT"
    assert epoch["legacy_fallback"] is False

def test_c91_missing_legacy_artifacts_does_not_stop_native_controller():
    result=replay_c91_incident(
        runtime_epoch="UNIVERSAL_V2_DEVELOPMENT",
        legacy_g01_package_present=False,
        universal_native_state_valid=True,
    )
    assert result["needs_exact_hitl"] is False
    assert result["advance_beyond_old_failure"] is True
    assert result["first_state_beyond_failure"]=="UR.G1_TYPED_CONTROLLER_NEXT"
