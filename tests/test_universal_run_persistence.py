from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from test_universal_v2_core_isolation import _make_controller_owned_g4_binding
from tools.node_architect.universal_run_controller import UniversalController
from tools.node_architect.universal_run_persistence import (
    CheckpointPersistenceError,
    make_checkpoint_document,
    materialize_controller_successor_snapshot,
    materialize_successor_bound_transition_receipt,
    materialize_persistence_intent,
    persist_same_sequence_checkpoint_recovery,
)


def _digest(value, omitted=None):
    body = {k: v for k, v in value.items() if k != omitted}
    return "sha256:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _decision():
    profile, plan, state, allocation = _make_controller_owned_g4_binding()
    controller = UniversalController(profile=profile, runtime_plan=plan, run_state=state, node_allocation=allocation)
    controller.assign_current_action()
    decision = controller.complete_controller_owned_gate(evidence={"integration_outcome": "IN_PLACE"})
    return profile, plan, allocation, state, decision


def _snapshot(tmp_path):
    profile, plan, allocation, predecessor, decision = _decision()
    snapshot_path = tmp_path / "successors" / "seq11.json"
    result = materialize_controller_successor_snapshot(
        successor_run_state=decision["successor_run_state"],
        runtime_plan_digest=plan["digest"],
        candidate_sha=plan["source_binding"]["pre_head_sha"],
        transition_ref=decision["transition_receipt"]["transition_ref"],
        path=snapshot_path,
    )
    transition_path = tmp_path / "transitions" / "seq10-to11.json"
    materialized_transition = materialize_successor_bound_transition_receipt(
        transition=decision["transition_receipt"], snapshot=result, path=transition_path
    )
    transition = materialized_transition["transition"]
    return profile, plan, allocation, predecessor, decision, snapshot_path, result, transition_path, transition


def _corrupt_checkpoint_document(state, plan, allocation):
    document = make_checkpoint_document(run_state=state, runtime_plan=plan, node_allocation=allocation)
    document["run_state"]["state_digest"] = "sha256:" + "0" * 64
    document["state_digest"] = document["run_state"]["state_digest"]
    document.pop("checkpoint_digest", None)
    document["checkpoint_digest"] = _digest(document, "checkpoint_digest")
    return document


def _controller_authorization(plan, state, snapshot, transition, checkpoint_sha):
    auth = {
        "schema_id": "gwc.universal-run.same-sequence-recovery-authorization.v2",
        "schema_version": 2,
        "decision": "AUTHORIZE",
        "authorized_action": "NONREWRITE_SAME_SEQ_CHECKPOINT_RECOVERY",
        "authority_ref": "controller-comment:107",
        "controller_sequence": 107,
        "controller_body_sha256": "a" * 64,
        "run_id": state["run_id"],
        "runtime_plan_digest": plan["digest"],
        "candidate_sha": plan["source_binding"]["pre_head_sha"],
        "sequence": state["sequence"],
        "active_gate": state["active_gate"],
        "next_owner": state["next_owner"],
        "typed_next": state["typed_next"],
        "expected_checkpoint_file_sha256": checkpoint_sha,
        "successor_snapshot_digest": snapshot["snapshot_digest"],
        "transition_digest": transition["transition_digest"],
        "authority_granted": False,
        "executed_effects": [],
    }
    auth["authorization_digest"] = _digest(auth)
    return auth


def test_successor_snapshot_is_full_immutable_and_exact_readback(tmp_path):
    _, plan, _, _, decision = _decision()
    path = tmp_path / "successor.json"
    first = materialize_controller_successor_snapshot(
        successor_run_state=decision["successor_run_state"],
        runtime_plan_digest=plan["digest"],
        candidate_sha=plan["source_binding"]["pre_head_sha"],
        transition_ref=decision["transition_receipt"]["transition_ref"],
        path=path,
    )
    body = json.loads(path.read_text())
    assert body["successor_run_state"] == decision["successor_run_state"]
    assert body["successor_state_digest"] == decision["successor_run_state"]["state_digest"]
    assert body["snapshot_digest"] == _digest(body, "snapshot_digest")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first["file_sha256"]
    replay = materialize_controller_successor_snapshot(
        successor_run_state=decision["successor_run_state"],
        runtime_plan_digest=plan["digest"],
        candidate_sha=plan["source_binding"]["pre_head_sha"],
        transition_ref=decision["transition_receipt"]["transition_ref"],
        path=path,
    )
    assert replay["idempotent_replay"] is True
    corrupt = copy.deepcopy(decision["successor_run_state"])
    corrupt["sequence"] += 1
    with pytest.raises(CheckpointPersistenceError, match="SUCCESSOR_STATE_DIGEST_INVALID"):
        materialize_controller_successor_snapshot(
            successor_run_state=corrupt,
            runtime_plan_digest=plan["digest"],
            candidate_sha=plan["source_binding"]["pre_head_sha"],
            transition_ref=decision["transition_receipt"]["transition_ref"],
            path=tmp_path / "corrupt.json",
        )


