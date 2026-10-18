"""SCRUM-841 NodeEvidenceLedger binding for the M1-M7 workflow (P4).

Verifies the canonical evidence ledger records M1-M7 workflow state as exact,
replay-safe, task/run/node-bound evidence: idempotent replay, digest chain
integrity, binding identity, and complete node evidence emission.
"""
from __future__ import annotations

from pathlib import Path

from tools.node_architect.node_evidence_ledger import (
    EvidenceConflict,
    NodeEvidenceLedger,
    RECORD_SEQUENCE,
    emit_complete_node_evidence,
)

REPOSITORY = "nhatnguyenquang1838-coder/gwc"
BASE = "82a64d30bea55287855d5c591d0b9338f32f450f"
BRANCH = "hermes/SCRUM-841-m1-m7-langgraph-r1"
SCOPE = "sha256:" + "a" * 64
TASK = "SCRUM-841"
RUN = "g1-841-ledger"
NODE = "scrum841-m1-m7-workflow"
KEY = "op-841:M1:M5:write-1"


def _ledger(root: Path) -> NodeEvidenceLedger:
    return NodeEvidenceLedger(
        root=root, task_id=TASK, run_id=RUN, node_id=NODE,
        repository=REPOSITORY, branch=BRANCH, base_sha=BASE, head_sha=BASE,
        scope_hash=SCOPE, idempotency_key=KEY,
        occurred_at="2026-10-18T05:00:00Z",
    )


def _evidence() -> dict[str, dict]:
    return {
        "node-start": {"status": "START", "current_activity": "M1"},
        "node-decision": {"decision": "M1_CONTINUE", "reason_code": "M1_OBSERVATION_ACCEPTED"},
        "node-result": {"status": "PASS", "current_activity": "M7"},
        "node-readback": {"status": "VERIFIED", "readback_digest": "sha256:" + "2" * 64},
        "checkpoint": {"revision": 1, "current_activity": "M7"},
        "next-route-decision": {"next_node": None, "next_action": "complete"},
    }


def test_ledger_binds_run_identity_and_scope(tmp_path: Path):
    ledger = _ledger(tmp_path)
    record = ledger.record_start({"status": "START"})
    assert record["task_id"] == TASK
    assert record["run_id"] == RUN
    assert record["node_id"] == NODE
    assert record["repository"] == REPOSITORY
    assert record["branch"] == BRANCH
    assert record["base_sha"] == BASE
    assert record["head_sha"] == BASE
    assert record["scope_hash"] == SCOPE
    assert record["idempotency_key"] == KEY
    assert record["record_digest"].startswith("sha256:")


def test_complete_node_evidence_emits_all_sequence_records(tmp_path: Path):
    ledger = _ledger(tmp_path)
    result = emit_complete_node_evidence(ledger=ledger, evidence=_evidence())
    records = result["records"]
    assert set(records) == set(RECORD_SEQUENCE)
    summary = result["summary"]
    assert summary["node_id"] == NODE
    assert len([p for p in summary["paths"] if Path(p).is_file()]) == len(RECORD_SEQUENCE) + 1  # records + events


def test_exact_replay_is_idempotent(tmp_path: Path):
    ledger = _ledger(tmp_path)
    first = ledger.record_result({"status": "PASS", "current_activity": "M7"})
    second = ledger.record_result({"status": "PASS", "current_activity": "M7"})
    assert first == second
    assert len(ledger.events_path.read_text(encoding="utf-8").splitlines()) == 1


def test_conflicting_replay_fails_closed(tmp_path: Path):
    ledger = _ledger(tmp_path)
    ledger.record_result({"status": "PASS"})
    try:
        ledger.record_result({"status": "FAIL"})
    except EvidenceConflict:
        pass
    else:
        raise AssertionError("conflicting replay must raise EvidenceConflict")


def test_digest_chain_and_event_sequence(tmp_path: Path):
    ledger = _ledger(tmp_path)
    record = ledger.record_checkpoint({"revision": 1, "current_activity": "M7"})
    assert record["artifact_type"] == "checkpoint"
    events = ledger.events_path.read_text(encoding="utf-8").splitlines()
    assert len(events) == 1
    event = __import__("json").loads(events[0])
    assert event["task_id"] == TASK
    assert event["node_id"] == NODE
    assert event["event_digest"].startswith("sha256:")