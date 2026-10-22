from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.node_architect import q0_qualification
from tools.node_architect.q0_native_g1_admission import (
    Q0NativeG1AdmissionError,
    build_native_g1_plan_receipt,
    materialize_native_g1_genesis,
    validate_native_g1_plan_receipt,
)


def _bindings():
    run_id = "cmd163-test-run"
    runtime_plan_digest = "sha256:" + "a" * 64
    candidate_sha = "b" * 40
    allocation = {"node_allocation_id": "alloc-1", "content_digest": {"value": "sha256:" + "c" * 64}}
    plan = {
        "digest": runtime_plan_digest,
        "source_binding": {"pre_head_sha": candidate_sha},
        "dag": {"nodes": [{"id": f"W{i}", "predecessors": [] if i == 1 else [f"W{i-1}"]} for i in range(1, 7)]},
        "node_allocations": [allocation["node_allocation_id"]],
    }
    kwargs = dict(run_id=run_id, runtime_plan_digest=runtime_plan_digest,
                  candidate_sha=candidate_sha, node_allocation=allocation,
                  runtime_plan=plan, source_head=candidate_sha)
    return kwargs


def _valid():
    return build_native_g1_plan_receipt(**_bindings())


def _reseal(receipt):
    body = {k: v for k, v in receipt.items() if k != "receipt_digest"}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {**body, "receipt_digest": "sha256:" + hashlib.sha256(raw).hexdigest()}


def _assert_code(code, receipt=None, **overrides):
    kwargs = _bindings()
    kwargs.update(overrides)
    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        validate_native_g1_plan_receipt(_valid() if receipt is None else receipt, **kwargs)
    assert exc.value.code == code


def test_ur_g1_rejects_truthy_raw_plan_receipt():
    with pytest.raises(q0_qualification.Q0QualificationError) as exc:
        q0_qualification.complete_q0_gate(gate="UR.G1", evidence={"PLAN_RECEIPT": "g1"})
    assert exc.value.code == "PLAN_RECEIPT_INVALID"


def test_ur_g1_requires_real_plan_and_allocation_bindings():
    with pytest.raises(q0_qualification.Q0QualificationError) as exc:
        q0_qualification.complete_q0_gate(
            gate="UR.G1", evidence={"PLAN_RECEIPT": _valid()}
        )
    assert exc.value.code == "PLAN_RECEIPT_BINDING_REQUIRED"


def test_canonical_receipt_is_sealed_and_non_authorizing():
    receipt = _valid()
    verdict = validate_native_g1_plan_receipt(receipt, **_bindings())
    assert verdict["valid"] is True
    assert verdict["authority_granted"] is False
    assert verdict["effect_authority_granted"] is False
    assert verdict["consumed"] is False
    assert q0_qualification.complete_q0_gate(
        gate="UR.G1", evidence={"PLAN_RECEIPT": receipt}, **_bindings()
    )["gate_state"] == "PASSED"


def test_forged_seal_fails_closed():
    receipt = _valid()
    receipt["receipt_digest"] = "sha256:" + "f" * 64
    _assert_code("RECEIPT_SEAL_INVALID", receipt)


def test_stale_source_sha_fails_closed():
    _assert_code("SOURCE_SHA_MISMATCH", source_head="d" * 40)


def test_wrong_run_id_fails_closed():
    _assert_code("RUN_ID_MISMATCH", run_id="another-run")


def test_wrong_type_and_schema_fail_closed():
    _assert_code("RECEIPT_TYPE_INVALID", "g1")
    _assert_code("RECEIPT_TYPE_INVALID", ["g1"])
    receipt = _valid()
    receipt["schema_id"] = "unknown"
    _assert_code("RECEIPT_SCHEMA_INVALID", _reseal(receipt))


def test_allocation_id_and_digest_must_match():
    allocation = copy.deepcopy(_bindings()["node_allocation"])
    allocation["node_allocation_id"] = "alloc-other"
    _assert_code("NODE_ALLOCATION_MISMATCH", node_allocation=allocation)
    allocation = copy.deepcopy(_bindings()["node_allocation"])
    allocation["content_digest"]["value"] = "sha256:" + "d" * 64
    _assert_code("NODE_ALLOCATION_MISMATCH", node_allocation=allocation)


def test_reversed_dag_order_fails_closed():
    receipt = _valid()
    receipt["work_order"] = list(reversed(receipt["work_order"]))
    _assert_code("WORK_ORDER_INVALID", _reseal(receipt))
    kwargs = _bindings()
    kwargs["runtime_plan"]["dag"]["nodes"] = [
        {"id": f"W{i}", "predecessors": [f"W{i+1}"] if i < 6 else []}
        for i in range(1, 7)
    ]
    _assert_code("WORK_ORDER_INVALID", **kwargs)


def test_cyclic_dag_fails_closed():
    kwargs = _bindings()
    kwargs["runtime_plan"]["dag"]["nodes"][0]["predecessors"] = ["W6"]
    _assert_code("PLAN_DAG_INVALID", **kwargs)