def test_persistence_intent_is_durable_before_checkpoint_mutation(tmp_path):
    profile, plan, allocation, predecessor, decision, snapshot_path, snapshot, transition_path, transition = _snapshot(tmp_path)
    checkpoint_path = tmp_path / "official.json"
    corrupt_state = copy.deepcopy(decision["successor_run_state"])
    corrupt_state["state_digest"] = "sha256:" + "0" * 64
    current = _corrupt_checkpoint_document(decision["successor_run_state"], plan, allocation)
    checkpoint_path.write_text(json.dumps(current, sort_keys=True, indent=2) + "\n")
    before = checkpoint_path.read_bytes()
    intended = make_checkpoint_document(run_state=decision["successor_run_state"], runtime_plan=plan, node_allocation=allocation)
    with pytest.raises(CheckpointPersistenceError, match="SUCCESSOR_SNAPSHOT_INVALID"):
        materialize_persistence_intent(
            current_checkpoint_path=checkpoint_path,
            expected_current_file_sha256=hashlib.sha256(before).hexdigest(),
            intended_checkpoint_document=intended,
            snapshot_path=tmp_path / "missing-canonical-successor.json",
            transition_receipt_path=transition_path,
            writer_identity="tools.node_architect.universal_run_persistence.persist_same_sequence_checkpoint_recovery/v1",
            intent_path=tmp_path / "missing-snapshot-intent.json",
        )
    assert checkpoint_path.read_bytes() == before
    intent_path = tmp_path / "intents" / "repair-intent.json"
    intent = materialize_persistence_intent(
        current_checkpoint_path=checkpoint_path,
        expected_current_file_sha256=hashlib.sha256(before).hexdigest(),
        intended_checkpoint_document=intended,
        snapshot_path=snapshot_path,
        transition_receipt_path=transition_path,
        writer_identity="tools.node_architect.universal_run_persistence.persist_same_sequence_checkpoint_recovery/v1",
        intent_path=intent_path,
    )
    assert checkpoint_path.read_bytes() == before
    saved = json.loads(intent_path.read_text())
    assert saved["prior_generation"]["checkpoint_file_sha256"] == hashlib.sha256(before).hexdigest()
    assert saved["intended_checkpoint_file_sha256"] == hashlib.sha256((json.dumps(intended, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()).hexdigest()
    assert saved["successor_snapshot"]["file_sha256"] == snapshot["file_sha256"]
    assert saved["transition_receipt"]["transition_digest"] == transition["transition_digest"]
    assert intent["intent_digest"] == saved["intent_digest"]


def test_recovery_requires_exact_controller_authorization_and_cas(tmp_path):
    profile, plan, allocation, predecessor, decision, snapshot_path, snapshot, transition_path, transition = _snapshot(tmp_path)
    checkpoint_path = tmp_path / "official.json"
    corrupt_state = copy.deepcopy(decision["successor_run_state"])
    corrupt_state["state_digest"] = "sha256:" + "0" * 64
    current = _corrupt_checkpoint_document(decision["successor_run_state"], plan, allocation)
    checkpoint_path.write_text(json.dumps(current, sort_keys=True, indent=2) + "\n")
    expected_bytes = checkpoint_path.read_bytes()
    intended = make_checkpoint_document(run_state=decision["successor_run_state"], runtime_plan=plan, node_allocation=allocation)
    intent_path = tmp_path / "intent.json"
    materialize_persistence_intent(
        current_checkpoint_path=checkpoint_path,
        expected_current_file_sha256=hashlib.sha256(expected_bytes).hexdigest(),
        intended_checkpoint_document=intended,
        snapshot_path=snapshot_path,
        transition_receipt_path=transition_path,
        writer_identity="tools.node_architect.universal_run_persistence.persist_same_sequence_checkpoint_recovery/v1",
        intent_path=intent_path,
    )
    archive_path = tmp_path / "archive" / "corrupt-original.json"
    with pytest.raises(CheckpointPersistenceError, match="RECOVERY_AUTHORIZATION_REQUIRED"):
        persist_same_sequence_checkpoint_recovery(
            checkpoint_path=checkpoint_path, intent_path=intent_path,
            snapshot_path=snapshot_path, transition_receipt_path=transition_path,
            archive_path=archive_path, authorization=None,
            profile=profile, runtime_plan=plan, node_allocation=allocation,
            recovery_receipt_path=tmp_path / "recovery-receipt.json",
        )
    assert checkpoint_path.read_bytes() == expected_bytes
    assert not archive_path.exists()

    checkpoint_path.write_bytes(expected_bytes + b"\nconcurrent-writer")
    auth = _controller_authorization(plan, corrupt_state, snapshot, transition, hashlib.sha256(expected_bytes).hexdigest())
    with pytest.raises(CheckpointPersistenceError, match="NATIVE_CHECKPOINT_CAS_CONFLICT"):
        persist_same_sequence_checkpoint_recovery(
            checkpoint_path=checkpoint_path, intent_path=intent_path,
            snapshot_path=snapshot_path, transition_receipt_path=transition_path,
            archive_path=archive_path, authorization=auth,
            profile=profile, runtime_plan=plan, node_allocation=allocation,
            recovery_receipt_path=tmp_path / "recovery-receipt.json",
        )
    assert not archive_path.exists()


def test_authorized_recovery_preserves_corrupt_bytes_and_logical_cursor(tmp_path):
    profile, plan, allocation, predecessor, decision, snapshot_path, snapshot, transition_path, transition = _snapshot(tmp_path)
    checkpoint_path = tmp_path / "official.json"
    corrupt_state = copy.deepcopy(decision["successor_run_state"])
    corrupt_state["state_digest"] = "sha256:" + "0" * 64
    current = _corrupt_checkpoint_document(decision["successor_run_state"], plan, allocation)
    checkpoint_path.write_text(json.dumps(current, sort_keys=True, indent=2) + "\n")
    old_bytes = checkpoint_path.read_bytes()
    old_sha = hashlib.sha256(old_bytes).hexdigest()
    intended = make_checkpoint_document(run_state=decision["successor_run_state"], runtime_plan=plan, node_allocation=allocation)
    intent_path = tmp_path / "intent.json"
    materialize_persistence_intent(
        current_checkpoint_path=checkpoint_path,
        expected_current_file_sha256=old_sha,
        intended_checkpoint_document=intended,
        snapshot_path=snapshot_path,
        transition_receipt_path=transition_path,
        writer_identity="tools.node_architect.universal_run_persistence.persist_same_sequence_checkpoint_recovery/v1",
        intent_path=intent_path,
    )
    auth = _controller_authorization(plan, corrupt_state, snapshot, transition, old_sha)
    receipt_path = tmp_path / "recovery-receipt.json"
    result = persist_same_sequence_checkpoint_recovery(
        checkpoint_path=checkpoint_path, intent_path=intent_path,
        snapshot_path=snapshot_path, transition_receipt_path=transition_path,
        archive_path=tmp_path / "archive" / "corrupt-original.json",
        authorization=auth, profile=profile, runtime_plan=plan,
        node_allocation=allocation, recovery_receipt_path=receipt_path,
    )
    assert (tmp_path / "archive" / "corrupt-original.json").read_bytes() == old_bytes
    current_after = json.loads(checkpoint_path.read_text())
    repaired = current_after["run_state"]
    assert repaired["state_digest"] == _digest(repaired, "state_digest")
    assert repaired["run_id"] == corrupt_state["run_id"]
    assert repaired["sequence"] == corrupt_state["sequence"]
    assert repaired["active_gate"] == corrupt_state["active_gate"]
    assert repaired["next_owner"] == corrupt_state["next_owner"]
    assert repaired["typed_next"] == corrupt_state["typed_next"]
    assert result["logical_cursor_changed"] is False
    assert result["recovery_receipt_file_sha256"] == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    assert json.loads(receipt_path.read_text())["authority_granted"] is False
    replay = persist_same_sequence_checkpoint_recovery(
        checkpoint_path=checkpoint_path, intent_path=intent_path,
        snapshot_path=snapshot_path, transition_receipt_path=transition_path,
        archive_path=tmp_path / "archive" / "corrupt-original.json",
        authorization=auth, profile=profile, runtime_plan=plan,
        node_allocation=allocation, recovery_receipt_path=receipt_path,
    )
    assert replay["idempotent_replay"] is True
    assert replay["logical_cursor_changed"] is False


def _recovery_activation_fixture(tmp_path):
    from test_universal_v2_core_isolation import _make_recovery_replan_inputs
    from tools.node_architect.universal_run_controller import create_recovery_replan_cursor_state
    from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile

    profile, plan, allocation, receipt, invalidation, incident, provenance = _make_recovery_replan_inputs()
    successor = create_recovery_replan_cursor_state(
        runtime_plan=plan, node_allocation=allocation, recovery_replan_receipt=receipt,
        stale_evidence_invalidation_record=invalidation, incident_checkpoint_identity=incident,
        requested_restart_gate="UR.G2", recovery_provenance=provenance,
    )
    state = {
        "schema_id": "gwc.universal-run.run-state.v2", "schema_version": 2,
        "run_id": plan["run_id"], "sequence": 14, "predecessor_sequence": 13,
        "active_gate": "UR.G5", "runtime_epoch": plan["runtime_epoch"],
        "runtime_plan_digest": plan["digest"], "node_allocation_id": allocation["node_allocation_id"],
        "execution_refs": {
            "branch": plan["source_binding"]["branch"],
            "node_allocation_id": allocation["node_allocation_id"],
            "node_allocation_ref": "fixture://allocation#record_id=" + allocation["record_id"],
            "candidate_sha": plan["source_binding"]["pre_head_sha"],
            "runtime_plan_digest": plan["digest"],
            "qualification_profile_digest": plan["qualification_profile_digest"],
        },
        "gate_evidence": {"readiness": "STALE_R6"}, "typed_next": "CONTINUE_UNIVERSAL_LANE_REMEDIATION",
        "next_owner": "CONTROLLER", "evidence_gap": [], "consumed_receipts": [],
        "state_digest": "sha256:" + "0" * 64,
    }
    document = {
        "schema_id": "gwc.universal-run.run-state-checkpoint.v2", "schema_version": 2,
        "run_id": state["run_id"], "runtime_plan": plan, "node_allocation": allocation,
        "run_state": state, "sequence": 14, "active_gate": "UR.G5", "next_owner": "CONTROLLER",
    }
    checkpoint = tmp_path / "official-fixture.json"
    old_bytes = (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    checkpoint.write_bytes(old_bytes)
    auth = {
        "schema_id": "gwc.universal-run.recovery-replan-cursor-activation-authorization.v2",
        "schema_version": 2, "decision": "AUTHORIZE",
        "authorized_action": "IMMUTABLE_INTEGRITY_RECOVERY_REPLAN_CURSOR_ACTIVATION",
        "authority_ref": "controller-comment:5747944812:seq109",
        "controller_sequence": 109,
        "controller_body_sha256": "a17f8349ed7a51d62b5ad5d4f629d04a744b93fd61b1508787eb7cfa5c18b26d",
        "run_id": plan["run_id"], "runtime_plan_digest": plan["digest"],
        "candidate_sha": plan["source_binding"]["pre_head_sha"],
        "expected_incident_checkpoint_file_sha256": hashlib.sha256(old_bytes).hexdigest(),
        "incident_sequence": 14, "incident_gate": "UR.G5",
        "recovery_sequence": 15, "recovery_gate": "UR.G2",
        "next_owner": "EXECUTOR", "typed_next": "EXECUTE_Q0_R7_UR_G2_REPLAY_PROBE",
        "recovery_replan_receipt_digest": receipt["receipt_digest"],
        "stale_evidence_invalidation_digest": invalidation["manifest_digest"],
        "authority_granted": False, "executed_effects": [],
    }
    auth["authorization_digest"] = _digest(auth, "authorization_digest")
    return profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth


def test_duplicate_recovery_replan_activation_is_idempotent(tmp_path):
    from tools.node_architect.universal_run_controller import UniversalController
    from tools.node_architect.universal_run_persistence import persist_recovery_replan_cursor_activation
    from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    archive = tmp_path / "archive" / "seq14-corrupt.json"
    generation = tmp_path / "generations" / "seq15-r7.json"
    activation_receipt = tmp_path / "activation-receipt.json"
    result = persist_recovery_replan_cursor_activation(
        checkpoint_path=checkpoint,
        expected_incident_checkpoint_file_sha256=hashlib.sha256(old_bytes).hexdigest(),
        archive_path=archive, generation_path=generation, activation_receipt_path=activation_receipt,
        recovery_cursor_state=successor, authorization=auth, profile=profile,
        runtime_plan=plan, node_allocation=allocation, recovery_replan_receipt=receipt,
        stale_evidence_invalidation_record=invalidation,
    )

    assert archive.read_bytes() == old_bytes
    installed = json.loads(checkpoint.read_text())["run_state"]
    assert installed == successor
    assert installed["sequence"] == 15 and installed["active_gate"] == "UR.G2"
    assert installed["next_owner"] == "EXECUTOR"
    assert installed["authority_granted"] is False and installed["executed_effects"] == []
    UniversalController(profile=load_universal_v2_default_profile(), runtime_plan=plan,
                        run_state=installed, node_allocation=allocation)
    assert json.loads(generation.read_text())["run_state"] == successor
    assert json.loads(activation_receipt.read_text())["receipt_digest"]
    assert result["idempotent_replay"] is False
    replay = persist_recovery_replan_cursor_activation(
        checkpoint_path=checkpoint,
        expected_incident_checkpoint_file_sha256=hashlib.sha256(old_bytes).hexdigest(),
        archive_path=archive, generation_path=generation, activation_receipt_path=activation_receipt,
        recovery_cursor_state=successor, authorization=auth, profile=profile,
        runtime_plan=plan, node_allocation=allocation, recovery_replan_receipt=receipt,
        stale_evidence_invalidation_record=invalidation,
    )
    assert replay["idempotent_replay"] is True


def test_recovery_replan_activation_requires_exact_controller_authorization(tmp_path):
    from tools.node_architect.universal_run_persistence import CheckpointPersistenceError, persist_recovery_replan_cursor_activation

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    auth["typed_next"] = "EXECUTE_UR_G5"
    auth["authorization_digest"] = _digest(auth, "authorization_digest")
    with pytest.raises(CheckpointPersistenceError):
        persist_recovery_replan_cursor_activation(
            checkpoint_path=checkpoint,
            expected_incident_checkpoint_file_sha256=hashlib.sha256(old_bytes).hexdigest(),
            archive_path=tmp_path / "archive" / "seq14.json",
            generation_path=tmp_path / "generation.json", activation_receipt_path=tmp_path / "receipt.json",
            recovery_cursor_state=successor, authorization=auth, profile=profile,
            runtime_plan=plan, node_allocation=allocation, recovery_replan_receipt=receipt,
            stale_evidence_invalidation_record=invalidation,
        )
    assert checkpoint.read_bytes() == old_bytes
    assert not (tmp_path / "archive" / "seq14.json").exists()


def test_recovery_replan_activation_cas_binds_incident_checkpoint_sha(tmp_path):
    from tools.node_architect.universal_run_persistence import CheckpointPersistenceError, persist_recovery_replan_cursor_activation

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    with pytest.raises(CheckpointPersistenceError):
        persist_recovery_replan_cursor_activation(
            checkpoint_path=checkpoint, expected_incident_checkpoint_file_sha256="f" * 64,
            archive_path=tmp_path / "archive" / "seq14.json", generation_path=tmp_path / "generation.json",
            activation_receipt_path=tmp_path / "receipt.json", recovery_cursor_state=successor,
            authorization=auth, profile=profile, runtime_plan=plan, node_allocation=allocation,
            recovery_replan_receipt=receipt, stale_evidence_invalidation_record=invalidation,
        )
    assert checkpoint.read_bytes() == old_bytes
    assert not (tmp_path / "archive" / "seq14.json").exists()


def test_recovery_replan_activation_archives_corrupt_seq14_before_install(tmp_path, monkeypatch):
    from tools.node_architect import universal_run_persistence as persistence

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    archive = tmp_path / "archive" / "seq14.json"
    original_replace = persistence.os.replace
    def guarded_replace(source, destination):
        assert archive.read_bytes() == old_bytes
        return original_replace(source, destination)
    monkeypatch.setattr(persistence.os, "replace", guarded_replace)
    persistence.persist_recovery_replan_cursor_activation(
        checkpoint_path=checkpoint, expected_incident_checkpoint_file_sha256=hashlib.sha256(old_bytes).hexdigest(),
        archive_path=archive, generation_path=tmp_path / "generation.json",
        activation_receipt_path=tmp_path / "receipt.json", recovery_cursor_state=successor,
        authorization=auth, profile=profile, runtime_plan=plan, node_allocation=allocation,
        recovery_replan_receipt=receipt, stale_evidence_invalidation_record=invalidation,
    )


def test_recovery_replan_activation_rejects_r7_candidate_or_receipt_mismatch(tmp_path):
    from tools.node_architect.universal_run_persistence import CheckpointPersistenceError, persist_recovery_replan_cursor_activation

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    receipt["new_candidate_sha"] = "f" * 40
    receipt["receipt_digest"] = _digest(receipt, "receipt_digest")
    auth["recovery_replan_receipt_digest"] = receipt["receipt_digest"]
    auth["authorization_digest"] = _digest(auth, "authorization_digest")
    with pytest.raises(CheckpointPersistenceError):
        persist_recovery_replan_cursor_activation(
            checkpoint_path=checkpoint,
            expected_incident_checkpoint_file_sha256=hashlib.sha256(old_bytes).hexdigest(),
            archive_path=tmp_path / "archive" / "seq14.json", generation_path=tmp_path / "generation.json",
            activation_receipt_path=tmp_path / "receipt.json", recovery_cursor_state=successor,
            authorization=auth, profile=profile, runtime_plan=plan, node_allocation=allocation,
            recovery_replan_receipt=receipt, stale_evidence_invalidation_record=invalidation,
        )
    assert checkpoint.read_bytes() == old_bytes


def test_conflicting_recovery_replan_activation_fails_closed(tmp_path):
    from tools.node_architect.universal_run_persistence import CheckpointPersistenceError, persist_recovery_replan_cursor_activation

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    archive = tmp_path / "archive" / "seq14.json"
    archive.parent.mkdir()
    archive.write_bytes(b"conflicting pre-existing archive")
    with pytest.raises(CheckpointPersistenceError):
        persist_recovery_replan_cursor_activation(
            checkpoint_path=checkpoint,
            expected_incident_checkpoint_file_sha256=hashlib.sha256(old_bytes).hexdigest(),
            archive_path=archive, generation_path=tmp_path / "generation.json",
            activation_receipt_path=tmp_path / "receipt.json", recovery_cursor_state=successor,
            authorization=auth, profile=profile, runtime_plan=plan, node_allocation=allocation,
            recovery_replan_receipt=receipt, stale_evidence_invalidation_record=invalidation,
        )
    assert checkpoint.read_bytes() == old_bytes
    assert archive.read_bytes() == b"conflicting pre-existing archive"


def test_recovery_replan_activation_installs_seq15_ur_g2_generation(tmp_path):
    from tools.node_architect.universal_run_persistence import persist_recovery_replan_cursor_activation

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    generation = tmp_path / "generation.json"
    persist_recovery_replan_cursor_activation(
        checkpoint_path=checkpoint,
        expected_incident_checkpoint_file_sha256=hashlib.sha256(old_bytes).hexdigest(),
        archive_path=tmp_path / "archive" / "seq14.json", generation_path=generation,
        activation_receipt_path=tmp_path / "receipt.json", recovery_cursor_state=successor,
        authorization=auth, profile=profile, runtime_plan=plan, node_allocation=allocation,
        recovery_replan_receipt=receipt, stale_evidence_invalidation_record=invalidation,
    )
    assert json.loads(generation.read_text())["run_state"]["sequence"] == 15
    assert json.loads(generation.read_text())["run_state"]["active_gate"] == "UR.G2"
    assert json.loads(checkpoint.read_text())["run_state"]["next_owner"] == "EXECUTOR"


def test_recovery_replan_activation_readback_is_exact_and_controller_valid(tmp_path):
    from tools.node_architect.universal_run_controller import UniversalController
    from tools.node_architect.universal_run_persistence import persist_recovery_replan_cursor_activation
    from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    persist_recovery_replan_cursor_activation(
        checkpoint_path=checkpoint,
        expected_incident_checkpoint_file_sha256=hashlib.sha256(old_bytes).hexdigest(),
        archive_path=tmp_path / "archive" / "seq14.json", generation_path=tmp_path / "generation.json",
        activation_receipt_path=tmp_path / "receipt.json", recovery_cursor_state=successor,
        authorization=auth, profile=profile, runtime_plan=plan, node_allocation=allocation,
        recovery_replan_receipt=receipt, stale_evidence_invalidation_record=invalidation,
    )
    installed = json.loads(checkpoint.read_text())["run_state"]
    assert installed == successor
    assert installed["state_digest"] == _digest(installed, "state_digest")
    controller = UniversalController(profile=load_universal_v2_default_profile(), runtime_plan=plan,
                                     run_state=installed, node_allocation=allocation)
    assert controller.assign_current_action()["actor"] == "EXECUTOR"


def test_recovery_replan_activation_does_not_execute_ur_g2(tmp_path):
    from tools.node_architect.universal_run_persistence import persist_recovery_replan_cursor_activation

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    result = persist_recovery_replan_cursor_activation(
        checkpoint_path=checkpoint,
        expected_incident_checkpoint_file_sha256=hashlib.sha256(old_bytes).hexdigest(),
        archive_path=tmp_path / "archive" / "seq14.json", generation_path=tmp_path / "generation.json",
        activation_receipt_path=tmp_path / "receipt.json", recovery_cursor_state=successor,
        authorization=auth, profile=profile, runtime_plan=plan, node_allocation=allocation,
        recovery_replan_receipt=receipt, stale_evidence_invalidation_record=invalidation,
    )
    installed = json.loads(checkpoint.read_text())["run_state"]
    assert result["idempotent_replay"] is False
    assert installed["active_gate"] == "UR.G2" and installed["typed_next"] == "EXECUTE_Q0_R7_UR_G2_REPLAY_PROBE"
    assert installed["authority_granted"] is False and installed["executed_effects"] == []
    assert installed["consumed_receipts"] == [] and installed["evidence_gap"] == ["EXECUTION_RECEIPT"]


def test_recovery_replan_activation_repairs_missing_receipt_after_installed_checkpoint(tmp_path):
    from tools.node_architect.universal_run_persistence import persist_recovery_replan_cursor_activation

    profile, plan, allocation, receipt, invalidation, successor, checkpoint, old_bytes, auth = _recovery_activation_fixture(tmp_path)
    archive = tmp_path / "archive" / "seq14.json"
    generation = tmp_path / "generation.json"
    activation_receipt = tmp_path / "receipt.json"
    kwargs = {
        "checkpoint_path": checkpoint,
        "expected_incident_checkpoint_file_sha256": hashlib.sha256(old_bytes).hexdigest(),
        "archive_path": archive, "generation_path": generation,
        "activation_receipt_path": activation_receipt, "recovery_cursor_state": successor,
        "authorization": auth, "profile": profile, "runtime_plan": plan,
        "node_allocation": allocation, "recovery_replan_receipt": receipt,
        "stale_evidence_invalidation_record": invalidation,
    }
    first = persist_recovery_replan_cursor_activation(**kwargs)
    activation_receipt.unlink()
    replay = persist_recovery_replan_cursor_activation(**kwargs)
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert json.loads(activation_receipt.read_text())["checkpoint_readback_file_sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()
