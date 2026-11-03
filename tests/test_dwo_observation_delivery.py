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
