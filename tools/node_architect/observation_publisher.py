"""Durable non-blocking GWC -> DWO observation publisher."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from tools.node_architect import delivery_outbox
from tools.node_architect.dwo_observation_transport import (
    DESTINATION_ID, EVENT_SOURCE, DwoTransportError, send_event, verify_ack_signature,
)
from tools.node_architect.observation_event import (
    build_observation_event, canonical_digest, observation_event_digest,
)

PROJECTION_TARGET = "dwo-observation"


def publish_run_state(
    *,
    outbox_path: Path,
    run_state: Mapping[str, Any],
    source_repository: str,
    source_sha: str,
    runtime_epoch: str,
    endpoint: str,
    machine_secret: str,
    key_id: str,
    worker_id: str,
    delivery_generation: int = 1,
    destination_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deliver one canonical RunStateRecord without blocking the GWC lifecycle."""
    event = build_observation_event(
        run_state,
        source_repository=source_repository,
        source_sha=source_sha,
        runtime_epoch=runtime_epoch,
    )
    event_payload_digest = observation_event_digest(event)
    policy = dict(destination_policy or {
        "destination_id": DESTINATION_ID,
        "endpoint": endpoint,
        "auth": "hmac-sha256",
        "read_only_projection": True,
    })
    rec = delivery_outbox.enqueue(
        outbox_path,
        projection_target=PROJECTION_TARGET,
        event_source=EVENT_SOURCE,
        event_id=event["event_id"],
        canonical_state_digest=event["source_digest"],
        event_payload_digest=event_payload_digest,
        destination_policy_digest=canonical_digest(policy),
        destination_id=DESTINATION_ID,
        delivery_generation=delivery_generation,
    )
    key = {
        "projection_target": PROJECTION_TARGET,
        "event_source": EVENT_SOURCE,
        "event_id": event["event_id"],
        "canonical_state_digest": event["source_digest"],
        "delivery_generation": delivery_generation,
    }
    delivery_outbox.acquire_lease(outbox_path, worker_id=worker_id, **key)
    try:
        ack, request_digest, payload_digest = send_event(
            endpoint,
            event=event,
            secret=machine_secret,
            key_id=key_id,
            delivery_generation=delivery_generation,
        )
        delivery_outbox.record_attempt(
            outbox_path,
            semantic_event_id=rec["semantic_event_id"],
            delivery_generation=delivery_generation,
            destination_id=DESTINATION_ID,
            attempt_no=1,
            request_digest=request_digest,
            response_class="2xx",
            ack_binding=ack,
        )
        if payload_digest != event_payload_digest:
            raise delivery_outbox.OutboxConflict("REQUEST_PAYLOAD_DIGEST_MISMATCH")
        confirmed = delivery_outbox.confirm_ack(
            outbox_path,
            ack=ack,
            worker_id=worker_id,
            verifier=lambda value: verify_ack_signature(machine_secret, value),
        )
        return {"status": "DELIVERED", "event": event, "outbox": confirmed, "ack": ack}
    except (DwoTransportError, delivery_outbox.OutboxConflict) as exc:
        try:
            delivery_outbox.transition(
                outbox_path, worker_id=worker_id,
                to_state=delivery_outbox.RETRY_SCHEDULED,
                reason_class=type(exc).__name__, **key,
            )
        except delivery_outbox.OutboxConflict:
            pass
        return {"status": "RETRY_SCHEDULED", "event": event, "reason": str(exc)}