def test_work_must_be_in_plan_dag_and_authority_must_stay_false():
    receipt = _valid()
    receipt["work_id"] = "W99"
    _assert_code("WORK_NOT_IN_PLAN_DAG", _reseal(receipt))
    receipt = _valid()
    receipt["authority_granted"] = True
    _assert_code("AUTHORITY_FIELDS_INVALID", _reseal(receipt))


def test_missing_plan_receipt_keeps_required_code():
    with pytest.raises(q0_qualification.Q0QualificationError) as exc:
        q0_qualification.complete_q0_gate(gate="UR.G1", evidence={})
    assert exc.value.code == "PLAN_RECEIPT_REQUIRED"


def test_extra_key_fails_closed():
    receipt = _valid()
    receipt["surprise"] = True
    _assert_code("RECEIPT_KEYS_INVALID", _reseal(receipt))


def test_missing_provenance_or_decision_reference_fails_closed():
    receipt = _valid()
    receipt["provenance_ref"] = ""
    _assert_code("PROVENANCE_REF_REQUIRED", _reseal(receipt))
    receipt = _valid()
    receipt["decision_ref"] = ""
    _assert_code("DECISION_REF_REQUIRED", _reseal(receipt))


def test_missing_mandatory_qualification_entry_fails_closed():
    receipt = _valid()
    receipt["qualification_entries"].pop(next(iter(receipt["qualification_entries"])))
    _assert_code("QUALIFICATION_ENTRIES_INCOMPLETE", _reseal(receipt))


def test_digest_mismatch_fails_closed():
    _assert_code("PLAN_DIGEST_MISMATCH", runtime_plan_digest="sha256:" + "f" * 64)


def test_raw_string_and_wrong_type_fail_closed():
    _assert_code("RECEIPT_TYPE_INVALID", "g1")
    _assert_code("RECEIPT_TYPE_INVALID", ["g1"])


def test_self_sealed_receipt_cannot_bind_itself_to_real_plan_or_allocation(tmp_path):
    bindings = _bindings()
    forged = build_native_g1_plan_receipt(**bindings)
    forged["runtime_plan_digest"] = "sha256:" + "d" * 64
    forged["node_allocation_digest"] = "sha256:" + "e" * 64
    forged = _reseal(forged)

    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        validate_native_g1_plan_receipt(forged, **bindings)
    assert exc.value.code in {"PLAN_DIGEST_MISMATCH", "NODE_ALLOCATION_MISMATCH"}

    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        materialize_native_g1_genesis(
            forged, worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
            runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
        )
    assert exc.value.code in {"PLAN_DIGEST_MISMATCH", "NODE_ALLOCATION_MISMATCH"}


def test_genesis_materializer_requires_explicit_plan_binding(tmp_path):
    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        materialize_native_g1_genesis(
            _valid(), worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox"
        )
    assert exc.value.code == "PLAN_BINDING_REQUIRED"


def test_genesis_materialization_is_digest_idempotent_and_sandbox_only(tmp_path):
    receipt = _valid()
    bindings = _bindings()
    first = materialize_native_g1_genesis(
        receipt, worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
        runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
    )
    second = materialize_native_g1_genesis(
        receipt, worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
        runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
    )
    assert first == second
    artifact = Path(first["ref"])
    assert artifact.is_relative_to(tmp_path / "sandbox")
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == first["digest"].removeprefix("sha256:")
    assert artifact.read_text().count("native-g1-genesis") == 1


def test_genesis_refuses_path_outside_sandbox(tmp_path):
    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        materialize_native_g1_genesis(
            _valid(), worktree_root=tmp_path,
            sandbox_dir=tmp_path / "sandbox/../escape", **{
                "runtime_plan": _bindings()["runtime_plan"],
                "node_allocation": _bindings()["node_allocation"],
            },
        )
    assert exc.value.code == "SANDBOX_PATH_INVALID"


def test_genesis_materializer_rejects_conflicting_existing_content(tmp_path):
    receipt = _valid()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    ref = sandbox / f"native-g1-genesis-{receipt['receipt_digest'].split(':', 1)[1]}.json"
    ref.write_text("conflicting artifact")
    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        materialize_native_g1_genesis(
            receipt, worktree_root=tmp_path, sandbox_dir=sandbox, **{
                "runtime_plan": _bindings()["runtime_plan"],
                "node_allocation": _bindings()["node_allocation"],
            },
        )
    assert exc.value.code == "GENESIS_CONTENT_MISMATCH"


def test_historical_evidence_is_unchanged(tmp_path):
    root = Path(__file__).resolve().parents[1]
    historical = root / ".gwc/tasks/SCRUM-781/evidence/native108-jira-reader-binding-v1.json"
    before = hashlib.sha256(historical.read_bytes()).hexdigest()
    bindings = _bindings()
    materialize_native_g1_genesis(
        _valid(), worktree_root=root, sandbox_dir=tmp_path / "sandbox",
        runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
    )
    assert hashlib.sha256(historical.read_bytes()).hexdigest() == before
