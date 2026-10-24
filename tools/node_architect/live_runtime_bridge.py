"""Universal Runtime v2-only bridge boundary.

The former mixed legacy/V2 Agent bridge is preserved under
``legacy/gwc-v1/sources``. This module accepts only UR lifecycle names and never
imports the GWC v1 semantic runtime; the default execution route is the native
UniversalController/UniversalExecutor CLI.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .q0_qualification import Q0_RUNTIME_EPOCH, Q0_WORKFLOW_MODE, q0_qualification_profile
from .universal_run_kernel import GATES
from .universal_runtime_profile import load_universal_v2_default_profile

UNIVERSAL_GATES = GATES
CANONICAL_SOURCE_KIND = "canonical_agent_gate_state"


@dataclass
class LiveRuntimeState:
    """Projection cache only; this state never owns the Universal cursor."""
    event_digests: dict[str, str] = field(default_factory=dict)
    event_results: dict[str, dict[str, Any]] = field(default_factory=dict)


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def build_live_runtime_event(
    *, canonical_state: Mapping[str, Any], event_id: str, run_id: str, gate: str,
    requested_action: str, scenario: str, input_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if gate not in GATES:
        raise ValueError("UNIVERSAL_GATE_INVALID")
    if not isinstance(canonical_state, Mapping) or not isinstance(input_payload, Mapping):
        raise ValueError("GWC_RUNTIME_DEFECT")
    profile = load_universal_v2_default_profile()
    q0_profile = q0_qualification_profile()
    if (
        input_payload.get("workflow_mode") != Q0_WORKFLOW_MODE
        or input_payload.get("runtime_epoch") != Q0_RUNTIME_EPOCH
        or input_payload.get("q0_profile") != q0_profile
        or profile.get("runtime_family") != "UNIVERSAL_V2"
    ):
        raise ValueError("GWC_RUNTIME_DEFECT")
    event_body = {
        "schema_id": "gwc.universal-run.live-runtime-event.v2",
        "schema_version": 2,
        "runtime_protocol": profile["runtime_protocol"],
        "runtime_epoch": Q0_RUNTIME_EPOCH,
        "runtime_profile_digest": profile["profile_digest"],
        "workflow_mode": Q0_WORKFLOW_MODE,
        "q0_profile_digest": q0_profile["profile_digest"],
        "event_id": event_id,
        "run_id": run_id,
        "task_id": str(canonical_state.get("task_id") or ""),
        "repository": str(canonical_state.get("repository") or ""),
        "branch": str(canonical_state.get("branch") or ""),
        "base_sha": str(canonical_state.get("base_sha") or ""),
        "head_sha": str(canonical_state.get("head_sha") or ""),
        "scope_hash": str(canonical_state.get("scope_hash") or ""),
        "source_kind": str(canonical_state.get("source_kind") or ""),
        "gate": gate,
        "requested_action": requested_action,
        "scenario": scenario,
        "input_payload": dict(input_payload),
        "effect_authority": "NONE",
        "authority_granted": False,
        "executed_effects": [],
        "occurred_at": str(canonical_state.get("occurred_at") or datetime.now(timezone.utc).isoformat()),
    }
    return {**event_body, "event_digest": _digest(event_body)}


def dispatch_live_runtime_event(*, event: Mapping[str, Any], **_unused: Any) -> dict[str, Any]:
    """Fail closed: this bridge is not an alternate executor or V1 fallback."""
    if not isinstance(event, Mapping) or event.get("schema_id") != "gwc.universal-run.live-runtime-event.v2":
        return {"status": "BLOCKED", "reason_code": "GWC_RUNTIME_DEFECT", "authority_granted": False, "executed_effects": []}
    return {"status": "BLOCKED", "reason_code": "USE_UNIVERSAL_V2_EXECUTOR", "authority_granted": False, "executed_effects": []}


def resume_live_runtime_event(*, checkpoint: Mapping[str, Any], **_unused: Any) -> dict[str, Any]:
    """Resume only through the native RuntimePlan/RunState controller."""
    if not isinstance(checkpoint, Mapping) or not isinstance(checkpoint.get("run_state"), Mapping):
        return {"status": "BLOCKED", "reason_code": "GWC_RUNTIME_DEFECT"}
    return {"status": "BLOCKED", "reason_code": "USE_UNIVERSAL_V2_CONTROLLER"}


__all__ = [
    "GATES", "UNIVERSAL_GATES", "CANONICAL_SOURCE_KIND", "LiveRuntimeState",
    "build_live_runtime_event", "dispatch_live_runtime_event", "resume_live_runtime_event",
]
