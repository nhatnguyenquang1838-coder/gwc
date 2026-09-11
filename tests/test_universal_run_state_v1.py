from __future__ import annotations

import copy
import importlib
import json
from typing import Any
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from tools.node_architect.universal_run_kernel import GATES, UniversalRunKernelError

MODULE_NAME = "tools.node_architect.universal_run_state"
PROFILE = {"id": "gwc.universal-run", "version": 1}
CREATED = {"kind": "agent", "id": "DWA"}
TS = "2026-09-10T08:00:00+07:00"


def _api():
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


def _gates(active: str = "G0") -> dict[str, str]:
    return {gate: ("ACTIVE" if gate == active else "NOT_STARTED") for gate in GATES}


def _valid(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "record_id": "RS-1",
        "run_id": "RUN-R1",
        "lifecycle_profile": PROFILE,
        "run_manifest_ref": "RM-R1",
        "run_manifest_digest": "a" * 64,
        "state_revision": 1,
        "predecessor_state_ref": None,
        "predecessor_state_digest": None,
        "sequence": 0,
        "active_gate": "G0",
        "gate_states": _gates(),
        "terminal_state": "OPEN",
        "execution_refs": {
            "runtime_plan_ref": None,
            "runtime_plan_digest": None,
            "cursor_ref": None,
        },
        "future_contract_refs": {
            "target_contract_ref": None,
            "closure_receipt_ref": None,
            "handoff_receipt_ref": None,
        },
        "created_at": TS,
        "created_by": CREATED,
        "provenance": {"predecessor_refs": [], "source_refs": ["g1:SCRUM-668"]},
    }
    value.update(overrides)
    return value


def _create(**overrides: Any) -> dict[str, Any]:
    return _api().create_run_state_record(**_valid(**overrides))


def _successor(previous: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    api = _api()
    fn = getattr(api, "make_successor_state_record", None) or getattr(api, "make_successor_run_state_record", None)
    if fn is None:
        pytest.fail("R1 RED contract missing symbols: make_successor_state_record")
    changes = {"active_gate": "G1", "gate_states": _gates("G1"), "sequence": 1, "state_revision": 2}
    changes.update(overrides)
    return fn(previous, record_id="RS-2", created_at=TS, created_by=CREATED, changes=changes)


def test_run_state_requires_universal_profile_v1():
    with pytest.raises(UniversalRunKernelError):
        _create(lifecycle_profile={"id": "legacy", "version": 3})


def test_run_state_requires_exact_seven_gate_positions():
    gates = _gates()
    gates.pop("G6")
    with pytest.raises(UniversalRunKernelError):
        _create(gate_states=gates)


def test_run_state_run_id_cannot_change_in_successor():
    previous = _create()
    with pytest.raises(UniversalRunKernelError):
        _successor(previous, run_id="RUN-OTHER")


def test_run_state_manifest_run_id_must_match():
    with pytest.raises(UniversalRunKernelError):
        _create(run_manifest_ref="RM-OTHER", run_manifest_run_id="RUN-OTHER")


def test_run_state_genesis_cannot_have_predecessor_refs():
    with pytest.raises(UniversalRunKernelError):
        _create(
            state_revision=1,
            predecessor_state_ref="RS-0",
            predecessor_state_digest="a" * 64,
        )


def test_run_state_schema_rejects_premature_accepted_terminal_state():
    record = _create()
    record["terminal_state"] = "ACCEPTED"
    schema_path = Path(__file__).parents[1] / "schemas/node-architect/universal-run/run-state-record.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert Draft7Validator(schema).is_valid(record) is False


def test_child_run_state_requires_manifest_run_identity():
    with pytest.raises(UniversalRunKernelError):
        _create(
            run_id="CHILD-R1",
            parent_run_ref="RM-R1",
            child_run_ref="CHILD-R1",
        )


def test_run_state_schema_rejects_child_without_manifest_run_identity():
    record = _create()
    record.update({"parent_run_ref": "RM-R1", "child_run_ref": "RUN-R1"})
    schema_path = Path(__file__).parents[1] / "schemas/node-architect/universal-run/run-state-record.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert Draft7Validator(schema).is_valid(record) is False


def test_child_run_state_cannot_bind_wrong_parent_manifest():
    with pytest.raises(UniversalRunKernelError):
        _create(run_id="CHILD-R1", run_manifest_ref="ROOT-MANIFEST", parent_run_ref="OTHER-ROOT")


def test_state_successor_requires_predecessor_digest():
    previous = _create()
    with pytest.raises(UniversalRunKernelError):
        _successor(previous, predecessor_state_digest=None)


def test_state_successor_sequence_must_be_monotonic():
    previous = _create()
    with pytest.raises(UniversalRunKernelError):
        _successor(previous, sequence=0, state_revision=2)


def test_state_record_tamper_breaks_digest():
    record = _create()
    tampered = copy.deepcopy(record)
    tampered["sequence"] = 99
    assert _api().verify_run_state_record(record) is True
    assert _api().verify_run_state_record(tampered) is False


def test_logical_store_first_write_requires_revision_one():
    api = _api()
    store = api.LogicalRunStateStore()
    with pytest.raises(UniversalRunKernelError):
        store.put(_create(state_revision=2), expected_predecessor_digest=None)


def test_logical_store_rejected_first_write_has_no_binding_side_effect():
    api = _api()
    store = api.LogicalRunStateStore()
    first = _create(run_id="RUN-BAD")
    invalid_first_write = _successor(first)
    with pytest.raises(UniversalRunKernelError):
        store.put(invalid_first_write, expected_predecessor_digest=first["content_digest"]["value"])
    accepted = _create(run_id="RUN-GOOD")
    stored = store.put(accepted, expected_predecessor_digest=None)
    assert stored["run_id"] == "RUN-GOOD"


def test_logical_store_rejects_stale_expected_digest():
    api = _api()
    store = api.LogicalRunStateStore()
    first = _create()
    store.put(first, expected_predecessor_digest=None)
    with pytest.raises(UniversalRunKernelError):
        store.put(_successor(first), expected_predecessor_digest="b" * 64)


def test_logical_store_rejects_cross_run_write():
    api = _api()
    store = api.LogicalRunStateStore()
    store.put(_create(), expected_predecessor_digest=None)
    with pytest.raises(UniversalRunKernelError):
        store.put(_create(record_id="RS-OTHER", run_id="RUN-OTHER"), expected_predecessor_digest=None)


def test_logical_store_preserves_previous_state():
    api = _api()
    store = api.LogicalRunStateStore()
    first = _create()
    second = _successor(first)
    store.put(first, expected_predecessor_digest=None)
    store.put(second, expected_predecessor_digest=first["content_digest"]["value"])
    assert store.get("RUN-R1")["record_id"] == "RS-2"
    assert store.history("RUN-R1")[0]["record_id"] == "RS-1"


def test_logical_store_does_not_execute_external_effect():
    api = _api()
    store = api.LogicalRunStateStore()
    record = _create()
    store.put(record, expected_predecessor_digest=None)
    assert getattr(store, "executed_effects", []) == []
