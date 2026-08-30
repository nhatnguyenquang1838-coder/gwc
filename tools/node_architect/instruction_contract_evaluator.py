#!/usr/bin/env python3
"""Semantic evaluator for nodes whose executable semantics live in a Node Instruction Card.

This is not the old generic shadow adapter. The evaluator is bound to one exact
node/version/instruction digest and interprets that node's validated ENTRY,
allowed/forbidden actions, evidence, authority and NEXT contracts. It never
performs a mutation itself; W12's capability boundary owns effect execution.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .validate_node_instruction import digest_payload, load_data


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _blocked(binding: Mapping[str, Any], event: Mapping[str, Any], reason: str, *, detail: Any = None) -> dict[str, Any]:
    result = {
        "node_id": binding.get("node_id"),
        "node_version": binding.get("node_version"),
        "implementation_ref": binding.get("implementation_ref"),
        "binding_digest": binding.get("binding_digest"),
        "semantic_execution": True,
        "implementation_invoked": True,
        "outcome": "BLOCKED",
        "reason_code": reason,
        "applicability": "BLOCKED",
        "requested_effects": [],
        "proposed_effects": [],
        "executed_effects": [],
        "authority_granted": False,
        "evidence_refs": [],
        "next_contract": None,
    }
    if detail is not None:
        result["detail"] = detail
    result["invocation_digest"] = _digest({"binding": binding.get("binding_digest"), "event": event, "result": result})
    return result


def evaluate_instruction_contract(
    binding: Mapping[str, Any],
    runtime_event: Mapping[str, Any],
    *,
    root: Path | str = Path("."),
) -> dict[str, Any]:
    """Interpret one exact node instruction as semantic runtime behavior."""
    repo_root = Path(root).resolve()
    instruction_ref = binding.get("instruction_ref")
    if not isinstance(instruction_ref, str) or not instruction_ref:
        return _blocked(binding, runtime_event, "SEMANTIC_INSTRUCTION_REF_MISSING")
    path = repo_root / instruction_ref
    if not path.is_file():
        return _blocked(binding, runtime_event, "SEMANTIC_INSTRUCTION_MISSING")
    try:
        card = load_data(path)
    except Exception as exc:
        return _blocked(binding, runtime_event, "SEMANTIC_INSTRUCTION_INVALID", detail=f"{type(exc).__name__}: {exc}")
    if not isinstance(card, Mapping):
        return _blocked(binding, runtime_event, "SEMANTIC_INSTRUCTION_INVALID")
    if str(card.get("node_id", "")) != str(binding.get("node_id", "")):
        return _blocked(binding, runtime_event, "SEMANTIC_INSTRUCTION_NODE_MISMATCH")
    if digest_payload(card) != binding.get("instruction_digest"):
        return _blocked(binding, runtime_event, "SEMANTIC_INSTRUCTION_DIGEST_DRIFT")

    required_identity = ("task_id", "run_id", "gate", "exact_revision", "input_payload")
    missing_identity = [key for key in required_identity if runtime_event.get(key) in (None, "")]
    if missing_identity:
        return _blocked(binding, runtime_event, "SEMANTIC_ENTRY_IDENTITY_MISSING", detail=missing_identity)
    gate = str(runtime_event.get("gate", ""))
    if gate not in set(map(str, card.get("gate", []) or [])):
        return _blocked(binding, runtime_event, "SEMANTIC_GATE_NOT_APPLICABLE")

    payload = runtime_event.get("input_payload")
    if not isinstance(payload, Mapping):
        return _blocked(binding, runtime_event, "SEMANTIC_INPUT_PAYLOAD_INVALID")
    entry_contract = list(binding.get("entry_contract", []) or [])
    missing_entry = [key for key in entry_contract if key not in payload]
    if missing_entry:
        return _blocked(binding, runtime_event, "SEMANTIC_ENTRY_EVIDENCE_MISSING", detail=missing_entry)

    requested_action = str(runtime_event.get("requested_action") or payload.get("requested_action") or "")
    allowed = set(map(str, card.get("allowed_actions", []) or []))
    forbidden = set(map(str, card.get("forbidden_actions", []) or []))
    if requested_action and requested_action in forbidden:
        return _blocked(binding, runtime_event, "SEMANTIC_ACTION_FORBIDDEN")

    side_effect = str(binding.get("side_effect_class") or "read_only")
    requested_effects = []
    if requested_action:
        requested_effects.append({"action": requested_action, "side_effect_class": side_effect})
    elif allowed:
        requested_effects.append({"action": sorted(allowed)[0], "side_effect_class": side_effect})

    next_table = card.get("next") if isinstance(card.get("next"), Mapping) else {}
    next_contract = next_table.get("pass") if isinstance(next_table, Mapping) else None
    result = {
        "node_id": binding.get("node_id"),
        "node_version": binding.get("node_version"),
        "implementation_ref": binding.get("implementation_ref"),
        "binding_digest": binding.get("binding_digest"),
        "semantic_execution": True,
        "implementation_invoked": True,
        "outcome": "PASS",
        "reason_code": "SEMANTIC_INSTRUCTION_EVALUATED",
        "applicability": "APPLICABLE",
        "requested_effects": requested_effects,
        "proposed_effects": requested_effects if side_effect != "read_only" else [],
        "executed_effects": [],
        "authority_granted": False,
        "evidence_refs": [instruction_ref, str(binding.get("descriptor_ref") or "")],
        "next_contract": next_contract,
        "instruction_digest": binding.get("instruction_digest"),
        "input_digest": _digest(payload),
    }
    result["invocation_digest"] = _digest({"binding": binding.get("binding_digest"), "event": runtime_event, "result": result})
    return result


__all__ = ["evaluate_instruction_contract"]
