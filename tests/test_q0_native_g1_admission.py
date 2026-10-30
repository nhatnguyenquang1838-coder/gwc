from __future__ import annotations
from contextlib import closing

import copy
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from tools.node_architect import q0_qualification
from tools.node_architect.q0_m1_m7_integration import prepare_successor_activation
from tools.node_architect.q0_native_g1_admission import build_live_activation_effect_envelope
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
        "run_id": run_id,
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


def _predecessor(tmp_path, *, run_id="cmd162-predecessor", context_digest="sha256:" + "d" * 64,
                 owner_session_id="session-predecessor", plan_content=b"predecessor plan"):
    plan_path = tmp_path / "predecessor-plan.json"
    plan_path.write_bytes(plan_content)
    checkpoint_path = tmp_path / "predecessor.sqlite3"
    with closing(sqlite3.connect(checkpoint_path)) as db:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS engineering_workflow (run TEXT PRIMARY KEY, context_digest TEXT, state TEXT)")
            db.execute("INSERT OR REPLACE INTO engineering_workflow VALUES (?, ?, ?)",
                       (run_id, context_digest, json.dumps({"executor": {"session_id": owner_session_id}})))
    return {"kind": "R3_CHECKPOINT", "run_id": run_id,
            "runtime_plan_ref": str(plan_path),
            "runtime_plan_digest": "sha256:" + hashlib.sha256(plan_content).hexdigest(),
            "checkpoint_ref": str(checkpoint_path), "context_digest": context_digest,
            "owner_session_id": owner_session_id, "source_head": "c" * 40}


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
    assert receipt["plan_coverage"] == {
        name: "PLANNED" for name in q0_qualification.MANDATORY_QUALIFICATION_ENTRIES
    }
    assert receipt["qualification_results"] == {}
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
    receipt["plan_coverage"].pop(next(iter(receipt["plan_coverage"])))
    _assert_code("PLAN_COVERAGE_INVALID", _reseal(receipt))


def test_qualification_coverage_is_planned_not_a_pass_claim():
    receipt = _valid()
    receipt["plan_coverage"][q0_qualification.MANDATORY_QUALIFICATION_ENTRIES[0]] = "PASS"
    _assert_code("PLAN_COVERAGE_INVALID", _reseal(receipt))


def test_qualification_result_pass_requires_evidence_reference():
    receipt = _valid()
    receipt["qualification_results"] = {
        q0_qualification.MANDATORY_QUALIFICATION_ENTRIES[0]: {"status": "PASS"}
    }
    _assert_code("QUALIFICATION_RESULT_INVALID", _reseal(receipt))


def test_ur_g1_does_not_report_qualification_pass_from_plan_coverage():
    result = q0_qualification.complete_q0_gate(
        gate="UR.G1", evidence={"PLAN_RECEIPT": _valid()}, **_bindings()
    )
    assert result["gate_state"] == "PASSED"
    assert result["qualification_status"] == "NOT_QUALIFIED"
    assert result["qualification_results"] == {}


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
            predecessor=_predecessor(tmp_path),
        )
    assert exc.value.code in {"PLAN_DIGEST_MISMATCH", "NODE_ALLOCATION_MISMATCH"}


def test_genesis_materializer_requires_explicit_plan_binding(tmp_path):
    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        materialize_native_g1_genesis(
            _valid(), worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox"
        )
    assert exc.value.code == "PLAN_BINDING_REQUIRED"


def test_transition_requires_explicit_predecessor_binding(tmp_path):
    bindings = _bindings()
    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        materialize_native_g1_genesis(
            _valid(), worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
            runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
        )
    assert exc.value.code == "PREDECESSOR_BINDING_REQUIRED"


@pytest.mark.parametrize("mutation,code", [
    ("self", "PREDECESSOR_SELF_REFERENCE"),
    ("stale_digest", "PLAN_DIGEST_MISMATCH"),
    ("missing_plan", "PREDECESSOR_PLAN_UNREADABLE"),
    ("missing_checkpoint", "PREDECESSOR_CHECKPOINT_UNBOUND"),
    ("context", "PREDECESSOR_CONTEXT_MISMATCH"),
    ("owner", "PREDECESSOR_OWNER_MISMATCH"),
])
def test_transition_rejects_unbound_or_invalid_predecessor(tmp_path, mutation, code):
    bindings = _bindings()
    predecessor = _predecessor(tmp_path)
    if mutation == "self":
        predecessor["run_id"] = bindings["run_id"]
    elif mutation == "stale_digest":
        predecessor["runtime_plan_digest"] = "sha256:" + "e" * 64
    elif mutation == "missing_plan":
        predecessor["runtime_plan_ref"] = str(tmp_path / "absent-plan.json")
    elif mutation == "missing_checkpoint":
        predecessor["checkpoint_ref"] = str(tmp_path / "absent.sqlite3")
    elif mutation == "context":
        predecessor["context_digest"] = "sha256:" + "f" * 64
    elif mutation == "owner":
        predecessor["owner_session_id"] = "wrong-session"
    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        materialize_native_g1_genesis(
            _valid(), worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
            runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
            predecessor=predecessor,
        )
    assert exc.value.code == code


def test_genesis_materialization_is_digest_idempotent_and_sandbox_only(tmp_path):
    receipt = _valid()
    bindings = _bindings()
    first = materialize_native_g1_genesis(
        receipt, worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
        runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
        predecessor=_predecessor(tmp_path),
    )
    second = materialize_native_g1_genesis(
        receipt, worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
        runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
        predecessor=_predecessor(tmp_path),
    )
    assert first["run_id"] == second["run_id"]
    assert first["state_digest"] == second["state_digest"]
    assert first["transition_receipt_digest"] == second["transition_receipt_digest"]
    assert first["db_ref"] == second["db_ref"]
    assert first["readback"] == second["readback"]
    artifact = Path(first["db_ref"])
    assert artifact.is_relative_to(tmp_path / "sandbox")
    assert artifact.is_file()
    assert first["readback"] == {"run_id": first["run_id"], "state_digest": first["state_digest"]}
    from tools.node_architect.q0_native_g1_admission import read_back_genesis
    assert read_back_genesis(first["db_ref"]) == first["readback"]
    import sqlite3
    with closing(sqlite3.connect(first["db_ref"])) as db:
        with db:
            assert db.execute("SELECT COUNT(*) FROM checkpoint_events").fetchone()[0] == 1
            payload = json.loads(db.execute("SELECT payload_json FROM checkpoint_events").fetchone()[0])
    assert payload["run_state"]["schema_id"] == "gwc.universal-run.run-state-record.v2"
    assert payload["run_state"]["run_id"] == first["run_id"]
    transition_path = Path(first["transition_receipt_ref"])
    transition = json.loads(transition_path.read_text())
    assert transition["predecessor"]["identity"] == "cmd162-predecessor"
    assert transition["successor"]["run_id"] == first["run_id"]
    assert transition["predecessor"]["digest"] == _predecessor(tmp_path)["runtime_plan_digest"]
    assert transition["successor"]["node_allocation_id"] == "alloc-1"
    assert transition["transition_digest"] == first["transition_receipt_digest"]


