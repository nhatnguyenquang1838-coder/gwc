"""Durable non-blocking GWC -> DWO observation publisher."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Mapping

from tools.node_architect import delivery_outbox
from tools.node_architect.dwo_observation_transport import (
    DESTINATION_ID, EVENT_SOURCE, DwoTransportError, send_event, verify_ack_signature,
)
from tools.node_architect.observation_event import (
    build_controller_decision_observation_event,
    build_observation_event,
    canonical_digest,
    observation_event_digest,
)

PROJECTION_TARGET = "dwo-observation"


def _publish_event(
    *,
    outbox_path: Path,
    event: Mapping[str, Any],
    endpoint: str,
    machine_secret: str,
    key_id: str,
    worker_id: str,
    source_id: str,
    delivery_generation: int = 1,
    destination_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
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
        event_id=str(event["event_id"]),
        canonical_state_digest=str(event["source_digest"]),
        event_payload_digest=event_payload_digest,
        destination_policy_digest=canonical_digest(policy),
        destination_id=DESTINATION_ID,
        delivery_generation=delivery_generation,
    )
    key = {
        "projection_target": PROJECTION_TARGET,
        "event_source": EVENT_SOURCE,
        "event_id": str(event["event_id"]),
        "canonical_state_digest": str(event["source_digest"]),
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
            source_id=source_id,
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
        return {"status": "DELIVERED", "event": dict(event), "outbox": confirmed, "ack": ack}
    except (DwoTransportError, delivery_outbox.OutboxConflict) as exc:
        try:
            delivery_outbox.transition(
                outbox_path,
                worker_id=worker_id,
                to_state=delivery_outbox.RETRY_SCHEDULED,
                reason_class=type(exc).__name__,
                **key,
            )
        except delivery_outbox.OutboxConflict:
            pass
        return {"status": "RETRY_SCHEDULED", "event": dict(event), "reason": str(exc)}


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
    source_id: str = "gwc-main",
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
    return _publish_event(
        outbox_path=outbox_path,
        event=event,
        endpoint=endpoint,
        machine_secret=machine_secret,
        key_id=key_id,
        worker_id=worker_id,
        source_id=source_id,
        delivery_generation=delivery_generation,
        destination_policy=destination_policy,
    )


def publish_controller_decision(
    *,
    outbox_path: Path,
    decision: Mapping[str, Any],
    source_repository: str,
    source_sha: str,
    runtime_epoch: str,
    endpoint: str,
    machine_secret: str,
    key_id: str,
    worker_id: str,
    source_id: str,
    node_id: str | None = None,
    emitted_at: str | None = None,
) -> dict[str, Any]:
    """Project one already-validated native Controller transition."""
    event = build_controller_decision_observation_event(
        decision,
        source_repository=source_repository,
        source_sha=source_sha,
        runtime_epoch=runtime_epoch,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        node_id=node_id,
    )
    return _publish_event(
        outbox_path=outbox_path,
        event=event,
        endpoint=endpoint,
        machine_secret=machine_secret,
        key_id=key_id,
        worker_id=worker_id,
        source_id=source_id,
    )


def observe_controller_decision_from_env(
    *,
    decision: Mapping[str, Any],
    runtime_plan: Mapping[str, Any],
    runtime_epoch: str,
    node_id: str | None,
) -> dict[str, Any]:
    """Optionally project a native decision without owning or blocking its cursor."""
    env_names = {
        "endpoint": "GWC_DWO_OBSERVATION_ENDPOINT",
        "machine_secret": "GWC_DWO_MACHINE_SECRET",
        "key_id": "GWC_DWO_KEY_ID",
        "source_id": "GWC_DWO_SOURCE_ID",
        "outbox_path": "GWC_DWO_OUTBOX_PATH",
    }
    values = {key: os.getenv(env_name, "") for key, env_name in env_names.items()}
    supplied = [key for key, value in values.items() if value]
    if not supplied:
        return {"status": "DISABLED", "authority_granted": False, "executed_effects": []}
    missing = sorted(key for key, value in values.items() if not value)
    if missing:
        return {
            "status": "DEGRADED",
            "reason_code": "DWO_OBSERVATION_CONFIG_INCOMPLETE",
            "missing": missing,
            "authority_granted": False,
            "executed_effects": [],
        }

    source = runtime_plan.get("source_binding")
    if not isinstance(source, Mapping):
        return {
            "status": "DEGRADED",
            "reason_code": "DWO_OBSERVATION_SOURCE_BINDING_MISSING",
            "authority_granted": False,
            "executed_effects": [],
        }
    try:
        result = publish_controller_decision(
            outbox_path=Path(values["outbox_path"]),
            decision=decision,
            source_repository=str(source["repository"]),
            source_sha=str(source["pre_head_sha"]),
            runtime_epoch=runtime_epoch,
            endpoint=values["endpoint"],
            machine_secret=values["machine_secret"],
            key_id=values["key_id"],
            worker_id="dwo-observer:" + str(decision.get("decision_subject", {}).get("run_id", "unknown")),
            source_id=values["source_id"],
            node_id=node_id,
        )
    except Exception as exc:
        return {
            "status": "DEGRADED",
            "reason_code": "DWO_OBSERVATION_PROJECTION_FAILED",
            "error_class": type(exc).__name__,
            "authority_granted": False,
            "executed_effects": [],
        }
    return {**result, "authority_granted": False, "executed_effects": []}
