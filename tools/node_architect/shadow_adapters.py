#!/usr/bin/env python3
"""Read-only shadow adapters for canonical Node Architect nodes."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_adapter_registry(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    adapters: dict[str, dict[str, Any]] = {}
    for node in registry.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            continue
        effect = node.get("effect_class", "read_only")
        adapters[node_id] = {
            "node_id": node_id,
            "adapter_kind": "observe" if effect == "read_only" else "propose_only",
            "mode": "shadow_readonly",
            "authority": "none",
            "output_effect": "observe_only",
            "write_capable": False,
        }
    return adapters


def execute_shadow_node(node: dict[str, Any], event: dict[str, Any], input_payload: dict[str, Any]) -> dict[str, Any]:
    node_id = node.get("id")
    if not isinstance(node_id, str) or not node_id:
        raise ValueError("node.id is required")
    required = ("task_id", "run_id", "gate", "exact_revision")
    missing = [field for field in required if not event.get(field)]
    if missing:
        return {
            "node_id": node_id,
            "applicability": "BLOCKED",
            "outcome": "INVALID_EVENT",
            "reason_code": "SHADOW_EVENT_IDENTITY_MISSING",
            "missing": missing,
            "executed_effects": [],
            "proposed_effects": [],
            "authority_granted": False,
        }
    effect = node.get("effect_class", "read_only")
    proposed: list[dict[str, Any]] = []
    outcome = "OBSERVED"
    reason = "SHADOW_READ_ONLY_OBSERVATION"
    if effect != "read_only":
        proposed = [{"effect_class": effect, "disposition": "WOULD_REQUIRE_AUTHORITY"}]
        outcome = "WOULD_REQUEST_ACTION"
        reason = "SHADOW_MUTATION_PROPOSAL_ONLY"
    suspension = node.get("suspension") if isinstance(node.get("suspension"), dict) else {}
    checkpoint = {
        "recommended": bool(suspension.get("suspendable")),
        "resume_metadata": list(suspension.get("resume_metadata", [])) if isinstance(suspension.get("resume_metadata", []), list) else [],
    }
    stable = {
        "node_id": node_id,
        "node_version": node.get("version"),
        "family": node.get("family"),
        "maturity": node.get("maturity"),
        "task_id": event["task_id"],
        "run_id": event["run_id"],
        "gate": event["gate"],
        "exact_revision": event["exact_revision"],
        "input_payload": input_payload,
        "applicability": "APPLICABLE",
        "outcome": outcome,
        "reason_code": reason,
        "proposed_effects": proposed,
        "executed_effects": [],
        "authority_granted": False,
        "checkpoint": checkpoint,
    }
    stable["result_digest"] = _digest(stable)
    return stable
