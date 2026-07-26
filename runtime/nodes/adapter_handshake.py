"""Node adapter handshake and request routing."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
from typing import Any, Mapping, Sequence

from runtime.store.sqlite_adapter import SqliteRuntimeStore
from runtime.store.pending_action import PendingActionStore

RUNTIME_VERSION = "0.1"


class AdapterHandshake:
    """Perform adapter handshake and bind fencing metadata."""

    def __init__(self, store: SqliteRuntimeStore | None = None) -> None:
        self.store = store or SqliteRuntimeStore()

    def handshake(self, node_id: str, capabilities: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "0.1",
            "artifact_type": "adapter-contract",
            "adapter_id": node_id,
            "adapter_version": "0.1.0",
            "capabilities": {
                "side_effects": bool(capabilities.get("side_effects", False)),
                "idempotency": True,
                "readback": bool(capabilities.get("readback", False)),
            },
            "request": {
                "type": "adapter.handshake",
                "payload": dict(capabilities),
            },
            "result": {
                "outcome": "success",
                "adapter_version": "0.1.0",
                "readback_status": "not_required",
                "evidence_refs": [],
                "error_code": None,
            },
        }

    def route(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if request.get("request", {}).get("type") == "adapter.handshake":
            return self.handshake(
                node_id=request["adapter_id"],
                capabilities=request.get("request", {}).get("payload", {}),
            )

        node_request = request.get("request", {})
        return {
            "schema_version": "0.1",
            "artifact_type": "adapter-contract",
            "adapter_id": request.get("adapter_id", "unknown"),
            "adapter_version": "0.1.0",
            "capabilities": {
                "side_effects": True,
                "idempotency": True,
                "readback": True,
            },
            "request": node_request,
            "result": {
                "outcome": "blocked",
                "adapter_version": "0.1.0",
                "readback_status": "required",
                "evidence_refs": [],
                "error_code": "unsupported_operation",
            },
        }
