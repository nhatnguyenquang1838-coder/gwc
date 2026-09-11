from __future__ import annotations

import copy
import importlib
from typing import Any

import pytest

from tools.node_architect.universal_run_kernel import GATES, UniversalRunKernelError, verify_record_digest
from tools.node_architect.universal_run_topology import (
    create_node_allocation,
    create_run_manifest_revision,
    materialize_child_run,
)

MODULE_NAME = "tools.node_architect.universal_run_state"
CREATED = {"kind": "agent", "id": "DWA"}
TS = "2026-09-10T08:00:00+07:00"


def _state_api():
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:
        if exc.name == MODULE_NAME:
            pytest.fail("R1 RED contract missing: universal_run_state.py is not materialized")
        pytest.fail(f"R1 RED contract unavailable: {type(exc).__name__}: {exc}")
    required = ("create_run_state_record", "verify_run_state_record")
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        pytest.fail("R1 RED contract missing symbols: " + ", ".join(missing))
    return module


def _root_manifest():
    return create_run_manifest_revision(
        record_id="RM-ROOT",
        run_id="RUN-ROOT",
        revision=1,
        run_kind="ROOT",
        created_at=TS,
        created_by=CREATED,
    )


def _work_allocation():
    return create_node_allocation(
        record_id="NA-R1",
        run_id="RUN-ROOT",
        node_allocation_id="NODE-R1",
        kind="WORK",
        requirement="REQUIRED",
        created_at=TS,
        created_by=CREATED,
    )


def _child_receipt():
    return materialize_child_run(
        record_id="CM-R1",
        parent_run_id="RUN-ROOT",
        child_run_id="RUN-R1",
        node_allocation=_work_allocation(),
        created_at=TS,
        created_by=CREATED,
    )


def _gates(active: str = "G0") -> dict[str, str]:
    return {gate: ("ACTIVE" if gate == active else "NOT_STARTED") for gate in GATES}


def _state_kwargs(**overrides: Any) -> dict[str, Any]:
    manifest = _root_manifest()
    value: dict[str, Any] = {
        "record_id": "RS-ROOT",
        "run_id": "RUN-ROOT",
        "lifecycle_profile": {"id": "gwc.universal-run", "version": 1},
        "run_manifest_ref": manifest["record_id"],
        "run_manifest_digest": manifest["content_digest"]["value"],
        "state_revision": 1,
        "predecessor_state_ref": None,
        "predecessor_state_digest": None,
        "sequence": 0,
        "active_gate": "G0",
        "gate_states": _gates(),
        "terminal_state": "OPEN",
        "execution_refs": {
            "runtime_plan_ref": "dw:runtime-plan/RP-1",
            "runtime_plan_digest": "c" * 64,
            "cursor_ref": "dw:cursor/RUN-ROOT",
        },
        "future_contract_refs": {
            "target_contract_ref": None,
            "closure_receipt_ref": None,
            "handoff_receipt_ref": None,
        },
        "created_at": TS,
        "created_by": CREATED,
        "provenance": {"predecessor_refs": [], "source_refs": ["dw:provenance"]},
    }
    value.update(overrides)
    return value


def _create(**overrides: Any) -> dict[str, Any]:
    return _state_api().create_run_state_record(**_state_kwargs(**overrides))


def test_e3_manifest_and_child_receipt_are_bound_as_immutable_refs():
    manifest = _root_manifest()
    receipt = _child_receipt()
    assert verify_record_digest(manifest)
    assert verify_record_digest(receipt)
    state = _create(run_manifest_ref=manifest["record_id"], run_manifest_digest=manifest["content_digest"]["value"])
    assert state["run_manifest_ref"] == manifest["record_id"]
    assert state["lifecycle_profile"] == {"id": "gwc.universal-run", "version": 1}


def test_child_run_state_cannot_bind_wrong_parent_manifest():
    receipt = _child_receipt()
    with pytest.raises(UniversalRunKernelError):
        _create(
            run_id=receipt["child_run_ref"],
            run_manifest_ref=receipt["parent_run_ref"],
            parent_run_ref="RUN-OTHER",
            child_run_ref=receipt["child_run_ref"],
        )


def test_dw_runtime_plan_binding_is_provenance_not_lifecycle_authority():
    state = _create()
    assert state["lifecycle_profile"] == {"id": "gwc.universal-run", "version": 1}
    assert state["execution_refs"]["runtime_plan_ref"] == "dw:runtime-plan/RP-1"
    assert state.get("authority_granted", False) is False


@pytest.mark.parametrize("legacy_gate", ["G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION_DATA"])
def test_legacy_gate_number_only_conversion_is_rejected(legacy_gate: str):
    with pytest.raises(UniversalRunKernelError):
        _create(lifecycle_profile=legacy_gate)


def test_future_handoff_ref_presence_does_not_accept_run():
    with pytest.raises(UniversalRunKernelError):
        _create(
            future_contract_refs={
                "target_contract_ref": "future:target/1",
                "closure_receipt_ref": "future:closure/1",
                "handoff_receipt_ref": "future:handoff/1",
            },
            terminal_state="ACCEPTED",
        )


def test_future_target_contract_ref_presence_does_not_pass_g4():
    with pytest.raises(UniversalRunKernelError):
        _create(
            active_gate="G4",
            gate_states=_gates("G4"),
            future_contract_refs={"target_contract_ref": "future:target/1"},
            terminal_state="ACCEPTED",
        )


def test_interop_record_tamper_is_detected_without_mutating_e3():
    manifest = _root_manifest()
    before = copy.deepcopy(manifest)
    state = _create()
    tampered = copy.deepcopy(state)
    tampered["run_manifest_digest"] = "d" * 64
    assert _state_api().verify_run_state_record(state) is True
    assert _state_api().verify_run_state_record(tampered) is False
    assert manifest == before