def test_genesis_materialization_leaves_predecessor_checkpoint_byte_identical(tmp_path):
    bindings = _bindings()
    predecessor = _predecessor(tmp_path)
    checkpoint_path = Path(predecessor["checkpoint_ref"])
    before = hashlib.sha256(checkpoint_path.read_bytes()).digest()

    materialize_native_g1_genesis(
        _valid(), worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
        runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
        predecessor=predecessor,
    )

    after = hashlib.sha256(checkpoint_path.read_bytes()).digest()
    assert after == before


def test_activation_prepare_requires_separate_authority(tmp_path):
    envelope = build_live_activation_effect_envelope(idempotency_key="prepare-test")
    with pytest.raises(ValueError, match="^LIVE_ACTIVATION_AUTHORITY_REQUIRED$"):
        prepare_successor_activation(envelope, authority=None)
    with pytest.raises(ValueError, match="^LIVE_ACTIVATION_AUTHORITY_REQUIRED$"):
        prepare_successor_activation(envelope, authority={"granted": True})


def test_activation_prepare_is_dry_run_even_with_valid_authority(tmp_path):
    envelope = build_live_activation_effect_envelope(idempotency_key="prepare-test")
    predecessor = _predecessor(tmp_path)
    checkpoint_path = Path(predecessor["checkpoint_ref"])
    checkpoint_before = hashlib.sha256(checkpoint_path.read_bytes()).digest()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    result = prepare_successor_activation(
        envelope,
        authority={"granted": True, "authority_kind": "SEPARATE_HUMAN_OR_CONTROLLER_GRANT",
                   "grant_ref": "grant:human-1"},
    )

    assert result == {
        "accepted": True, "executed": False,
        "effects": ["selector_write", "checkpoint_write", "cursor_advance"],
        "authority_ref": "grant:human-1",
        "next_step": "LIVE_ACTIVATION_EXECUTION_NOT_IMPLEMENTED",
    }
    assert hashlib.sha256(checkpoint_path.read_bytes()).digest() == checkpoint_before
    assert not list(sandbox.rglob("*selector*"))
    assert not list(sandbox.rglob("*cursor*"))


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
    bindings = _bindings()
    first = materialize_native_g1_genesis(
        receipt, worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
        runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
        predecessor=_predecessor(tmp_path),
    )
    Path(first["transition_receipt_ref"]).write_text("conflicting artifact")
    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        materialize_native_g1_genesis(
            receipt, worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
            runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
            predecessor=_predecessor(tmp_path),
        )
    assert exc.value.code == "GENESIS_CONTENT_MISMATCH"


def test_genesis_rejects_conflicting_input_for_existing_sandbox_database(tmp_path):
    bindings = _bindings()
    first = _valid()
    materialize_native_g1_genesis(
        first, worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
        runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
        predecessor=_predecessor(tmp_path),
    )
    conflict = build_native_g1_plan_receipt(
        **{**bindings, "provenance_ref": "evidence:changed"}
    )
    with pytest.raises(Q0NativeG1AdmissionError) as exc:
        materialize_native_g1_genesis(
            conflict, worktree_root=tmp_path, sandbox_dir=tmp_path / "sandbox",
            runtime_plan=bindings["runtime_plan"], node_allocation=bindings["node_allocation"],
            predecessor=_predecessor(tmp_path),
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
        predecessor=_predecessor(tmp_path),
    )
    assert hashlib.sha256(historical.read_bytes()).hexdigest() == before


def test_live_bridge_rejects_real_worktree_and_hermes_home_and_live_mode(tmp_path, monkeypatch):
    from tools.node_architect.q0_m1_m7_integration import apply_live_activation_isolated
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="^LIVE_ACTIVATION_LIVE_TARGET_FORBIDDEN$"):
        apply_live_activation_isolated(grant=None, predecessor={}, runtime_plan={}, node_allocation={},
                                       branch="branch", head="head", isolated_root=root,
                                       successor_plan_ref="core/node-architect/q0-successor-test.json")
    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    with pytest.raises(ValueError, match="^LIVE_ACTIVATION_LIVE_TARGET_FORBIDDEN$"):
        apply_live_activation_isolated(grant=None, predecessor={}, runtime_plan={}, node_allocation={},
                                       branch="branch", head="head", isolated_root=hermes_home / "child",
                                       successor_plan_ref="core/node-architect/q0-successor-test.json")
    with pytest.raises(ValueError, match="^LIVE_ACTIVATION_LIVE_MODE_FORBIDDEN$"):
        apply_live_activation_isolated(grant=None, predecessor={}, runtime_plan={}, node_allocation={},
                                       branch="branch", head="head", isolated_root=tmp_path,
                                       successor_plan_ref="core/node-architect/q0-successor-test.json", mode="LIVE")


