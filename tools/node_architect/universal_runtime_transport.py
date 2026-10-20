"""Transport adapters for Universal Runtime v2 decisions.

Adapters project already-decided native work; they cannot modify the runtime
subject, cursor, owner, or typed NEXT.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Protocol


class UniversalTransportError(ValueError):
    """A projection/transport receipt failed its V2 boundary."""


class TransportAdapter(Protocol):
    name: str

    def deliver(self, decision_subject: Mapping[str, Any]) -> Mapping[str, Any]: ...


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


class InProcessTransportAdapter:
    name = "in_process"

    def deliver(self, decision_subject: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "transport": self.name,
            "message_id": "local:" + _sha(decision_subject)[7:31],
            "readback_digest": _sha(decision_subject),
        }


class MailboxProjectionAdapter:
    """Pure projection adapter; it performs no GitHub/mailbox write."""

    name = "mailbox_projection"

    def deliver(self, decision_subject: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "transport": self.name,
            "message_id": "projection:" + _sha(decision_subject)[7:31],
            "readback_digest": _sha(decision_subject),
        }


def project_controller_decision(
    decision: Mapping[str, Any], adapter: TransportAdapter
) -> dict[str, Any]:
    """Attach transport-only evidence without changing the native decision digest."""
    subject = decision.get("decision_subject")
    if not isinstance(subject, Mapping):
        raise UniversalTransportError("NATIVE_DECISION_SUBJECT_REQUIRED")
    allowed = {"runtime_epoch", "actor", "typed_next", "run_id", "sequence"}
    if set(subject) != allowed:
        raise UniversalTransportError("NATIVE_DECISION_SUBJECT_FIELDS_INVALID")
    expected_digest = _sha(subject)
    if decision.get("decision_digest") != expected_digest:
        raise UniversalTransportError("NATIVE_DECISION_DIGEST_INVALID")
    frozen_subject = copy.deepcopy(dict(subject))
    receipt = adapter.deliver(copy.deepcopy(frozen_subject))
    if not isinstance(receipt, Mapping):
        raise UniversalTransportError("TRANSPORT_RECEIPT_INVALID")
    if any(key in receipt for key in ("typed_next", "next_gate", "successor_run_state", "authority_granted")):
        raise UniversalTransportError("TRANSPORT_CONTROL_FIELD_FORBIDDEN")
    if _sha(frozen_subject) != expected_digest:
        raise UniversalTransportError("TRANSPORT_MUTATED_NATIVE_DECISION")
    return {
        "decision_subject": frozen_subject,
        "decision_digest": expected_digest,
        "transport_receipt": copy.deepcopy(dict(receipt)),
    }


__all__ = [
    "InProcessTransportAdapter",
    "MailboxProjectionAdapter",
    "TransportAdapter",
    "UniversalTransportError",
    "project_controller_decision",
]
