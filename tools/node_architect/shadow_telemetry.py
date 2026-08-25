#!/usr/bin/env python3
"""Deterministic append-only logical telemetry for Node Architect shadow runs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

IDENTITY_FIELDS = ("task_id", "run_id", "gate", "exact_revision", "node_id")


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_telemetry_event(result: dict[str, Any], *, route_pack: str) -> dict[str, Any]:
    identity = {field: result.get(field) for field in IDENTITY_FIELDS}
    identity["route_pack"] = route_pack
    identity["result_digest"] = result.get("result_digest")
    idempotency_key = _sha(identity)
    stable = {
        **identity,
        "idempotency_key": idempotency_key,
        "applicability": result.get("applicability"),
        "shadow_decision": result.get("outcome"),
        "reason_code": result.get("reason_code"),
        "proposed_effects": list(result.get("proposed_effects") or []),
        "executed_effects": list(result.get("executed_effects") or []),
        "authority_granted": bool(result.get("authority_granted", False)),
    }
    stable["event_digest"] = _sha(stable)
    return stable


def append_telemetry(path: Path, event: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    key = event.get("idempotency_key")
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("idempotency_key") == key:
                return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    return True
