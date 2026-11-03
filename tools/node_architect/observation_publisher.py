"""Durable non-blocking GWC -> DWO observation publisher.

Observation is downstream projection only. Delivery failure never owns the
Universal cursor. Events are persisted before network send and are drained in
source sequence order per run so a later transition cannot overtake an earlier
retry after a receiver outage/restart.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from tools.node_architect import delivery_outbox
from tools.node_architect.dwo_observation_transport import (
    DESTINATION_ID,
    EVENT_SOURCE,
    DwoTransportError,
    send_event,
    verify_ack_signature,
)
from tools.node_architect.observation_event import (
    build_controller_decision_observation_event,
    build_observation_event,
    canonical_digest,
    observation_event_digest,
)

PROJECTION_TARGET = "dwo-observation"
DEFAULT_DRAIN_LIMIT = 32


def _default_policy(endpoint: str) -> dict[str, Any]:
    return {
        "destination_id": DESTINATION_ID,
        "endpoint": endpoint,
        "auth": "hmac-sha256",
        "read_only_projection": True,
    }


def _env_config() -> tuple[dict[str, str], list[str], list[str]]:
    env_names = {
        "endpoint": "GWC_DWO_OBSERVATION_ENDPOINT",
        "machine_secret": "GWC_DWO_MACHINE_SECRET",
        "key_id": "GWC_DWO_KEY_ID",
        "source_id": "GWC_DWO_SOURCE_ID",
        "outbox_path": "GWC_DWO_OUTBOX_PATH",
    }
    values = {key: os.getenv(env_name, "") for key, env_name in env_names.items()}
    supplied = [key for key, value in values.items() if value]
    missing = sorted(key for key, value in values.items() if not value)
    return values, supplied, missing


def _row_key(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "projection_target": str(row["projection_target"]),
        "event_source": row.get("event_source"),
        "event_id": str(row["event_id"]),
        "canonical_state_digest": str(row["canonical_state_digest"]),
        "delivery_generation": int(row["delivery_generation"]),
    }


def _deliver_row(
    *,
    outbox_path: Path,
    row: Mapping[str, Any],
    endpoint: str,
    machine_secret: str,
    key_id: str,
    source_id: str,
    worker_id: str,
) -> dict[str, Any]:
    """Deliver one already-durable row under a fenced lease."""
    policy_digest = canonical_digest(_default_policy(endpoint))
    if row.get("destination_policy_digest") != policy_digest:
        return {
            "status": "BLOCKED",
            "reason_code": "DWO_OBSERVATION_DESTINATION_POLICY_DRIFT",
            "event_id": row.get("event_id"),
        }

    payload_json = row.get("event_payload_json")
    if not isinstance(payload_json, str) or not payload_json:
        return {
            "status": "BLOCKED",
            "reason_code": "DWO_OBSERVATION_DURABLE_PAYLOAD_MISSING",
            "event_id": row.get("event_id"),
        }
    try:
        event = json.loads(payload_json)
    except json.JSONDecodeError:
        return {
            "status": "BLOCKED",
            "reason_code": "DWO_OBSERVATION_DURABLE_PAYLOAD_INVALID",
            "event_id": row.get("event_id"),
        }
    if not isinstance(event, dict):
        return {
            "status": "BLOCKED",
            "reason_code": "DWO_OBSERVATION_DURABLE_PAYLOAD_INVALID",
            "event_id": row.get("event_id"),
        }

    key = _row_key(row)
    try:
        delivery_outbox.acquire_lease(outbox_path, worker_id=worker_id, **key)
    except delivery_outbox.OutboxConflict as exc:
        return {
            "status": "SKIPPED",
            "reason_code": str(exc),
            "event_id": row.get("event_id"),
        }

    attempt_no = int(row.get("attempt_no") or 0) + 1
    try:
        ack, request_digest, payload_digest = send_event(
            endpoint,
            event=event,
            secret=machine_secret,
            key_id=key_id,
            delivery_generation=int(row["delivery_generation"]),
            source_id=source_id,
        )
        delivery_outbox.record_attempt(
            outbox_path,
            semantic_event_id=str(row["semantic_event_id"]),
            delivery_generation=int(row["delivery_generation"]),
            destination_id=DESTINATION_ID,
            attempt_no=attempt_no,
            request_digest=request_digest,
            response_class="2xx",
            ack_binding=ack,
        )
        if payload_digest != row.get("event_payload_digest"):
            raise delivery_outbox.OutboxConflict("REQUEST_PAYLOAD_DIGEST_MISMATCH")
        confirmed = delivery_outbox.confirm_ack(
            outbox_path,
            ack=ack,
            worker_id=worker_id,
            verifier=lambda value: verify_ack_signature(machine_secret, value),
        )
        return {
            "status": "DELIVERED",
            "event_id": row.get("event_id"),
            "source_run_id": row.get("source_run_id"),
            "source_sequence": row.get("source_sequence"),
            "outbox": confirmed,
            "ack": ack,
        }
    except (DwoTransportError, delivery_outbox.OutboxConflict) as exc:
        try:
            retry = delivery_outbox.transition(
                outbox_path,
                worker_id=worker_id,
                to_state=delivery_outbox.RETRY_SCHEDULED,
                reason_class=type(exc).__name__,
                **key,
            )
        except delivery_outbox.OutboxConflict:
            retry = {"state": "UNKNOWN"}
        return {
            "status": "RETRY_SCHEDULED",
            "event_id": row.get("event_id"),
            "source_run_id": row.get("source_run_id"),
            "source_sequence": row.get("source_sequence"),
            "reason": str(exc),
            "outbox": retry,
        }


def drain_observation_outbox(
    *,
    outbox_path: Path,
    endpoint: str,
    machine_secret: str,
    key_id: str,
    source_id: str,
    worker_id: str,
    max_items: int = DEFAULT_DRAIN_LIMIT,
) -> dict[str, Any]:
    """Recover and drain durable rows without same-run sequence overtaking."""
    delivery_outbox.init_store(outbox_path)
    results: list[dict[str, Any]] = []
    for _ in range(max(1, int(max_items))):
        row = delivery_outbox.next_ready_ordered(outbox_path)
        if row is None:
            break
        result = _deliver_row(
            outbox_path=outbox_path,
            row=row,
            endpoint=endpoint,
            machine_secret=machine_secret,
            key_id=key_id,
            source_id=source_id,
            worker_id=worker_id,
        )
        results.append(result)
        if result["status"] == "BLOCKED":
            # The same row would remain first forever; stop without spinning.
            break
    return {
        "status": "DRAINED" if results else "IDLE",
        "attempted": len(results),
        "results": results,
    }


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
    """Persist the event, then drain the oldest ready event(s) for all runs."""
    event_payload_digest = observation_event_digest(event)
    policy = dict(destination_policy or _default_policy(endpoint))
    delivery_outbox.init_store(outbox_path)
    try:
        delivery_outbox.enqueue(
            outbox_path,
            projection_target=PROJECTION_TARGET,
            event_source=EVENT_SOURCE,
            event_id=str(event["event_id"]),
            canonical_state_digest=str(event["source_digest"]),
            event_payload_digest=event_payload_digest,
            event_payload=dict(event),
            source_run_id=str(event["run_id"]),
            source_sequence=int(event["sequence"]),
            destination_policy_digest=canonical_digest(policy),
            destination_id=DESTINATION_ID,
            delivery_generation=delivery_generation,
        )
    except delivery_outbox.OutboxConflict as exc:
        if str(exc) != "DELIVERY_IDENTITY_ALREADY_ENQUEUED":
            raise

    drain = drain_observation_outbox(
        outbox_path=outbox_path,
        endpoint=endpoint,
        machine_secret=machine_secret,
        key_id=key_id,
        source_id=source_id,
        worker_id=worker_id,
    )
    row = delivery_outbox.get_record(
        outbox_path,
        projection_target=PROJECTION_TARGET,
        event_source=EVENT_SOURCE,
        event_id=str(event["event_id"]),
        canonical_state_digest=str(event["source_digest"]),
        delivery_generation=delivery_generation,
    )
    state = row.get("state") if isinstance(row, Mapping) else None
    if state == delivery_outbox.ACK_CONFIRMED:
        return {"status": "DELIVERED", "event": dict(event), "outbox": dict(row), "drain": drain}
    return {
        "status": "QUEUED",
        "event": dict(event),
        "outbox": dict(row) if isinstance(row, Mapping) else None,
        "drain": drain,
    }


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


def _disabled_or_incomplete() -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    values, supplied, missing = _env_config()
    if not supplied:
        return None, {"status": "DISABLED", "authority_granted": False, "executed_effects": []}
    if missing:
        return None, {
            "status": "DEGRADED",
            "reason_code": "DWO_OBSERVATION_CONFIG_INCOMPLETE",
            "missing": missing,
            "authority_granted": False,
            "executed_effects": [],
        }
    return values, None


def drain_observation_outbox_from_env(*, max_items: int = DEFAULT_DRAIN_LIMIT) -> dict[str, Any]:
    """Drain durable observation rows after process restart or on a sidecar tick."""
    values, early = _disabled_or_incomplete()
    if early is not None:
        return early
    assert values is not None
    try:
        result = drain_observation_outbox(
            outbox_path=Path(values["outbox_path"]),
            endpoint=values["endpoint"],
            machine_secret=values["machine_secret"],
            key_id=values["key_id"],
            source_id=values["source_id"],
            worker_id=os.getenv("GWC_DWO_WORKER_ID", f"dwo-observation-worker:{os.getpid()}"),
            max_items=max_items,
        )
    except Exception as exc:
        return {
            "status": "DEGRADED",
            "reason_code": "DWO_OBSERVATION_DRAIN_FAILED",
            "error_class": type(exc).__name__,
            "authority_granted": False,
            "executed_effects": [],
        }
    return {**result, "authority_granted": False, "executed_effects": []}


def observe_run_state_from_env(
    *,
    run_state: Mapping[str, Any],
    runtime_plan: Mapping[str, Any],
    runtime_epoch: str,
    node_id: str | None,
) -> dict[str, Any]:
    """Observe canonical genesis/state materialization when runtime config exists."""
    values, early = _disabled_or_incomplete()
    if early is not None:
        return early
    assert values is not None
    source = runtime_plan.get("source_binding")
    if not isinstance(source, Mapping):
        return {
            "status": "DEGRADED",
            "reason_code": "DWO_OBSERVATION_SOURCE_BINDING_MISSING",
            "authority_granted": False,
            "executed_effects": [],
        }
    try:
        result = publish_run_state(
            outbox_path=Path(values["outbox_path"]),
            run_state=run_state,
            source_repository=str(source["repository"]),
            source_sha=str(source["pre_head_sha"]),
            runtime_epoch=runtime_epoch,
            endpoint=values["endpoint"],
            machine_secret=values["machine_secret"],
            key_id=values["key_id"],
            worker_id="dwo-observer:" + str(run_state.get("run_id", "unknown")),
            source_id=values["source_id"],
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


def observe_controller_decision_from_env(
    *,
    decision: Mapping[str, Any],
    runtime_plan: Mapping[str, Any],
    runtime_epoch: str,
    node_id: str | None,
) -> dict[str, Any]:
    """Observe a canonical Controller transition without owning its cursor."""
    values, early = _disabled_or_incomplete()
    if early is not None:
        return early
    assert values is not None
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
