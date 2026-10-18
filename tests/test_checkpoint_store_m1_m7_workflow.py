"""SCRUM-841 checkpoint/store binding for the M1-M7 workflow (P4).

Verifies the run-bound, CAS/fencing-safe, idempotent persistence contract used
by the selected LangGraph workflow: exact persisted state readback, strict CAS
revision enforcement, unknown-outcome reconciliation, and the host-side
run-bound/scope guard on the checkpoint path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.node_architect.checkpoint_store import (
    CheckpointConflict,
    CheckpointInput,
    load_store,
    persist_to_file,
    reconcile_unknown_outcome,
    replay_checkpoint,
    validate_readback,
)
from tools.node_architect.agent_runtime_entrypoint import _prepare_m1_m7_checkpoint

REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BASE = "82a64d30bea55287855d5c591d0b9338f32f450f"
BRANCH = "hermes/SCRUM-841-m1-m7-langgraph-r1"
SCOPE = "sha256:" + "a" * 64
NODE = "scrum841-m1-m7-workflow"


def _item(run_id: str = "g1-841-checkpoint", revision: int = 0, **overrides):
    return CheckpointInput(
        task_id="SCRUM-841", run_id=run_id, node_id=NODE,
        repository=REPOSITORY, branch=BRANCH, base_sha=BASE, head_sha=BASE,
        scope_hash=SCOPE, state={"current_activity": "M1", "run_id": run_id},
        expected_revision=revision,
        graph_revision="scrum841-m1-m7-agent-workflow-r1",
        **overrides,
    )


def test_persist_and_readback_round_trip(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    item = _item()
    persist_to_file(path, item)
    store = load_store(path)
    result = validate_readback(store, item)
    assert result["outcome"] == "PASS"
    assert store["revision"] == 1
    record = replay_checkpoint(store, "SCRUM-841", item.run_id, NODE)
    assert record["state"]["current_activity"] == "M1"
    assert record["scope_hash"] == SCOPE
    assert record["task_id"] == "SCRUM-841"
    assert record["run_id"] == item.run_id


def test_cas_revision_mismatch_fails_closed(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    persist_to_file(path, _item(revision=0))
    with pytest.raises(CheckpointConflict):
        persist_to_file(path, _item(revision=0))  # baseline moved to 1


def test_unknown_outcome_reconciles_to_known_state(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    persist_to_file(path, _item(run_id="g1-841-reconcile"))
    store = load_store(path)
    out = reconcile_unknown_outcome(store, _item(run_id="g1-841-reconcile"))
    assert out["outcome"] == "KNOWN_STATE"
    assert out["reasons"] == []


def test_corrupt_store_digest_is_unknown_outcome(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    persist_to_file(path, _item(run_id="g1-841-tamper"))
    store = load_store(path)
    store["revision"] = 99
    out = reconcile_unknown_outcome(store, _item(run_id="g1-841-tamper"))
    assert out["outcome"] == "UNKNOWN_OUTCOME"
    assert set(out["reasons"]) & {"INVALID_REVISION", "REVISION_CHECKPOINT_MISMATCH", "STORE_DIGEST_MISMATCH"}


def test_prepare_checkpoint_enforces_run_bound_store_ref(tmp_path: Path):
    root = tmp_path / "repo"
    operation = {
        "run_id": "g1-841-cp", "task_id": "SCRUM-841", "repository": REPOSITORY,
        "working_branch": BRANCH, "base_sha": BASE, "head_sha": BASE,
        "scope_hash": SCOPE,
    }
    with pytest.raises(ValueError, match="CHECKPOINT_STORE_PATH_NOT_RUN_BOUND"):
        _prepare_m1_m7_checkpoint(
            root=root,
            selection={
                "checkpoint_store_ref": ".gwc/tasks/SCRUM-841/g2/checkpoints/other.json",
                "checkpoint_expected_revision": 0,
            },
            operation=operation,
        )


def test_prepare_checkpoint_rejects_path_outside_task_scope(tmp_path: Path):
    root = tmp_path / "repo"
    operation = {
        "run_id": "g1-841-cp", "task_id": "SCRUM-841", "repository": REPOSITORY,
        "working_branch": BRANCH, "base_sha": BASE, "head_sha": BASE,
        "scope_hash": SCOPE,
    }
    with pytest.raises(ValueError):
        _prepare_m1_m7_checkpoint(
            root=root,
            selection={
                "checkpoint_store_ref": ".gwc/tasks/SCRUM-841/g2/checkpoints/../other.json",
                "checkpoint_expected_revision": 0,
            },
            operation=operation,
        )