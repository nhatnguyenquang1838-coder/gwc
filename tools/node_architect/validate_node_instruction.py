#!/usr/bin/env python3
"""Validate one route-selected Node Architect instruction card fail closed."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator, FormatChecker

SUPPORTED_MODES = ("normal", "fastlane", "e2e", "hotfix", "rescue")
REQUIRED_EVIDENCE = {
    "node-start", "node-decision", "node-result", "node-readback",
    "checkpoint", "runtime-event", "next-route-decision",
}
REQUIRED_LOGS = {"runtime-events.jsonl", "decision_digest", "state_digest", "event_digest"}
PROHIBITED_AUTHORITY_ACTIONS = {
    "grant_gate_authority", "grant_g2_authority", "grant_g3_authority",
    "merge", "auto_merge", "deploy", "redeploy", "release", "publish",
    "runtime_reload", "production_configuration", "production_data",
    "credential_change", "secret_change", "migration", "force_push",
    "branch_deletion", "history_rewrite", "pr_base_change",
}


@dataclass(frozen=True)
class InstructionValidationReport:
    valid: bool
    node_id: str
    mode: str
    instruction_digest: str | None
    reason_code: str
    reason_codes: list[str]
    evidence_contract_valid: bool
    log_contract_valid: bool
    next_route_contract_valid: bool
    mode_runtime_required: bool
    authority_boundary_valid: bool


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def load_data(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)


def _dedupe(codes: list[str]) -> list[str]:
    return list(dict.fromkeys(codes))


def _schema_valid(card: Any, schema: Mapping[str, Any]) -> bool:
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        return not list(validator.iter_errors(card))
    except Exception:
        return False


def validate_instruction(
    *,
    card: Mapping[str, Any],
    schema: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    registry_node: Mapping[str, Any],
    route: Mapping[str, Any],
    active_gate: str,
    mode: str,
) -> InstructionValidationReport:
    codes: list[str] = []
    node_id = str(card.get("node_id", ""))
    instruction_digest = digest_payload(card) if card else None

    if not _schema_valid(card, schema):
        codes.append("NODE_INSTRUCTION_INVALID")

    identities = {
        node_id,
        str(descriptor.get("node_id", "")),
        str(registry_node.get("id", "")),
        str(route.get("current_node", "")),
    }
    if len(identities) != 1 or "" in identities:
        codes.append("NODE_INSTRUCTION_INVALID")

    card_gates = set(card.get("gate", []) if isinstance(card.get("gate"), list) else [])
    descriptor_gates = set(descriptor.get("gates", []) if isinstance(descriptor.get("gates"), list) else [])
    if active_gate not in card_gates or active_gate not in descriptor_gates:
        codes.append("NODE_INSTRUCTION_INVALID")

    evidence = set(card.get("evidence_required", []) if isinstance(card.get("evidence_required"), list) else [])
    evidence_valid = REQUIRED_EVIDENCE.issubset(evidence)
    if not evidence_valid:
        codes.append("NODE_EVIDENCE_CONTRACT_MISSING")

    logs = set(card.get("logs_required", []) if isinstance(card.get("logs_required"), list) else [])
    log_valid = REQUIRED_LOGS.issubset(logs)
    if not log_valid:
        codes.append("NODE_LOG_CONTRACT_MISSING")

    next_map = card.get("next", {}) if isinstance(card.get("next"), Mapping) else {}
    next_valid = True
    for outcome in ("pass", "blocked", "pending", "retry"):
        target = next_map.get(outcome)
        if not isinstance(target, Mapping):
            next_valid = False
            continue
        if not any(target.get(field) for field in ("next_node", "next_action", "next_gate")):
            next_valid = False
    pass_target = next_map.get("pass", {}) if isinstance(next_map.get("pass"), Mapping) else {}
    for field in ("next_node", "next_action", "next_gate"):
        if pass_target.get(field) != route.get(field):
            next_valid = False
    if not next_valid:
        codes.append("NODE_NEXT_ROUTE_MISSING")

    authority = card.get("authority_boundary", {}) if isinstance(card.get("authority_boundary"), Mapping) else {}
    authority_flags = [
        "node_grants_gate_authority", "g2_authority_granted", "g3_authority_granted",
        "merge_authority_granted", "deployment_authority_granted", "production_authority_granted",
    ]
    authority_valid = bool(authority) and all(authority.get(flag) is False for flag in authority_flags)
    allowed = set(card.get("allowed_actions", []) if isinstance(card.get("allowed_actions"), list) else [])
    if allowed & PROHIBITED_AUTHORITY_ACTIONS:
        authority_valid = False
    if not authority_valid:
        codes.append("NODE_AUTHORITY_ESCALATION_ATTEMPT")

    policy = card.get("mode_policy", {}) if isinstance(card.get("mode_policy"), Mapping) else {}
    runtime_flags = [
        "runtime_required", "boot_required", "claim_required", "gate_authority_required",
        "route_required", "instruction_required", "evidence_required", "logs_required",
        "next_route_required",
    ]
    supported = set(policy.get("supported_modes", []) if isinstance(policy.get("supported_modes"), list) else [])
    mode_valid = mode in SUPPORTED_MODES and set(SUPPORTED_MODES).issubset(supported) and all(policy.get(flag) is True for flag in runtime_flags)
    if not mode_valid:
        codes.append("MODE_BYPASSES_NODE_RUNTIME")

    codes = _dedupe(codes)
    return InstructionValidationReport(
        valid=not codes,
        node_id=node_id,
        mode=mode,
        instruction_digest=instruction_digest,
        reason_code=codes[0] if codes else "NODE_INSTRUCTION_VALID",
        reason_codes=codes or ["NODE_INSTRUCTION_VALID"],
        evidence_contract_valid=evidence_valid,
        log_contract_valid=log_valid,
        next_route_contract_valid=next_valid,
        mode_runtime_required=mode_valid,
        authority_boundary_valid=authority_valid,
    )


def validate_instruction_path(
    *, instruction_path: Path, schema_path: Path, descriptor_path: Path,
    registry_path: Path, route_profile_path: Path, active_gate: str, mode: str,
    route_id: str | None = None,
) -> InstructionValidationReport:
    if not instruction_path.is_file():
        return InstructionValidationReport(
            valid=False, node_id="", mode=mode, instruction_digest=None,
            reason_code="NODE_INSTRUCTION_MISSING", reason_codes=["NODE_INSTRUCTION_MISSING"],
            evidence_contract_valid=False, log_contract_valid=False,
            next_route_contract_valid=False, mode_runtime_required=False,
            authority_boundary_valid=False,
        )
    try:
        card = load_data(instruction_path)
        schema = load_data(schema_path)
        descriptor = load_data(descriptor_path)
        registry = load_data(registry_path)
        profile = load_data(route_profile_path)
        if not all(isinstance(item, Mapping) for item in (card, schema, descriptor, registry, profile)):
            raise ValueError("instruction validation inputs must be objects")
        node_id = str(card.get("node_id", ""))
        registry_node = next((node for node in registry.get("nodes", []) if node.get("id") == node_id), {})
        routes = [route for route in profile.get("routes", []) if route.get("current_node") == node_id and route.get("gate") == active_gate]
        if route_id:
            routes = [route for route in routes if route.get("route_id") == route_id]
        if len(routes) != 1:
            raise ValueError("instruction must resolve to exactly one route")
        return validate_instruction(
            card=card, schema=schema, descriptor=descriptor,
            registry_node=registry_node, route=routes[0], active_gate=active_gate, mode=mode,
        )
    except Exception:
        return InstructionValidationReport(
            valid=False, node_id="", mode=mode, instruction_digest=None,
            reason_code="NODE_INSTRUCTION_INVALID", reason_codes=["NODE_INSTRUCTION_INVALID"],
            evidence_contract_valid=False, log_contract_valid=False,
            next_route_contract_valid=False, mode_runtime_required=False,
            authority_boundary_valid=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instruction", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--route-profile", type=Path, required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--mode", choices=SUPPORTED_MODES, default="normal")
    parser.add_argument("--route-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = validate_instruction_path(
        instruction_path=args.instruction, schema_path=args.schema,
        descriptor_path=args.descriptor, registry_path=args.registry,
        route_profile_path=args.route_profile, active_gate=args.gate,
        mode=args.mode, route_id=args.route_id,
    )
    payload = asdict(report)
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else report.reason_code)
    return 0 if report.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