def test_live_bridge_requires_typed_grant_without_writes(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import apply_live_activation_isolated
    root = tmp_path / "isolated"
    with pytest.raises(ValueError, match="^LIVE_ACTIVATION_AUTHORITY_REQUIRED$"):
        apply_live_activation_isolated(grant=None, predecessor={}, runtime_plan={}, node_allocation={},
                                       branch="fix/test", head="b" * 40, isolated_root=root,
                                       successor_plan_ref="core/node-architect/q0-successor-test.json")
    assert not root.exists()


def test_live_bridge_rejects_expired_scope_and_binding_grants(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import apply_live_activation_isolated
    grant, predecessor, plan, allocation, _ = _activation_fixture(tmp_path)
    kwargs = dict(predecessor=predecessor, runtime_plan=plan, node_allocation=allocation,
                  branch="fix/test", head="b" * 40, isolated_root=tmp_path / "target",
                  successor_plan_ref="core/node-architect/q0-successor-test.json")
    for changes, code in [({"expires_at":"2000-01-01T00:00:00Z"}, "GRANT_EXPIRED"),
                          ({"scope":[]}, "GRANT_SCOPE_INVALID"),
                          ({"bindings":{**grant["bindings"], "head":"wrong"}}, "GRANT_BINDING_MISMATCH")]:
        with pytest.raises(ValueError, match=f"^{code}$"):
            apply_live_activation_isolated(grant={**grant, **changes}, **kwargs)
    assert not kwargs["isolated_root"].exists()


def test_live_bridge_materializes_native_activation_idempotently_and_recovers_prepare(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import (
        _live_activation_paths, apply_live_activation_isolated, reconcile_live_activation_journal,
        verify_live_activation_isolated,
    )
    grant, predecessor, plan, allocation, _ = _activation_fixture(tmp_path)
    root = tmp_path / "isolated-native"
    repo_root = Path(__file__).resolve().parents[1]
    watched = [repo_root / ".gwc", repo_root / "selector.json", repo_root / "checkpoint.json", repo_root / "cursor.json"]
    def hashes():
        return {str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else path.name:
                hashlib.sha256(path.read_bytes()).hexdigest()
                for base in watched for path in ([base] if base.is_file() else base.rglob("*") if base.is_dir() else [])
                if path.is_file()}
    real_before = hashes()
    r3_path = repo_root / "core/node-architect/q0-controlled-failure-frontier-r3.json"
    r3_before = hashlib.sha256(r3_path.read_bytes()).hexdigest()
    kwargs = dict(grant=grant, predecessor=predecessor, runtime_plan=plan, node_allocation=allocation,
                  branch="fix/test", head="b" * 40, isolated_root=root,
                  successor_plan_ref="core/node-architect/q0-successor-runtime-plan-w1-w6.json")
    result = apply_live_activation_isolated(**kwargs)
    readback = verify_live_activation_isolated(root)
    assert readback == {"resolved_plan_ref":"core/node-architect/q0-successor-runtime-plan-w1-w6.json",
                        "generation":1,"activation_status":"ACTIVATED"}
    assert result["resolve_readback"] == readback
    assert result["authority_granted"] is False and result["live_target_touched"] is False
    import sqlite3
    db_path = _live_activation_paths(root)["database"]
    with closing(sqlite3.connect(db_path)) as db:
        with db:
            assert db.execute("SELECT COUNT(*) FROM engineering_plan_activation").fetchone()[0] == 1
    before = (root / "live-activation-journal.json").read_bytes()
    second = apply_live_activation_isolated(**kwargs)
    assert second["already_applied"] is True
    assert (root / "live-activation-journal.json").read_bytes() == before
    record = _live_activation_paths(root)["record"]
    assert record.is_relative_to(root) and record.is_file()

    # A durable PREPARE can be replayed and the following reconciliation is a no-op.
    rows = json.loads(before)
    rows = [row for row in rows if row["phase"] == "PREPARE"]
    (root / "live-activation-journal.json").write_text(json.dumps(rows))
    (root / "core/node-architect/q0-engineering-coordination-route-r1.json").unlink()
    assert reconcile_live_activation_journal(root)["status"] == "COMPLETED"
    assert reconcile_live_activation_journal(root)["status"] == "NO_PENDING_PREPARE"
    assert verify_live_activation_isolated(root)["generation"] == 1
    assert hashes() == real_before
    assert hashlib.sha256(r3_path.read_bytes()).hexdigest() == r3_before


def test_successor_activation_resolves_successor_not_r3(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import apply_live_activation_isolated, verify_live_activation_isolated
    grant, predecessor, plan, allocation, _ = _activation_fixture(tmp_path)
    successor_plan_ref = "core/node-architect/q0-successor-runtime-plan-w1-w6.json"
    predecessor["runtime_plan_ref"] = "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json"
    predecessor["runtime_plan_digest"] = "sha256:" + "f" * 64
    kwargs = dict(grant=grant, predecessor=predecessor, runtime_plan=plan, node_allocation=allocation,
                  branch="fix/test", head="b" * 40, isolated_root=tmp_path / "successor-root",
                  successor_plan_ref=successor_plan_ref)
    # Bind the grant to the complete predecessor identity used for this activation.
    from tools.node_architect.q0_m1_m7_integration import _digest
    grant["bindings"]["predecessor_context_digest"] = _digest(predecessor)
    apply_live_activation_isolated(**kwargs)
    assert verify_live_activation_isolated(kwargs["isolated_root"])["resolved_plan_ref"] == successor_plan_ref
    assert successor_plan_ref != "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json"


def test_activation_rejects_r3_as_successor(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import apply_live_activation_isolated, _digest
    grant, predecessor, plan, allocation, _ = _activation_fixture(tmp_path)
    predecessor["runtime_plan_ref"] = "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json"
    predecessor["runtime_plan_digest"] = "sha256:" + "f" * 64
    grant["bindings"]["predecessor_context_digest"] = _digest(predecessor)
    with pytest.raises(ValueError, match="^SUCCESSOR_PLAN_MUST_DIFFER_FROM_PREDECESSOR$"):
        apply_live_activation_isolated(
            grant=grant, predecessor=predecessor, runtime_plan=plan, node_allocation=allocation,
            branch="fix/test", head="b" * 40, isolated_root=tmp_path / "reject-r3",
            successor_plan_ref="core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json")


@pytest.mark.parametrize("bad_ref,code", [
    ("/absolute/plan.json", "SUCCESSOR_PLAN_REF_INVALID"),
    ("core/node-architect/../escape.json", "SUCCESSOR_PLAN_REF_INVALID"),
    ("core/node-architect/predecessor.json", "SUCCESSOR_PLAN_MUST_DIFFER_FROM_PREDECESSOR"),
])
def test_activation_rejects_predecessor_ref_and_bad_refs(tmp_path, bad_ref, code):
    from tools.node_architect.q0_m1_m7_integration import apply_live_activation_isolated
    grant, predecessor, plan, allocation, _ = _activation_fixture(tmp_path)
    if bad_ref.endswith("predecessor.json"):
        predecessor["runtime_plan_ref"] = bad_ref
        from tools.node_architect.q0_m1_m7_integration import _digest
        grant["bindings"]["predecessor_context_digest"] = _digest(predecessor)
    with pytest.raises(ValueError, match=f"^{code}$"):
        apply_live_activation_isolated(
            grant=grant, predecessor=predecessor, runtime_plan=plan, node_allocation=allocation,
            branch="fix/test", head="b" * 40, isolated_root=tmp_path / "reject-bad-ref",
            successor_plan_ref=bad_ref)


def test_activation_rejects_successor_plan_digest_matching_predecessor(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import apply_live_activation_isolated
    grant, predecessor, plan, allocation, _ = _activation_fixture(tmp_path)
    import hashlib
    plan_bytes = (json.dumps(plan, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    predecessor["runtime_plan_digest"] = "sha256:" + hashlib.sha256(plan_bytes).hexdigest()
    with pytest.raises(ValueError, match="^SUCCESSOR_PLAN_MUST_DIFFER_FROM_PREDECESSOR$"):
        apply_live_activation_isolated(
            grant=grant, predecessor=predecessor, runtime_plan=plan, node_allocation=allocation,
            branch="fix/test", head="b" * 40, isolated_root=tmp_path / "reject-matching-digest",
            successor_plan_ref="core/node-architect/q0-successor-runtime-plan-w1-w6.json")


def test_activation_adapter_exists_and_envelope_points_to_it():
    from tools.node_architect import q0_m1_m7_integration as integration
    assert callable(getattr(integration, "activate_successor_plan", None))
    envelope = build_live_activation_effect_envelope(idempotency_key="adapter-v2")
    assert envelope["schema_id"] == "gwc.q0.live-activation-effect-envelope.v2"
    assert envelope["api_entrypoint"] == "tools.node_architect.q0_m1_m7_integration.activate_successor_plan"
    assert envelope["live_mode"] is False


def test_activation_adapter_rejects_absent_independent_grant_without_writes(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import activate_successor_plan
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    before = {p.relative_to(sandbox).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sandbox.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="^LIVE_ACTIVATION_AUTHORITY_REQUIRED$"):
        activate_successor_plan(grant=None, predecessor={}, runtime_plan={}, node_allocation={},
                                branch="branch", head="head", sandbox_root=sandbox)
    after = {p.relative_to(sandbox).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sandbox.rglob("*") if p.is_file()}
    assert after == before


def test_activation_dry_run_has_durable_prepare_and_sealed_readback(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import (
        activate_successor_plan, read_activation_receipt,
    )
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    predecessor = {"run_id": "prior-run", "context_digest": "sha256:" + "d" * 64}
    plan = {"run_id": "next-run", "digest": "sha256:" + "a" * 64}
    allocation = {"node_allocation_id": "alloc-1", "content_digest": {"value": "sha256:" + "c" * 64}}
    from tools.node_architect.q0_m1_m7_integration import _digest
    grant = {"grant_ref": "grant:1", "authority_kind": "SEPARATE_HUMAN_OR_CONTROLLER_GRANT",
             "actor": "controller-1", "scope": ["q0.live_activation.sandbox"],
             "issued_at": "2020-01-01T00:00:00Z", "expires_at": "2999-01-01T00:00:00Z",
             "bindings": {"predecessor_context_digest": _digest(predecessor),
                          "runtime_plan_digest": plan["digest"],
                          "node_allocation_digest": allocation["content_digest"]["value"],
                          "branch": "fix/test", "head": "b" * 40}}
    result = activate_successor_plan(grant=grant, predecessor=predecessor, runtime_plan=plan,
                                     node_allocation=allocation, branch="fix/test", head="b" * 40,
                                     sandbox_root=sandbox, mode="DRY_RUN")
    assert result["accepted"] is True and result["executed"] is False
    assert result["authority_granted"] is False
    assert result["typed_ce_admitted"] is False
    assert result["protected_effect"] == "SANDBOX_ONLY"
    assert read_activation_receipt(sandbox) is None
    journal = json.loads((sandbox / "activation-journal.json").read_text())
    assert journal[-1]["phase"] == "PREPARE"


def _activation_fixture(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import _digest
    predecessor = {"run_id": "prior-run", "context_digest": "sha256:" + "d" * 64,
                   "runtime_plan_ref": "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json",
                   "runtime_plan_digest": "sha256:" + "e" * 64}
    plan = {"run_id": "next-run", "digest": "sha256:" + "a" * 64}
    allocation = {"node_allocation_id": "alloc-1", "content_digest": {"value": "sha256:" + "c" * 64}}
    grant = {"grant_ref": "grant:1", "authority_kind": "SEPARATE_HUMAN_OR_CONTROLLER_GRANT",
             "actor": "controller-1", "scope": ["q0.live_activation.sandbox"],
             "issued_at": "2020-01-01T00:00:00Z", "expires_at": "2999-01-01T00:00:00Z",
             "bindings": {"predecessor_context_digest": _digest(predecessor),
                          "runtime_plan_digest": plan["digest"],
                          "node_allocation_digest": allocation["content_digest"]["value"],
                          "branch": "fix/test", "head": "b" * 40}}
    sandbox = tmp_path / "sandbox-activation"
    sandbox.mkdir()
    return grant, predecessor, plan, allocation, sandbox


def test_activation_sandbox_commit_orders_effects_seals_receipt_and_deduplicates(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import activate_successor_plan, read_activation_receipt
    grant, predecessor, plan, allocation, sandbox = _activation_fixture(tmp_path)
    kwargs = dict(grant=grant, predecessor=predecessor, runtime_plan=plan, node_allocation=allocation,
                  branch="fix/test", head="b" * 40, sandbox_root=sandbox, mode="SANDBOX_COMMIT")
    result = activate_successor_plan(**kwargs)
    assert result["executed"] is True
    assert result["applied_effects"] == ["selector_write", "checkpoint_write", "cursor_advance"]
    assert read_activation_receipt(sandbox)["receipt_digest"] == result["activation_receipt"]["receipt_digest"]
    journal_path = sandbox / "activation-journal.json"
    before = json.loads(journal_path.read_text())
    duplicate = activate_successor_plan(**kwargs)
    after = json.loads(journal_path.read_text())
    assert duplicate["already_applied"] is True
    assert after == before


def test_activation_reconciles_prepare_and_is_repeatable(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import (
        activate_successor_plan, read_activation_receipt, reconcile_activation_journal,
    )
    grant, predecessor, plan, allocation, sandbox = _activation_fixture(tmp_path)
    activate_successor_plan(grant=grant, predecessor=predecessor, runtime_plan=plan,
                            node_allocation=allocation, branch="fix/test", head="b" * 40,
                            sandbox_root=sandbox, mode="DRY_RUN")
    assert reconcile_activation_journal(sandbox)["status"] == "COMPLETED"
    receipt = read_activation_receipt(sandbox)
    assert receipt is not None
    assert reconcile_activation_journal(sandbox)["status"] == "NO_PENDING_PREPARE"
    assert read_activation_receipt(sandbox) == receipt


def test_activation_rejects_invalid_grant_and_mode_and_holds_lease(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import activate_successor_plan
    grant, predecessor, plan, allocation, sandbox = _activation_fixture(tmp_path)
    kwargs = dict(grant=grant, predecessor=predecessor, runtime_plan=plan, node_allocation=allocation,
                  branch="fix/test", head="b" * 40, sandbox_root=sandbox)
    for change, code in [
        ({"authority_kind": "UNTRUSTED"}, "GRANT_AUTHORITY_KIND_INVALID"),
        ({"grant_ref": " "}, "GRANT_IDENTITY_REQUIRED"),
        ({"actor": " "}, "GRANT_IDENTITY_REQUIRED"),
        ({"scope": []}, "GRANT_SCOPE_INVALID"),
        ({"expires_at": "2000-01-01T00:00:00Z"}, "GRANT_EXPIRED"),
        ({"issued_at": "2998-01-01T00:00:00Z"}, "GRANT_EXPIRED"),
    ]:
        bad = {**grant, **change}
        with pytest.raises(ValueError, match=f"^{code}$"):
            activate_successor_plan(**{**kwargs, "grant": bad})
    for key, wrong in [("predecessor_context_digest", "wrong"), ("runtime_plan_digest", "wrong"),
                       ("node_allocation_digest", "wrong"), ("branch", "wrong"), ("head", "wrong")]:
        bad = {**grant, "bindings": {**grant["bindings"], key: wrong}}
        with pytest.raises(ValueError, match="^GRANT_BINDING_MISMATCH$"):
            activate_successor_plan(**{**kwargs, "grant": bad})
    with pytest.raises(ValueError, match="^LIVE_ACTIVATION_MODE_INVALID$"):
        activate_successor_plan(**kwargs, mode="LIVE")
    lease = sandbox / ".activation-lease.json"
    lease.write_text(json.dumps({"owner_id": "other", "expires_at": 4102444800}))
    with pytest.raises(ValueError, match="^LEASE_HELD_BY_OTHER$"):
        activate_successor_plan(**kwargs, mode="SANDBOX_COMMIT")


def _real_r2_activation_fixture(tmp_path):
    import shutil
    repo_root = Path(__file__).resolve().parents[1]
    proposal = json.loads((repo_root / "core/node-architect/q0-native-successor-runtime-plan-r2.json").read_text())
    plan = proposal["native_runtime_plan"]
    plan_digest = plan["digest"]
    allocation = proposal["node_allocation"]
    predecessor = _predecessor(tmp_path, run_id="scrum781-q0-predecessor")
    predecessor["runtime_plan_ref"] = "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json"
    predecessor["runtime_plan_digest"] = "sha256:" + "f" * 64
    branch = "fix/SCRUM-781-q0-fresh-20261010-r1"
    head = subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True).strip()
    authority = {
        "authority_kind": "HUMAN_OPERATOR_EFFECT_AUTHORITY", "actor": "human-operator:test",
        "authority_ref": "authority:test:177", "scope": ["q0.live_activation.execute"],
        "issued_at": "2020-01-01T00:00:00Z", "expires_at": "2999-01-01T00:00:00Z",
        "bindings": {"predecessor_context_digest": predecessor["context_digest"],
                     "successor_plan_digest": plan_digest,
                     "node_allocation_digest": allocation["content_digest"]["value"],
                     "branch": branch, "head": head},
    }
    source = tmp_path / "real-authority-source"
    from tools.node_architect.q0_m1_m7_integration import (
        _REAL_TARGET_PLAN_REF, _R3_PREDECESSOR_PLAN_REF, ROUTE_REF, ACTIVATION_RECEIPT_REF,
    )
    for ref in (_REAL_TARGET_PLAN_REF, _R3_PREDECESSOR_PLAN_REF, ROUTE_REF, ACTIVATION_RECEIPT_REF):
        source_path = repo_root / ref
        if source_path.is_file():
            (source / Path(ref).parent).mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, source / ref)
    grant_ref = "authority/grants/authority-test-177.json"
    grant_path = source / grant_ref
    grant_path.parent.mkdir(parents=True, exist_ok=True)
    grant_path.write_text(json.dumps({**authority, "issuer_ref": grant_ref}), encoding="utf-8")
    authority["issuer_ref"] = grant_ref
    return source, proposal, plan, allocation, predecessor, authority, branch, head


@pytest.mark.parametrize("escape", ["parent_components", "symlink"])
def test_real_target_issuer_cannot_escape_canonical_grant_directory(tmp_path, escape):
    from tools.node_architect.q0_m1_m7_integration import RealTargetActivationAdapter

    source = tmp_path / "source"
    grants = source / "authority/grants"
    grants.mkdir(parents=True)
    outside = source / "not-a-grant.json"
    outside.write_text(json.dumps({"authority_kind": "HUMAN_OPERATOR_EFFECT_AUTHORITY"}))
    if escape == "parent_components":
        issuer_ref = "authority/grants/../../not-a-grant.json"
    else:
        (grants / "escaped.json").symlink_to(outside)
        issuer_ref = "authority/grants/escaped.json"
    before = outside.read_bytes()
    target = tmp_path / "unactivated"
    adapter = RealTargetActivationAdapter(source_root=source, live_root=target)
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE$"):
        adapter._canonical_issuer(issuer_ref)
    assert outside.read_bytes() == before
    assert not target.exists()


@pytest.mark.parametrize("escape", ["parent_components", "symlink"])
def test_real_target_transition_rejects_escaped_issuer_before_effects(tmp_path, escape):
    from tools.node_architect.q0_m1_m7_integration import RealTargetActivationAdapter, _REAL_TARGET_PLAN_REF

    source, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    outside = source / "not-a-grant.json"
    outside.write_text(json.dumps(authority))
    if escape == "parent_components":
        issuer_ref = "authority/grants/../../not-a-grant.json"
    else:
        (source / "authority/grants/escaped.json").symlink_to(outside)
        issuer_ref = "authority/grants/escaped.json"
    target = tmp_path / "unactivated-target"
    adapter = RealTargetActivationAdapter(source_root=source, live_root=target)
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE$"):
        adapter.transition(authority={**authority, "issuer_ref": issuer_ref},
                           predecessor=predecessor, successor_plan=plan,
                           successor_plan_ref=_REAL_TARGET_PLAN_REF,
                           node_allocation=allocation, branch=branch, head=head, mode="COMMIT")
    assert not target.exists()


def test_real_target_authority_rejects_policy_document_as_issuer(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import (
        _R3_PREDECESSOR_PLAN_REF, RealTargetActivationAdapter,
    )
    source, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    adapter = RealTargetActivationAdapter(source_root=source, live_root=tmp_path / "authority-target")
    kwargs = dict(predecessor=predecessor, successor_plan=plan,
                  successor_plan_ref="core/node-architect/q0-native-successor-runtime-plan-r2.json",
                  node_allocation=allocation, branch=branch, head=head)
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE$"):
        adapter.validate_authority(authority={**authority, "issuer_ref": _R3_PREDECESSOR_PLAN_REF}, **kwargs)


def test_real_target_authority_rejects_forged_grant_referencing_real_r3(tmp_path):
    """COMMAND #186: a structurally valid grant cannot self-authorize via real R3."""
    import shutil
    from tools.node_architect.q0_m1_m7_integration import (
        _REAL_TARGET_PLAN_REF, _R3_PREDECESSOR_PLAN_REF, RealTargetActivationAdapter,
    )
    source, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    forged_source = tmp_path / "forged-r3-source"
    for ref in (_REAL_TARGET_PLAN_REF, _R3_PREDECESSOR_PLAN_REF):
        (forged_source / Path(ref).parent).mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / ref, forged_source / ref)
    grant_ref = "authority/grants/forged-real-r3.json"
    grant_path = forged_source / grant_ref
    grant_path.parent.mkdir(parents=True, exist_ok=True)
    forged_grant = {**authority, "actor": "human-operator:forge", "authority_ref": "authority:forge:1",
                    "issuer_ref": _R3_PREDECESSOR_PLAN_REF}
    grant_path.write_text(json.dumps(forged_grant), encoding="utf-8")
    adapter = RealTargetActivationAdapter(source_root=forged_source, live_root=tmp_path / "forged-r3-target")
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE$"):
        adapter.validate_authority(authority=forged_grant, predecessor=predecessor,
                                   successor_plan=plan,
                                   successor_plan_ref=_REAL_TARGET_PLAN_REF,
                                   node_allocation=allocation, branch=branch, head=head)
    assert not (tmp_path / "forged-r3-target").exists()


def test_real_target_authority_trust_anchor_unavailable_without_independent_grant(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import (
        _R3_PREDECESSOR_PLAN_REF, RealTargetActivationAdapter,
    )
    source, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    adapter = RealTargetActivationAdapter(source_root=source, live_root=tmp_path / "missing-anchor-target")
    kwargs = dict(predecessor=predecessor, successor_plan=plan,
                  successor_plan_ref="core/node-architect/q0-native-successor-runtime-plan-r2.json",
                  node_allocation=allocation, branch=branch, head=head)
    issuer_refs = (None, _R3_PREDECESSOR_PLAN_REF)
    for issuer_ref in issuer_refs:
        candidate = ({k: v for k, v in authority.items() if k != "issuer_ref"}
                     if issuer_ref is None else {**authority, "issuer_ref": issuer_ref})
        with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE$"):
            adapter.validate_authority(authority=candidate, **kwargs)
    assert not (tmp_path / "missing-anchor-target").exists()


def test_real_target_authority_rejects_caller_supplied_registry_path(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import RealTargetActivationAdapter
    source, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    adapter = RealTargetActivationAdapter(source_root=source, live_root=tmp_path / "authority-target")
    kwargs = dict(predecessor=predecessor, successor_plan=plan,
                  successor_plan_ref="core/node-architect/q0-native-successor-runtime-plan-r2.json",
                  node_allocation=allocation, branch=branch, head=head)
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE$"):
        adapter.validate_authority(authority={**authority, "issuer_ref": str(tmp_path / "forged.json")}, **kwargs)


def test_real_target_effect_not_executed_when_trust_anchor_unavailable(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import (
        _R3_PREDECESSOR_PLAN_REF, RealTargetActivationAdapter,
    )
    source, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    live_root = tmp_path / "untrusted-effect-target"
    adapter = RealTargetActivationAdapter(source_root=source, live_root=live_root)
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE$"):
        adapter.transition(authority={**authority, "issuer_ref": _R3_PREDECESSOR_PLAN_REF},
                           predecessor=predecessor, successor_plan=plan,
                           successor_plan_ref="core/node-architect/q0-native-successor-runtime-plan-r2.json",
                           node_allocation=allocation, branch=branch, head=head, mode="COMMIT")
    assert not live_root.exists()


def test_real_target_first_activation_allows_missing_receipt_and_flags_cold_start(tmp_path):
    import shutil
    from tools.node_architect.q0_m1_m7_integration import (
        ACTIVATION_RECEIPT_REF, _REAL_TARGET_PLAN_REF, _R3_PREDECESSOR_PLAN_REF,
        RealTargetActivationAdapter,
    )
    repo_root, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    source = tmp_path / "cold-source"
    (source / Path(_REAL_TARGET_PLAN_REF).parent).mkdir(parents=True)
    (source / Path(_R3_PREDECESSOR_PLAN_REF).parent).mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo_root / _REAL_TARGET_PLAN_REF, source / _REAL_TARGET_PLAN_REF)
    shutil.copy2(repo_root / _R3_PREDECESSOR_PLAN_REF, source / _R3_PREDECESSOR_PLAN_REF)
    grant_ref = authority["issuer_ref"]
    (source / Path(grant_ref).parent).mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo_root / grant_ref, source / grant_ref)
    adapter = RealTargetActivationAdapter(source_root=source, live_root=tmp_path / "cold-target")
    view = adapter._real_target_view(_REAL_TARGET_PLAN_REF, plan, predecessor)
    assert ACTIVATION_RECEIPT_REF not in view["artifacts"]
    assert view["first_activation"] is True
    _bind_disposable_real_target_authority(adapter, authority, _REAL_TARGET_PLAN_REF)
    result = adapter.preflight(authority=authority, predecessor=predecessor, successor_plan=plan,
                               successor_plan_ref=_REAL_TARGET_PLAN_REF, node_allocation=allocation,
                               branch=branch, head=head)
    assert result["accepted"] is True and result["executed"] is False
    assert result["first_activation"] is True
    assert result["authority_verification"]["verified"] is True
    assert result["authority_verification"]["trusted_issuer_ref"] == authority["issuer_ref"]
    assert result["authority_verification"]["trusted_issuer_digest"].startswith("sha256:")


def test_real_target_subsequent_activation_without_receipt_is_rejected(tmp_path):
    import shutil
    from tools.node_architect.q0_m1_m7_integration import (
        _REAL_TARGET_PLAN_REF, _R3_PREDECESSOR_PLAN_REF, RealTargetActivationAdapter,
    )
    repo_root, _, plan, _, predecessor, _, _, _ = _real_r2_activation_fixture(tmp_path)
    source = tmp_path / "warm-source"
    for ref in (_REAL_TARGET_PLAN_REF, _R3_PREDECESSOR_PLAN_REF):
        (source / Path(ref).parent).mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / ref, source / ref)
    (source / "selector.json").write_text("{}")
    adapter = RealTargetActivationAdapter(source_root=source, live_root=tmp_path / "warm-target")
    with pytest.raises(ValueError, match="^REAL_TARGET_RECEIPT_MISSING$"):
        adapter._real_target_view(_REAL_TARGET_PLAN_REF, plan, predecessor)



def test_real_target_adapter_rejects_unallowlisted_authority_scope(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import RealTargetActivationAdapter
    repo_root, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    adapter = RealTargetActivationAdapter(source_root=repo_root, live_root=tmp_path / "isolated")
    kwargs = dict(authority={**authority, "scope": ["q0.live_activation.execute", "production.write"]},
                  predecessor=predecessor, successor_plan=plan,
                  successor_plan_ref="core/node-architect/q0-native-successor-runtime-plan-r2.json",
                  node_allocation=allocation, branch=branch, head=head)
    with pytest.raises(ValueError, match="^REAL_TARGET_AUTHORITY_SCOPE_INVALID$"):
        adapter.preflight(**kwargs)


def test_real_target_adapter_rejects_expired_and_mismatched_authority_bindings(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import RealTargetActivationAdapter
    repo_root, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    adapter = RealTargetActivationAdapter(source_root=repo_root, live_root=tmp_path / "authority-isolated")
    kwargs = dict(predecessor=predecessor, successor_plan=plan,
                  successor_plan_ref="core/node-architect/q0-native-successor-runtime-plan-r2.json",
                  node_allocation=allocation, branch=branch, head=head)
    for change, code in [
        ({"authority_kind": "UNKNOWN"}, "EFFECT_AUTHORITY_KIND_INVALID"),
        ({"expires_at": "2000-01-01T00:00:00Z"}, "EFFECT_AUTHORITY_EXPIRED"),
        ({"bindings": {**authority["bindings"], "branch": "wrong"}}, "EFFECT_AUTHORITY_BINDING_MISMATCH"),
    ]:
        with pytest.raises(ValueError, match=f"^{code}$"):
            adapter.preflight(authority={**authority, **change}, **kwargs)
    assert not (tmp_path / "authority-isolated").exists()


def test_real_target_adapter_recovers_partial_commit_and_rolls_back(tmp_path, monkeypatch):
    from tools.node_architect import q0_m1_m7_integration as integration
    repo_root, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    root = tmp_path / "partial-real-target"
    adapter = integration.RealTargetActivationAdapter(source_root=repo_root, live_root=root)
    _bind_disposable_real_target_authority(adapter, authority, integration._REAL_TARGET_PLAN_REF)
    kwargs = dict(authority=authority, predecessor=predecessor, successor_plan=plan,
                  successor_plan_ref="core/node-architect/q0-native-successor-runtime-plan-r2.json",
                  node_allocation=allocation, branch=branch, head=head)
    original_write = integration._executor_write
    def fail_after_selector(path, content):
        original_write(path, content)
        if path.name == "selector.json":
            raise RuntimeError("partial real-target commit")
    monkeypatch.setattr(integration, "_executor_write", fail_after_selector)
    with pytest.raises(RuntimeError, match="partial real-target commit"):
        adapter.commit(**kwargs)
    monkeypatch.setattr(integration, "_executor_write", original_write)
    assert integration.reconcile_real_target_activation_journal(root)["status"] == "COMPLETED"
    assert integration.verify_real_target_transition(
        root, expected_receipt=integration.read_live_activation_receipt(root))["verified"] is True
    assert integration.rollback_real_target_activation(root)["status"] == "ROLLED_BACK"


def test_real_target_rollback_restores_isolated_selector_checkpoint_cursor(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import RealTargetActivationAdapter, rollback_real_target_activation
    repo_root, _, plan, allocation, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    root = tmp_path / "rollback-isolated"
    adapter = RealTargetActivationAdapter(source_root=repo_root, live_root=root)
    _bind_disposable_real_target_authority(adapter, authority,
                                         "core/node-architect/q0-native-successor-runtime-plan-r2.json")
    kwargs = dict(authority=authority, predecessor=predecessor, successor_plan=plan,
                  successor_plan_ref="core/node-architect/q0-native-successor-runtime-plan-r2.json",
                  node_allocation=allocation, branch=branch, head=head)
    adapter.commit(**kwargs)
    assert all((root / name).is_file() for name in ("selector.json", "checkpoint.json", "cursor.json"))
    assert rollback_real_target_activation(root)["status"] == "ROLLED_BACK"
    assert not any((root / name).exists() for name in ("selector.json", "checkpoint.json", "cursor.json"))


# Bounded R2 -> exact R4 bootstrap. These are disposable synthetic grant fixtures,
# NOT operator grants or evidence of live approval, activation or host loading.
R4_ARTIFACT_ROOT = Path(__file__).resolve().parents[1]
R4_WRAPPER_REF = "core/node-architect/q0-native-successor-runtime-plan-r3-proposal-r2.json"
R4_PLAN_REF = "core/node-architect/q0-r4-native-runtime-plan-r1.json"
R4_ALLOCATION_REF = "core/node-architect/q0-r4-work-node-allocation-r1.json"
R4_DIGEST = "sha256:16445abb85d78f61ac6dc2207c47c98240a45c8107e49f546b369e2d90bfa38f"
R4_PREVIOUS = "sha256:bdcf4e9c44ea1b5cdeaa464c77446b9e1b66aeec98f2aaa48018564a2eedc0e6"


def _r4_bootstrap_fixture(tmp_path):
    import shutil
    from tools.node_architect.q0_m1_m7_integration import RealTargetActivationAdapter
    source, _, _, _, predecessor, authority, branch, head = _real_r2_activation_fixture(tmp_path)
    for ref in (R4_WRAPPER_REF, R4_PLAN_REF, R4_ALLOCATION_REF):
        (source / ref).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(R4_ARTIFACT_ROOT / ref, source / ref)
    wrapper = json.loads((source / R4_WRAPPER_REF).read_text())
    plan = wrapper["native_runtime_plan"]
    allocation = json.loads((source / R4_ALLOCATION_REF).read_text())
    target = tmp_path / "r4-unactivated-target"
    authority["bindings"].update(successor_plan_digest=plan["digest"],
                                node_allocation_digest=allocation["content_digest"]["value"],
                                successor_plan_ref=R4_WRAPPER_REF, live_target=str(target.resolve()))
    authority["issued"] = True
    (source / authority["issuer_ref"]).write_text(json.dumps(authority))
    adapter = RealTargetActivationAdapter(source_root=source, live_root=target)
    kwargs = dict(authority=authority, predecessor=predecessor, successor_plan=plan,
                  successor_plan_ref=R4_WRAPPER_REF, node_allocation=allocation, branch=branch, head=head)
    return adapter, kwargs


def _snapshot_tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_bootstrap_exact_r4_view_accepts_same_c273_plan_without_writes(tmp_path):
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    before = _snapshot_tree(tmp_path)
    view = adapter._real_target_view(R4_WRAPPER_REF, kwargs["successor_plan"], kwargs["predecessor"])
    assert kwargs["successor_plan"]["digest"] == R4_DIGEST
    assert kwargs["successor_plan"]["previous_digest"] == R4_PREVIOUS
    assert R4_WRAPPER_REF in view["artifacts"]
    assert "core/node-architect/q0-native-successor-runtime-plan-r2.json" not in view["artifacts"]
    assert not adapter.live_root.exists()
    assert _snapshot_tree(tmp_path) == before


def test_bootstrap_source_view_hashes_selected_r4_wrapper(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import _digest
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    path = adapter.source_root / R4_WRAPPER_REF
    first = adapter._real_target_view(R4_WRAPPER_REF, kwargs["successor_plan"], kwargs["predecessor"])
    path.write_bytes(path.read_bytes() + b"\n")
    second = adapter._real_target_view(R4_WRAPPER_REF, kwargs["successor_plan"], kwargs["predecessor"])
    assert first["view_digest"] != second["view_digest"]
    assert second["artifacts"][R4_WRAPPER_REF] == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert second["view_digest"] == _digest(second["artifacts"])


@pytest.mark.parametrize("ref", ["core/node-architect/unknown.json", "../escape.json", "/tmp/plan.json",
                                  "core/node-architect/../q0-native-successor-runtime-plan-r2.json"])
def test_bootstrap_unknown_successor_refs_remain_denied_without_writes(tmp_path, ref):
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    before = _snapshot_tree(tmp_path)
    with pytest.raises(ValueError, match="^SUCCESSOR_PLAN_REF_INVALID$"):
        adapter._real_target_view(ref, kwargs["successor_plan"], kwargs["predecessor"])
    assert _snapshot_tree(tmp_path) == before
    assert not adapter.live_root.exists()


@pytest.mark.parametrize("change", ["caller_plan", "digest", "previous_digest", "payload", "separate_plan", "allocation_bytes"])
def test_bootstrap_r4_exact_artifact_mismatches_remain_denied(tmp_path, change):
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    plan = copy.deepcopy(kwargs["successor_plan"])
    wrapper = json.loads((adapter.source_root / R4_WRAPPER_REF).read_text())
    if change == "caller_plan":
        plan["revision"] += 1
    elif change == "separate_plan":
        (adapter.source_root / R4_PLAN_REF).write_text("{}")
    elif change == "allocation_bytes":
        path = adapter.source_root / R4_ALLOCATION_REF
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        if change == "digest":
            plan["digest"] = "sha256:" + "0" * 64
        elif change == "previous_digest":
            plan["previous_digest"] = "sha256:" + "1" * 64
        else:
            plan["scope"]["max_children"] = 2
        wrapper["native_runtime_plan"] = plan
        (adapter.source_root / R4_WRAPPER_REF).write_text(json.dumps(wrapper))
        (adapter.source_root / R4_PLAN_REF).write_text(json.dumps(plan))
    before = _snapshot_tree(tmp_path)
    with pytest.raises(ValueError, match="^REAL_TARGET_SUCCESSOR_MISMATCH$"):
        adapter._real_target_view(R4_WRAPPER_REF, plan, kwargs["predecessor"])
    assert _snapshot_tree(tmp_path) == before
    assert not adapter.live_root.exists()


def _store_disposable_grant(adapter, authority):
    (adapter.source_root / authority["issuer_ref"]).write_text(json.dumps(authority))


def _bind_disposable_real_target_authority(adapter, authority, successor_ref):
    authority["bindings"].update(successor_plan_ref=successor_ref, live_target=str(adapter.live_root))
    _store_disposable_grant(adapter, authority)


@pytest.mark.parametrize("field,value", [
    ("successor_plan_ref", "core/node-architect/q0-native-successor-runtime-plan-r2.json"),
    ("successor_plan_ref", "core/node-architect/wrong.json"),
    ("live_target", "OTHER_TARGET"),
    ("live_target", "NONCANONICAL_ALIAS"),
    ("successor_plan_ref", None),
    ("live_target", None),
])
def test_bootstrap_authority_requires_exact_successor_ref_and_canonical_target(tmp_path, field, value):
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    authority = kwargs["authority"]
    if value == "OTHER_TARGET":
        value = str(tmp_path / "other-target")
    elif value == "NONCANONICAL_ALIAS":
        value = str(adapter.live_root.parent / "uncreated" / ".." / adapter.live_root.name)
    authority["bindings"][field] = value
    _store_disposable_grant(adapter, authority)
    before = _snapshot_tree(tmp_path)
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_BINDING_MISMATCH$"):
        adapter.preflight(**kwargs)
    assert not adapter.live_root.exists()
    assert _snapshot_tree(tmp_path) == before


def test_bootstrap_r2_committed_projection_cannot_back_rebound_r4_authority(tmp_path):
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    grant = copy.deepcopy(kwargs["authority"])
    grant["bindings"]["successor_plan_ref"] = "core/node-architect/q0-native-successor-runtime-plan-r2.json"
    _store_disposable_grant(adapter, grant)
    before = _snapshot_tree(tmp_path)
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_BINDING_MISMATCH$"):
        adapter.preflight(**kwargs)
    assert _snapshot_tree(tmp_path) == before
    assert not adapter.live_root.exists()


@pytest.mark.parametrize("issued", [False, None])
def test_bootstrap_unissued_template_is_not_operator_authority(tmp_path, issued):
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    grant = {**kwargs["authority"], "issued": issued}
    _store_disposable_grant(adapter, grant)
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_GRANT_NOT_ISSUED$"):
        adapter.preflight(**kwargs)
    assert not adapter.live_root.exists()


def test_bootstrap_every_accepted_plan_is_explicitly_self_referential(tmp_path):
    from tools.node_architect.q0_m1_m7_integration import _SELF_REFERENTIAL_ISSUER_REFS
    assert {R4_WRAPPER_REF, R4_PLAN_REF, R4_ALLOCATION_REF,
            "core/node-architect/q0-native-successor-runtime-plan-r2.json"} <= _SELF_REFERENTIAL_ISSUER_REFS
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    for ref in (R4_WRAPPER_REF, R4_PLAN_REF, R4_ALLOCATION_REF):
        with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE$"):
            adapter.preflight(**{**kwargs, "authority": {**kwargs["authority"], "issuer_ref": ref}})
    assert not adapter.live_root.exists()


def test_bootstrap_r4_preflight_still_requires_independent_grant_without_writes(tmp_path):
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    (adapter.source_root / kwargs["authority"]["issuer_ref"]).unlink()
    before = _snapshot_tree(tmp_path)
    with pytest.raises(ValueError, match="^EFFECT_AUTHORITY_TRUST_ANCHOR_UNAVAILABLE$"):
        adapter.preflight(**kwargs)
    assert _snapshot_tree(tmp_path) == before
    assert not adapter.live_root.exists()


def test_bootstrap_bound_r4_preflight_has_no_effects(tmp_path):
    adapter, kwargs = _r4_bootstrap_fixture(tmp_path)
    before = _snapshot_tree(tmp_path)
    result = adapter.preflight(**kwargs)
    assert result["accepted"] is True and result["executed"] is False
    assert R4_WRAPPER_REF in result["real_target_view"]["artifacts"]
    assert not adapter.live_root.exists()
    assert _snapshot_tree(tmp_path) == before
