#!/usr/bin/env python3
"""Deterministic append-only logical telemetry for Node Architect shadow runs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

INVOCATION_IDENTITY_FIELDS = ("task_id", "run_id", "gate", "exact_revision", "node_id", "node_version")


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_telemetry_event(
    result: dict[str, Any], *, route_pack: str, graph_revision: str | None = None
) -> dict[str, Any]:
    if result.get("authority_granted") is True:
        raise ValueError("SHADOW_AUTHORITY_ESCALATION_REJECTED")
    if result.get("executed_effects"):
        raise ValueError("SHADOW_EXECUTED_EFFECT_REJECTED")
    identity = {field: result.get(field) for field in INVOCATION_IDENTITY_FIELDS}
    missing = [field for field, value in identity.items() if value in (None, "")]
    if missing:
        raise ValueError("SHADOW_TELEMETRY_IDENTITY_MISSING:" + ",".join(missing))
    identity["route_pack"] = route_pack
    identity["graph_revision"] = graph_revision or f"repo-bound:{result['exact_revision']}"
    idempotency_key = _sha(identity)
    stable = {
        **identity,
        "idempotency_key": idempotency_key,
        "maturity": result.get("maturity"),
        "executability_level": result.get("executability_level"),
        "applicability": result.get("applicability"),
        "shadow_decision": result.get("outcome"),
        "reason_code": result.get("reason_code"),
        "result_digest": result.get("result_digest"),
        "proposed_effects": list(result.get("proposed_effects") or []),
        "executed_effects": [],
        "authority_granted": False,
        "checkpoint": result.get("checkpoint"),
    }
    stable["event_digest"] = _sha(stable)
    return stable


def append_telemetry(path: Path, event: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    key = event.get("idempotency_key")
    if not isinstance(key, str) or not key:
        raise ValueError("SHADOW_TELEMETRY_IDEMPOTENCY_KEY_REQUIRED")
    if path.exists():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"SHADOW_TELEMETRY_LEDGER_CORRUPT:{line_number}") from exc
            if existing.get("idempotency_key") == key:
                if existing.get("event_digest") != event.get("event_digest"):
                    raise ValueError("SHADOW_REPLAY_NON_DETERMINISTIC")
                return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    return True
