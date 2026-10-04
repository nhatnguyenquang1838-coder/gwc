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
