"""Machine-authenticated DWO observation transport.

GWC owns no Supabase credential. It talks only to the DWO ingestion boundary
with a non-production HMAC credential supplied at runtime.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any, Mapping

from tools.node_architect.canonical_digest.reference_canonicalizer import canonical_json_bytes

DESTINATION_ID = "dwo-observation-v2"
SOURCE_ID = "gwc-main"
EVENT_SOURCE = "gwc.node-architect.dwo-observation.v1.0"


class DwoTransportError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _secret_bytes(secret: str) -> bytes:
    if not isinstance(secret, str) or len(secret) < 32:
        raise DwoTransportError("DWO_MACHINE_SECRET_INVALID")
    return secret.encode("utf-8")


def request_signature(secret: str, *, timestamp: int, request_digest: str) -> str:
    msg = f"{timestamp}\n{request_digest}".encode("utf-8")
    return "hmac-sha256:" + hmac.new(_secret_bytes(secret), msg, hashlib.sha256).hexdigest()


def ack_signature(secret: str, ack: Mapping[str, Any]) -> str:
    fields = (
        str(ack["created"]),
        str(ack["request_digest"]),
        str(ack["payload_digest"]),
        str(ack["event_id"]),
        str(ack["delivery_generation"]),
        str(ack["raw_event_id"]),
        str(ack["projection_ordinal"]),
        str(ack["status"]),
    )
    return "hmac-sha256:" + hmac.new(
        _secret_bytes(secret), "\n".join(fields).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_ack_signature(secret: str, ack: Mapping[str, Any]) -> bool:
    proof = ack.get("signature_proof")
    if not isinstance(proof, str):
        return False
    try:
        expected = ack_signature(secret, ack)
    except (KeyError, TypeError, ValueError, DwoTransportError):
        return False
    return hmac.compare_digest(proof, expected)


def build_request(
    event: Mapping[str, Any], *, delivery_generation: int,
    destination_id: str = DESTINATION_ID,
) -> tuple[bytes, str, str]:
    payload_digest = _sha256(canonical_json_bytes(dict(event)))
    body = {
        "delivery": {
            "destination_id": destination_id,
            "generation": delivery_generation,
            "payload_digest": payload_digest,
        },
        "event": dict(event),
    }
    raw = canonical_json_bytes(body)
    return raw, _sha256(raw), payload_digest


def send_event(
    endpoint: str,
    *,
    event: Mapping[str, Any],
    secret: str,
    key_id: str,
    delivery_generation: int,
    source_id: str = SOURCE_ID,
    timeout_s: float = 15.0,
) -> tuple[dict[str, Any], str, str]:
    raw, request_digest, payload_digest = build_request(
        event, delivery_generation=delivery_generation
    )
    timestamp = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "X-DWO-Source-Id": source_id,
        "X-DWO-Key-Id": key_id,
        "X-DWO-Timestamp": str(timestamp),
        "X-DWO-Request-Digest": request_digest,
        "X-DWO-Signature": request_signature(
            secret, timestamp=timestamp, request_digest=request_digest
        ),
        # HTTPS bearer secret; DWO stores only its SHA-256 hash.
        "X-DWO-Machine-Token": secret,
    }
    request = urllib.request.Request(endpoint, data=raw, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read()
            if not 200 <= response.status < 300:
                raise DwoTransportError(f"DWO_HTTP_{response.status}")
    except urllib.error.HTTPError as exc:
        raise DwoTransportError(f"DWO_HTTP_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise DwoTransportError("DWO_TRANSPORT_UNAVAILABLE") from exc

    try:
        ack = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DwoTransportError("DWO_ACK_INVALID_JSON") from exc
    return ack, request_digest, payload_digest
