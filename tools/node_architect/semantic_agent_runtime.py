#!/usr/bin/env python3
"""Production-intended semantic Agent node lifecycle and dual-mode effect boundary.

One canonical-selected semantic binding is executed through:
ENTRY -> DO -> BRANCH -> EFFECT BOUNDARY -> READBACK -> EXIT -> LEDGER -> NEXT.
The semantic evaluator is shared by shadow and authoritative modes. Authority is
validated independently and only the capability boundary may perform effects.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .node_evidence_ledger import EvidenceConflict, NodeEvidenceLedger, digest_payload
from .semantic_implementation_registry import INSTRUCTION_EVALUATOR
from .semantic_implementation_runtime import invoke_semantic_implementation

SemanticHandler = Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
CapabilityHandler = Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
ReadbackHandler = Callable[..., Mapping[str, Any]]

_REQUIRED_EVENT = (
    "event_id", "task_id", "run_id", "repository", "branch", "base_sha", "head_sha",
    "exact_revision", "scope_hash", "gate", "node_registry_revision", "idempotency_key",
)


@dataclass
class RuntimeExecutionState:
    writer_fences: dict[str, str] = field(default_factory=dict)
    replay_digests: dict[str, str] = field(default_factory=dict)
    checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _validate_entry(event: Mapping[str, Any], binding: Mapping[str, Any]) -> str | None:
    missing = [key for key in _REQUIRED_EVENT if event.get(key) in (None, "")]
    if missing:
        return "SEMANTIC_ENTRY_IDENTITY_MISSING:" + ",".join(missing)
    if event.get("head_sha") != event.get("exact_revision"):
        return "SEMANTIC_ENTRY_REVISION_MISMATCH"
    if str(binding.get("node_registry_revision", "")) != str(event.get("node_registry_revision", "")):
        return "SEMANTIC_BINDING_REGISTRY_REVISION_DRIFT"
    if str(event.get("gate", "")) not in {str(item) for item in binding.get("gates", []) or []}:
        return "SEMANTIC_BINDING_GATE_MISMATCH"
    payload = event.get("input_payload")
    if not isinstance(payload, Mapping):
        return "SEMANTIC_INPUT_PAYLOAD_INVALID"
    missing_entry = [key for key in binding.get("entry_contract", []) or [] if key not in payload]
    if missing_entry:
        return "SEMANTIC_ENTRY_EVIDENCE_MISSING:" + ",".join(map(str, missing_entry))
    return None


def _invoke_semantic(
    binding: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    handlers: Mapping[str, SemanticHandler],
    root: Path,
) -> dict[str, Any]:
    ref = str(binding.get("implementation_ref") or "")
    if ref == INSTRUCTION_EVALUATOR:
        return invoke_semantic_implementation(binding, event, root=root)
    handler = handlers.get(ref)
    if handler is None:
        return {
            "node_id": binding.get("node_id"),
            "implementation_ref": ref,
            "binding_digest": binding.get("binding_digest"),
            "implementation_invoked": False,
            "semantic_execution": False,
            "outcome": "BLOCKED",
            "reason_code": "SEMANTIC_IMPLEMENTATION_HANDLER_UNAVAILABLE",
            "requested_effects": [],
            "proposed_effects": [],
            "executed_effects": [],
            "authority_granted": False,
        }
    try:
        raw = handler(binding, event)
    except Exception as exc:
        return {
            "node_id": binding.get("node_id"),
            "implementation_ref": ref,
            "binding_digest": binding.get("binding_digest"),
            "implementation_invoked": True,
            "semantic_execution": True,
            "outcome": "BLOCKED",
            "reason_code": "SEMANTIC_IMPLEMENTATION_EXCEPTION",
            "error": f"{type(exc).__name__}: {exc}",
            "requested_effects": [],
            "proposed_effects": [],
            "executed_effects": [],
            "authority_granted": False,
        }
    if not isinstance(raw, Mapping):
        return {
            "node_id": binding.get("node_id"),
            "implementation_ref": ref,
            "binding_digest": binding.get("binding_digest"),
            "implementation_invoked": True,
            "semantic_execution": True,
            "outcome": "BLOCKED",
            "reason_code": "SEMANTIC_IMPLEMENTATION_INVALID_RESULT",
            "requested_effects": [], "proposed_effects": [], "executed_effects": [],
            "authority_granted": False,
        }
    result = dict(raw)
    result.update({
        "node_id": binding.get("node_id"),
        "node_version": binding.get("node_version"),
        "implementation_ref": ref,
        "binding_digest": binding.get("binding_digest"),
        "implementation_invoked": True,
        "semantic_execution": True,
        "authority_granted": False,
        "executed_effects": [],
    })
    if not isinstance(result.get("invocation_digest"), str):
        result["invocation_digest"] = _digest({"binding": binding.get("binding_digest"), "event": event, "result": result})
    return result


def _validate_authority(
    authority: Mapping[str, Any] | None,
    *,
    event: Mapping[str, Any],
    requested_actions: set[str],
) -> str | None:
    if not isinstance(authority, Mapping):
        return "AUTHORITY_MISSING"
    exact = (
        ("task_id", event.get("task_id")),
        ("repository", event.get("repository")),
        ("branch", event.get("branch")),
        ("head_sha", event.get("head_sha")),
        ("scope_hash", event.get("scope_hash")),
        ("gate", event.get("gate")),
    )
    if any(str(authority.get(field, "")) != str(expected or "") for field, expected in exact):
        return "AUTHORITY_BINDING_MISMATCH"
    expiry = authority.get("expires_at")
    parsed = _parse_time(str(expiry)) if expiry else None
    if parsed is None or parsed <= datetime.now(timezone.utc):
        return "AUTHORITY_EXPIRED"
    allowed = {str(item) for item in authority.get("allowed_actions", []) or []}
    if not requested_actions.issubset(allowed):
        return "AUTHORITY_ACTION_NOT_ALLOWED"
    if authority.get("later_gate_authority") is True:
        return "AUTHORITY_LATER_GATE_ESCALATION_REJECTED"
    if not authority.get("authority_id"):
        return "AUTHORITY_IDENTITY_MISSING"
    return None


def _next_contract_valid(binding: Mapping[str, Any], candidate: Any) -> bool:
    if not isinstance(candidate, Mapping):
        return False
    table = binding.get("next_route_contract")
    if not isinstance(table, Mapping):
        return False
    return any(isinstance(value, Mapping) and dict(value) == dict(candidate) for value in table.values())


def _ledger(event: Mapping[str, Any], binding: Mapping[str, Any], evidence_root: Path) -> NodeEvidenceLedger:
    # Each immutable runtime event gets a physically isolated ledger root while
    # preserving canonical task/run/node identity inside every record. This
    # permits repeated/checkpointed invocations without overwriting prior proof.
    event_root = evidence_root / ".semantic-runtime-events" / str(event["event_id"])
    return NodeEvidenceLedger(
        root=event_root,
        task_id=str(event["task_id"]), run_id=str(event["run_id"]), node_id=str(binding["node_id"]),
        repository=str(event["repository"]), branch=str(event["branch"]), base_sha=str(event["base_sha"]),
        head_sha=str(event["head_sha"]), scope_hash=str(event["scope_hash"]),
        idempotency_key=str(event["idempotency_key"]), occurred_at=str(event.get("occurred_at") or "1970-01-01T00:00:00Z"),
    )


def _write_evidence(
    *,
    ledger: NodeEvidenceLedger,
    event: Mapping[str, Any],
    binding: Mapping[str, Any],
    semantic: Mapping[str, Any],
    branch: Mapping[str, Any],
    readback: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    next_route: Mapping[str, Any],
) -> dict[str, Any]:
    ledger.record_start({
        "stage": "ENTRY", "event_id": event["event_id"], "gate": event["gate"],
        "exact_revision": event["head_sha"], "binding_digest": binding.get("binding_digest"),
        "input_digest": digest_payload(event.get("input_payload", {})),
    })
    ledger.record_decision({"stage": "BRANCH", **dict(branch)})
    ledger.record_result({"stage": "DO_EFFECT", "semantic_result": dict(semantic), "executed_effects": list(branch.get("executed_effects", []) or [])})
    ledger.record_readback({"stage": "READBACK", **dict(readback)})
    ledger.record_checkpoint({"stage": "EXIT_CHECKPOINT", **dict(checkpoint)})
    ledger.record_next_route({"stage": "NEXT", **dict(next_route)})
    return ledger.summary()


def execute_semantic_node_lifecycle(
    *,
    event: Mapping[str, Any],
    binding: Mapping[str, Any],
    mode: str,
    semantic_handlers: Mapping[str, SemanticHandler],
    capability_handlers: Mapping[str, CapabilityHandler],
    readback_handler: ReadbackHandler | None,
    evidence_root: Path | str,
    state: RuntimeExecutionState,
    authority: Mapping[str, Any] | None = None,
    root: Path | str = Path("."),
) -> dict[str, Any]:
    if mode not in {"shadow_readonly", "authoritative"}:
        return {"status": "SEMANTIC_NODE_BLOCKED", "reason_code": "SEMANTIC_EXECUTION_MODE_INVALID", "authority_granted": False, "executed_effects": []}
    entry_error = _validate_entry(event, binding)
    if entry_error:
        return {"status": "SEMANTIC_NODE_BLOCKED", "reason_code": entry_error, "authority_granted": False, "executed_effects": []}

    event_digest = _digest({"event": event, "binding_digest": binding.get("binding_digest"), "mode": mode})
    replay_key = str(event["idempotency_key"])
    prior = state.replay_digests.get(replay_key)
    if prior is not None and prior != event_digest:
        return {"status": "SEMANTIC_NODE_BLOCKED", "reason_code": "SEMANTIC_RUNTIME_REPLAY_CONFLICT", "authority_granted": False, "executed_effects": []}
    state.replay_digests[replay_key] = event_digest

    semantic = _invoke_semantic(binding, event, handlers=semantic_handlers, root=Path(root))
    outcome = str(semantic.get("outcome") or "BLOCKED").upper()
    requested_effects = [dict(item) for item in semantic.get("requested_effects", []) if isinstance(item, Mapping)]
    proposed_effects = [dict(item) for item in semantic.get("proposed_effects", []) if isinstance(item, Mapping)]
    executed_effects: list[dict[str, Any]] = []
    branch_reason = str(semantic.get("reason_code") or "SEMANTIC_RESULT_UNTYPED")
    authority_granted = False

    if semantic.get("semantic_execution") is not True or semantic.get("implementation_invoked") is not True:
        outcome = "BLOCKED"
        branch_reason = str(semantic.get("reason_code") or "SEMANTIC_IMPLEMENTATION_NOT_INVOKED")

    write_effects = [item for item in requested_effects if str(item.get("side_effect_class") or binding.get("side_effect_class") or "read_only") != "read_only"]
    if mode == "shadow_readonly":
        proposed_effects.extend(item for item in write_effects if item not in proposed_effects)
    elif write_effects and outcome not in {"BLOCKED", "FAIL", "NOT_APPLICABLE", "PENDING", "WAIT", "RETRY"}:
        requested_actions = {str(item.get("action") or "") for item in write_effects if item.get("action")}
        authority_error = _validate_authority(authority, event=event, requested_actions=requested_actions)
        if authority_error:
            outcome = "BLOCKED"
            branch_reason = authority_error
        else:
            assert isinstance(authority, Mapping)
            target = str(authority.get("writer_target") or "")
            token = str(authority.get("fencing_token") or "")
            if not target or not token:
                outcome = "BLOCKED"
                branch_reason = "AUTHORITATIVE_WRITER_FENCE_MISSING"
            elif target in state.writer_fences and state.writer_fences[target] != token:
                outcome = "BLOCKED"
                branch_reason = "AUTHORITATIVE_WRITER_FENCED"
            else:
                state.writer_fences[target] = token
                for effect in write_effects:
                    action = str(effect.get("action") or "")
                    handler = capability_handlers.get(action)
                    if handler is None:
                        outcome = "BLOCKED"
                        branch_reason = "CAPABILITY_HANDLER_UNAVAILABLE"
                        executed_effects = []
                        break
                    try:
                        raw = handler(effect, event, authority)
                    except Exception as exc:
                        outcome = "BLOCKED"
                        branch_reason = "CAPABILITY_EXECUTION_ERROR"
                        executed_effects = []
                        semantic = {**semantic, "capability_error": f"{type(exc).__name__}: {exc}"}
                        break
                    if not isinstance(raw, Mapping):
                        outcome = "BLOCKED"
                        branch_reason = "CAPABILITY_RESULT_INVALID"
                        executed_effects = []
                        break
                    executed_effects.append({**dict(effect), **dict(raw), "authority_ref": authority.get("authority_id")})
                if outcome != "BLOCKED":
                    authority_granted = True

    next_candidate = semantic.get("next_contract")
    if not _next_contract_valid(binding, next_candidate):
        outcome = "BLOCKED"
        branch_reason = "SEMANTIC_NEXT_ROUTE_MISMATCH"
        next_candidate = binding.get("next_route_contract", {}).get("blocked") if isinstance(binding.get("next_route_contract"), Mapping) else None

    suspended = outcome in {"PENDING", "WAIT", "RETRY"}
    if outcome in {"BLOCKED", "FAIL", "NOT_APPLICABLE"}:
        status = "SEMANTIC_NODE_BLOCKED" if outcome != "NOT_APPLICABLE" else "SEMANTIC_NODE_NOT_APPLICABLE"
    elif suspended:
        status = "SEMANTIC_NODE_SUSPENDED"
    else:
        status = "SEMANTIC_NODE_COMPLETE"

    readback: dict[str, Any]
    if readback_handler is None:
        readback = {"status": "BLOCKED", "reason_code": "CANONICAL_READBACK_UNAVAILABLE"}
    else:
        try:
            raw_readback = readback_handler(binding, semantic, executed_effects, event)
        except Exception as exc:
            raw_readback = {"status": "BLOCKED", "reason_code": "CANONICAL_READBACK_ERROR", "error": f"{type(exc).__name__}: {exc}"}
        readback = dict(raw_readback) if isinstance(raw_readback, Mapping) else {"status": "BLOCKED", "reason_code": "CANONICAL_READBACK_INVALID"}
    canonical_verified = readback.get("status") == "VERIFIED"
    if status == "SEMANTIC_NODE_COMPLETE" and not canonical_verified:
        status = "SEMANTIC_NODE_BLOCKED"
        branch_reason = str(readback.get("reason_code") or "CANONICAL_READBACK_NOT_VERIFIED")
        authority_granted = False

    checkpoint = {
        "checkpoint_id": f"{event['event_id']}:{binding['node_id']}",
        "status": "SUSPENDED" if suspended else ("BLOCKED" if status != "SEMANTIC_NODE_COMPLETE" else "COMPLETE"),
        "task_id": event["task_id"], "run_id": event["run_id"], "node_id": binding["node_id"],
        "head_sha": event["head_sha"], "binding_digest": binding.get("binding_digest"),
        "event_digest": event_digest, "reason_code": branch_reason,
    }
    if suspended:
        state.checkpoints[checkpoint["checkpoint_id"]] = dict(checkpoint)

    next_route = dict(next_candidate) if isinstance(next_candidate, Mapping) else {
        "disposition": "stop", "reason": branch_reason, "next_node": None, "next_action": None, "next_gate": None
    }
    next_route["gate_authority_required"] = bool(next_route.get("next_gate"))
    next_route["automatic_gate_advance"] = False
    branch = {
        "outcome": outcome, "reason_code": branch_reason,
        "execution_mode": mode, "requested_effects": requested_effects,
        "proposed_effects": proposed_effects, "executed_effects": executed_effects,
        "authority_ref": authority.get("authority_id") if authority_granted and isinstance(authority, Mapping) else None,
    }

    try:
        evidence_summary = _write_evidence(
            ledger=_ledger(event, binding, Path(evidence_root)), event=event, binding=binding,
            semantic=semantic, branch=branch, readback=readback, checkpoint=checkpoint, next_route=next_route,
        )
    except EvidenceConflict:
        return {
            "status": "SEMANTIC_NODE_BLOCKED", "reason_code": "SEMANTIC_EVIDENCE_CONFLICT",
            "authority_granted": False, "executed_effects": [], "automatic_gate_advance": False,
        }

    return {
        "status": status,
        "reason_code": branch_reason if status != "SEMANTIC_NODE_COMPLETE" else "SEMANTIC_NODE_COMPLETE",
        "node_id": binding["node_id"],
        "binding_digest": binding.get("binding_digest"),
        "implementation_ref": binding.get("implementation_ref"),
        "implementation_invoked": semantic.get("implementation_invoked") is True,
        "semantic_execution": semantic.get("semantic_execution") is True,
        "semantic_invocation_digest": semantic.get("invocation_digest"),
        "execution_mode": mode,
        "requested_effects": requested_effects,
        "proposed_effects": proposed_effects,
        "executed_effects": executed_effects,
        "authority_granted": authority_granted,
        "authority_ref": authority.get("authority_id") if authority_granted and isinstance(authority, Mapping) else None,
        "canonical_readback_verified": canonical_verified,
        "readback": readback,
        "checkpoint": checkpoint,
        "next_route": next_route,
        "automatic_gate_advance": False,
        "evidence_summary": evidence_summary,
        "event_digest": event_digest,
    }


def resume_checkpoint(checkpoint: Mapping[str, Any], *, event: Mapping[str, Any], binding: Mapping[str, Any]) -> dict[str, Any]:
    if str(checkpoint.get("node_id", "")) != str(binding.get("node_id", "")):
        return {"status": "RESUME_BLOCKED", "reason_code": "CHECKPOINT_NODE_MISMATCH"}
    if checkpoint.get("binding_digest") != binding.get("binding_digest"):
        return {"status": "RESUME_BLOCKED", "reason_code": "CHECKPOINT_BINDING_DRIFT"}
    if str(checkpoint.get("head_sha", "")) != str(event.get("head_sha", "")) or event.get("head_sha") != event.get("exact_revision"):
        return {"status": "RESUME_BLOCKED", "reason_code": "CHECKPOINT_REVISION_DRIFT"}
    if str(checkpoint.get("task_id", "")) != str(event.get("task_id", "")):
        return {"status": "RESUME_BLOCKED", "reason_code": "CHECKPOINT_TASK_MISMATCH"}
    return {
        "status": "RESUME_ALLOWED", "reason_code": "CHECKPOINT_IDENTITY_MATCH",
        "node_id": binding.get("node_id"), "head_sha": event.get("head_sha"),
        "binding_digest": binding.get("binding_digest"),
    }


__all__ = ["RuntimeExecutionState", "execute_semantic_node_lifecycle", "resume_checkpoint"]
