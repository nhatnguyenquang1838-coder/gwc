import time
from pathlib import Path

from tools.node_architect import delivery_outbox
from tools.node_architect.dwo_observation_transport import ack_signature, verify_ack_signature


def _rec():
    return {
        "projection_target":"dwo-observation",
        "event_source":"gwc.node-architect.dwo-observation.v1.0",
        "event_id":"evt-1",
        "canonical_state_digest":"sha256:"+"a"*64,
        "event_payload_digest":"sha256:"+"b"*64,
        "destination_policy_digest":"sha256:"+"c"*64,
        "destination_id":"dwo-observation-v2",
        "delivery_generation":1,
    }


def _prepared(path: Path):
    delivery_outbox.init_store(path)
    rec = _rec()
    result = delivery_outbox.enqueue(path, **rec)
    key = {k:rec[k] for k in ("projection_target","event_source","event_id","canonical_state_digest","delivery_generation")}
    delivery_outbox.acquire_lease(path, worker_id="w1", **key)
    request_digest = "sha256:"+"d"*64
    delivery_outbox.record_attempt(
        path, semantic_event_id=result["semantic_event_id"], delivery_generation=1,
        destination_id=rec["destination_id"], attempt_no=1, request_digest=request_digest,
        response_class="2xx",
    )
    return rec, request_digest


def test_authenticated_ack_can_confirm(tmp_path: Path):
    path = tmp_path/"outbox.sqlite"
    rec, request_digest = _prepared(path)
    secret = "x"*32
    ack = {
        "destination_id":rec["destination_id"], "event_source":rec["event_source"],
        "event_id":rec["event_id"], "delivery_generation":1,
        "request_digest":request_digest, "payload_digest":rec["event_payload_digest"],
        "created":int(time.time()), "raw_event_id":1, "projection_ordinal":1,
        "status":"COMMITTED",
    }
    ack["signature_proof"] = ack_signature(secret, ack)
    confirmed = delivery_outbox.confirm_ack(
        path, ack=ack, worker_id="w1",
        verifier=lambda value: verify_ack_signature(secret, value),
    )
    assert confirmed["state"] == "ACK_CONFIRMED"


def test_bad_receiver_signature_is_rejected(tmp_path: Path):
    import pytest
    path = tmp_path/"outbox.sqlite"
    rec, request_digest = _prepared(path)
    ack = {
        "destination_id":rec["destination_id"], "event_source":rec["event_source"],
        "event_id":rec["event_id"], "delivery_generation":1,
        "request_digest":request_digest, "payload_digest":rec["event_payload_digest"],
        "created":int(time.time()), "raw_event_id":1, "projection_ordinal":1,
        "status":"COMMITTED", "signature_proof":"hmac-sha256:"+"0"*64,
    }
    with pytest.raises(delivery_outbox.OutboxConflict, match="ACK_NOT_AUTHENTICATED"):
        delivery_outbox.confirm_ack(
            path, ack=ack, worker_id="w1",
            verifier=lambda value: verify_ack_signature("x"*32, value),
        )



def test_ordered_outbox_blocks_later_sequence_while_prior_retry_waits(tmp_path: Path):
    from tools.node_architect.observation_event import canonical_digest

    path = tmp_path / "ordered.sqlite"
    delivery_outbox.init_store(path)

    def enqueue(run_id: str, seq: int, event_id: str):
        payload = {"run_id": run_id, "sequence": seq, "event_id": event_id}
        return delivery_outbox.enqueue(
            path,
            projection_target="dwo-observation",
            event_source="gwc.node-architect.dwo-observation.v1.0",
            event_id=event_id,
            canonical_state_digest="sha256:" + f"{seq:064x}",
            event_payload_digest=canonical_digest(payload),
            event_payload=payload,
            source_run_id=run_id,
            source_sequence=seq,
            destination_policy_digest="sha256:" + "c" * 64,
            destination_id="dwo-observation-v2",
            backoff_ms=60_000,
            jitter_ms=0,
        )

    enqueue("R1", 2, "R1:2")
    enqueue("R1", 3, "R1:3")

    first = delivery_outbox.next_ready_ordered(path)
    assert first["source_run_id"] == "R1"
    assert first["source_sequence"] == 2
    key = {k:first[k] for k in (
        "projection_target","event_source","event_id",
        "canonical_state_digest","delivery_generation",
    )}
    delivery_outbox.acquire_lease(path, worker_id="w1", **key)
    delivery_outbox.transition(
        path, worker_id="w1", to_state=delivery_outbox.RETRY_SCHEDULED,
        reason_class="receiver-down", **key,
    )

    # seq=3 is ready by its own timer but MUST remain blocked behind seq=2.
    assert delivery_outbox.next_ready_ordered(path) is None

    # A different run is independent and may still progress.
    enqueue("R2", 1, "R2:1")
    other = delivery_outbox.next_ready_ordered(path)
    assert other["source_run_id"] == "R2"
    assert other["source_sequence"] == 1


def test_existing_outbox_store_is_upgraded_with_durable_payload_columns(tmp_path: Path):
    import sqlite3

    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE delivery_outbox (
            projection_target TEXT NOT NULL,
            event_source TEXT,
            event_id TEXT NOT NULL,
            canonical_state_digest TEXT NOT NULL,
            delivery_generation INTEGER NOT NULL DEFAULT 1,
            event_payload_digest TEXT NOT NULL,
            destination_policy_digest TEXT NOT NULL,
            destination_id TEXT NOT NULL,
            state TEXT NOT NULL,
            attempt_no INTEGER NOT NULL DEFAULT 0,
            next_attempt_at REAL,
            reason_class TEXT,
            max_attempts INTEGER NOT NULL,
            max_age_s INTEGER NOT NULL,
            backoff_ms INTEGER NOT NULL,
            jitter_ms INTEGER NOT NULL,
            lease_holder TEXT,
            lease_expires_at REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            lineage_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (projection_target, event_source, event_id, canonical_state_digest, delivery_generation)
        );
        """)
    delivery_outbox.init_store(path)
    with sqlite3.connect(path) as conn:
        names = {row[1] for row in conn.execute("PRAGMA table_info(delivery_outbox)")}
    assert {"event_payload_json", "source_run_id", "source_sequence"} <= names
