"""Resolve a GWC gate/action pair to one instruction-backed executable node."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping

MATURITY = {"experimental": 0, "pilot": 1, "stable": 2}
SUPPORTED_MODES = {"normal", "fastlane", "e2e", "hotfix", "rescue"}
FAIL_CODES = {
    "NODE_CONTEXT_NOT_LOADED", "NODE_ROUTE_MISSING", "NODE_ROUTE_AMBIGUOUS",
    "NODE_CONTRACT_MISSING", "NODE_CONTRACT_INCOMPLETE",
    "NODE_IMPLEMENTATION_UNAVAILABLE", "NODE_NOT_EXECUTABLE_AT_MATURITY",
    "GATE_NODE_BINDING_MISMATCH", "GRAPH_REVISION_DRIFT",
    "PROFILE_REVISION_DRIFT", "NODE_INSTRUCTION_MISSING",
    "NODE_INSTRUCTION_INVALID", "NODE_EVIDENCE_CONTRACT_MISSING",
    "NODE_LOG_CONTRACT_MISSING", "NODE_NEXT_ROUTE_MISSING",
    "MODE_BYPASSES_NODE_RUNTIME", "NODE_AUTHORITY_ESCALATION_ATTEMPT",
    "FLOW_PROFILE_BINDING_MISMATCH", "GATE_APPLICABILITY_BLOCKED",
    "POLICY_REGISTRY_BINDING_MISMATCH",
}


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _graph_revision(graph: Mapping[str, Any]) -> str:
    revision = graph.get("revision")
    return str(revision.get("revision_id", "")) if isinstance(revision, Mapping) else str(revision or "")


def _node_registry_revision(registry: Mapping[str, Any]) -> str:
    revision = registry.get("revision")
    return str(revision.get("revision_id", "")) if isinstance(revision, Mapping) else str(revision or "")


def _node_map(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(node.get("id")): node for node in registry.get("nodes", []) if node.get("id")}


def _implementation_available(root: Path, implementation: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    """Check implementation presence without importing or executing implementation code."""
    kind = implementation.get("kind")
    ref = str(implementation.get("ref", ""))
    if kind == "connector":
        return ref in set(context.get("available_connectors", []))
    if kind not in {"python", "resolver"} or not ref:
        return False
    path_text, separator, callable_name = ref.partition(":")
    path = root / path_text
    if not separator or not path.is_file() or not callable_name.isidentifier():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == callable_name
        for node in tree.body
    )


def _instruction_validator(root: Path):
    path = root / "tools/node_architect/validate_node_instruction.py"
    if not path.is_file():
        return None
    name = "gwc_validate_node_instruction_runtime"
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _gate_applicability_evaluator(root: Path):
    path = root / "tools/node_architect/evaluate_gate_applicability.py"
    if not path.is_file():
        return None
    name = "gwc_evaluate_gate_applicability_runtime"
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _base_payload(*, task_id: str, gate: str, requested_action: str, mode: str,
                  profile_id: str = "", profile_revision: str = "",
                  graph_revision: str = "", route_id: str | None = None,
                  current_node: str | None = None,
                  implementation: Mapping[str, Any] | None = None,
                  required_context: list[str] | None = None,
                  loaded_context: list[str] | None = None,
                  instruction_ref: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.1", "artifact_type": "gate-node-route-decision",
        "task_id": task_id, "gate": gate, "requested_action": requested_action,
        "workflow_mode": mode, "profile_id": profile_id,
        "profile_revision": profile_revision, "graph_revision": graph_revision,
        "route_id": route_id, "current_node": current_node,
        "implementation": dict(implementation) if implementation else None,
        "required_context": required_context or [], "loaded_context": loaded_context or [],
        "node_instruction_ref": instruction_ref, "instruction_digest": None,
        "instruction_validated": False, "evidence_contract_valid": False,
        "log_contract_valid": False, "next_route_contract_valid": False,
        "mode_runtime_required": False,
        "next_node": None, "next_action": None, "next_gate": None,
        "authority_granted": False, "write_authority_granted": False,
        "pr_authority_granted": False, "merge_authority_granted": False,
        "deployment_authority_granted": False, "production_authority_granted": False,
    }


def _blocked(*, reasons: list[str], **kwargs: Any) -> dict[str, Any]:
    codes = list(dict.fromkeys(reasons))
    payload = _base_payload(**kwargs)
    payload.update({"outcome": "BLOCKED", "reason_code": codes[0], "reason_codes": codes})
    payload["decision_digest"] = _digest(payload)
    return payload


def _is_loaded(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set, str, bytes)):
        return bool(value)
    return True


def _load_bound_flow_profile(*, root: Path, route_profile: Mapping[str, Any],
                             flow_profile: Mapping[str, Any] | None) -> tuple[Mapping[str, Any] | None, str | None]:
    expected = str(route_profile.get("workflow_profile_ref") or "")
    if flow_profile is not None:
        actual = str(flow_profile.get("id") or "")
        if expected and actual != expected:
            return None, "FLOW_PROFILE_BINDING_MISMATCH"
        return flow_profile, None
    if not expected:
        return None, None

    path = root / "core/node-architect/profile-registry.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "FLOW_PROFILE_BINDING_MISMATCH"
    matches = [
        item for item in registry.get("profiles", [])
        if isinstance(item, Mapping) and item.get("id") == expected
    ]
    if len(matches) != 1:
        return None, "FLOW_PROFILE_BINDING_MISMATCH"
    return matches[0], None


def _load_gate_policy_registry(*, root: Path, flow_profile: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, str | None]:
    expected = str(flow_profile.get("policy_registry_ref") or "")
    if not expected:
        return None, "POLICY_REGISTRY_BINDING_MISMATCH"
    path = root / "core/node-architect/gate-applicability-policy-registry.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "POLICY_REGISTRY_BINDING_MISMATCH"
    if str(registry.get("registry_id") or "") != expected:
        return None, "POLICY_REGISTRY_BINDING_MISMATCH"
    return registry, None


def resolve_next_gate_applicability(*, route_profile: Mapping[str, Any],
                                    flow_profile: Mapping[str, Any] | None,
                                    next_gate: str | None,
                                    context: Mapping[str, Any],
                                    root: Path) -> dict[str, Any]:
    """Resolve effective next gate from workflow binding plus policy registry.

    A legacy route profile without ``workflow_profile_ref`` preserves its old
    behavior. Current profiles auto-load their bound flow profile and policy
    registry, so callers do not need gate-specific branching.
    """
    if next_gate is None:
        return {
            "outcome": "PASS", "next_gate": None,
            "reason_code": "GATE_APPLICABILITY_NOT_EVALUATED", "decision": None,
        }

    bound_flow, flow_error = _load_bound_flow_profile(
        root=root, route_profile=route_profile, flow_profile=flow_profile,
    )
    if flow_error:
        return {
            "outcome": "BLOCKED", "next_gate": next_gate,
            "reason_code": flow_error, "decision": None,
        }
    if bound_flow is None:
        return {
            "outcome": "PASS", "next_gate": next_gate,
            "reason_code": "GATE_APPLICABILITY_NOT_EVALUATED", "decision": None,
        }

    policy_registry, policy_error = _load_gate_policy_registry(root=root, flow_profile=bound_flow)
    if policy_error or policy_registry is None:
        return {
            "outcome": "BLOCKED", "next_gate": next_gate,
            "reason_code": policy_error or "POLICY_REGISTRY_BINDING_MISMATCH", "decision": None,
        }
    evaluator = _gate_applicability_evaluator(root)
    if evaluator is None:
        return {
            "outcome": "BLOCKED", "next_gate": next_gate,
            "reason_code": "GATE_APPLICABILITY_BLOCKED", "decision": None,
        }
    try:
        decision = evaluator.evaluate_gate_applicability(
            flow_profile=bound_flow,
            policy_registry=policy_registry,
            gate=next_gate,
            context=context,
        )
    except Exception:
        return {
            "outcome": "BLOCKED", "next_gate": next_gate,
            "reason_code": "GATE_APPLICABILITY_BLOCKED", "decision": None,
        }

    applicability = decision.get("decision")
    if applicability == "BLOCKED":
        return {
            "outcome": "BLOCKED", "next_gate": next_gate,
            "reason_code": "GATE_APPLICABILITY_BLOCKED", "decision": decision,
        }
    if applicability == "NOT_APPLICABLE":
        return {
            "outcome": "PASS", "next_gate": None,
            "reason_code": "NEXT_GATE_NOT_APPLICABLE", "decision": decision,
        }
    if applicability == "REQUIRED":
        return {
            "outcome": "PASS", "next_gate": next_gate,
            "reason_code": "NEXT_GATE_REQUIRED", "decision": decision,
        }
    return {
        "outcome": "BLOCKED", "next_gate": next_gate,
        "reason_code": "GATE_APPLICABILITY_BLOCKED", "decision": decision,
    }


def resolve_gate_node_route(*, profile: Mapping[str, Any], node_registry: Mapping[str, Any],
                            graph_registry: Mapping[str, Any], context: Mapping[str, Any],
                            root: Path, flow_profile: Mapping[str, Any] | None = None) -> dict[str, Any]:
    task_id = str(context.get("task_id", ""))
    gate = str(context.get("gate", ""))
    action = str(context.get("requested_action", ""))
    mode = str(context.get("workflow_mode", "normal"))
    profile_id = str(profile.get("profile_id", ""))
    profile_revision = str(profile.get("revision", ""))
    graph_revision = _graph_revision(graph_registry)
    common = dict(task_id=task_id, gate=gate, requested_action=action, mode=mode,
                  profile_id=profile_id, profile_revision=profile_revision,
                  graph_revision=graph_revision)

    if mode not in SUPPORTED_MODES:
        return _blocked(reasons=["MODE_BYPASSES_NODE_RUNTIME"], **common)
    expected_profile = str(context.get("expected_profile_revision", profile_revision))
    if expected_profile != profile_revision:
        return _blocked(reasons=["PROFILE_REVISION_DRIFT"], **common)
    expected_graph = str(context.get("expected_graph_revision", graph_revision))
    if expected_graph != graph_revision or str(profile.get("bound_graph_revision")) != graph_revision:
        return _blocked(reasons=["GRAPH_REVISION_DRIFT"], **common)
    if str(profile.get("bound_node_registry_revision")) != _node_registry_revision(node_registry):
        return _blocked(reasons=["PROFILE_REVISION_DRIFT"], **common)

    routes = [r for r in profile.get("routes", []) if r.get("gate") == gate and r.get("requested_action") == action]
    if not routes:
        return _blocked(reasons=["NODE_ROUTE_MISSING"], **common)
    if len(routes) != 1:
        return _blocked(reasons=["NODE_ROUTE_AMBIGUOUS"], **common)
    route = routes[0]
    route_id = str(route.get("route_id", ""))
    node_id = str(route.get("current_node", ""))
    implementation = route.get("implementation", {})
    instruction_ref = str(route.get("node_instruction_ref", "")) or None
    required_context = list(route.get("required_context", []))
    context_payload = context.get("context", {})
    if not isinstance(context_payload, Mapping):
        context_payload = {}
    loaded_context = sorted(k for k in required_context if _is_loaded(context_payload.get(k)))
    route_common = dict(**common, route_id=route_id, current_node=node_id,
                        implementation=implementation, required_context=required_context,
                        loaded_context=loaded_context, instruction_ref=instruction_ref)
    if len(loaded_context) != len(required_context):
        return _blocked(reasons=["NODE_CONTEXT_NOT_LOADED"], **route_common)

    envelope = context_payload.get("g2_envelope", {})
    approval = context_payload.get("approval_receipt", {})
    claim = context_payload.get("task_claim", {})
    envelope_invalid = not isinstance(envelope, Mapping) or any([
        str(envelope.get("task_id", "")) != task_id,
        str(envelope.get("authority_gate", "")) != gate,
        str(envelope.get("repository", "")) != str(context.get("repository", "")),
        str(envelope.get("base_sha", "")) != str(context.get("base_sha", "")),
        str(envelope.get("working_branch", "")) != str(context.get("working_branch", "")),
        str(envelope.get("scope_hash", "")) != str(context.get("scope_hash", "")),
    ])
    approval_invalid = not isinstance(approval, Mapping) or approval.get("status") not in {"VALID", "APPROVED", "PASS"}
    claim_invalid = not isinstance(claim, Mapping) or not claim.get("agent")
    if envelope_invalid or approval_invalid or claim_invalid:
        return _blocked(reasons=["GATE_NODE_BINDING_MISMATCH"], **route_common)

    nodes = _node_map(node_registry)
    node = nodes.get(node_id)
    if node is None:
        return _blocked(reasons=["NODE_CONTRACT_MISSING"], **route_common)
    descriptor_ref = str(route.get("node_descriptor_ref", ""))
    descriptor_path = root / descriptor_ref
    if not descriptor_ref or not descriptor_path.is_file():
        return _blocked(reasons=["NODE_CONTRACT_MISSING"], **route_common)
    try:
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except Exception:
        descriptor = {}
    if any(not descriptor.get(key) for key in ("node_id", "node_type", "authority_boundary", "gates")):
        return _blocked(reasons=["NODE_CONTRACT_INCOMPLETE"], **route_common)
    if descriptor.get("node_id") != node_id or gate not in descriptor.get("gates", []):
        return _blocked(reasons=["GATE_NODE_BINDING_MISMATCH"], **route_common)

    current_maturity = str(node.get("maturity", ""))
    minimum_maturity = str(route.get("minimum_maturity", "stable"))
    if MATURITY.get(current_maturity, -1) < MATURITY.get(minimum_maturity, 99):
        return _blocked(reasons=["NODE_NOT_EXECUTABLE_AT_MATURITY"], **route_common)
    if node.get("source_status") == "proposed_registry_slot" and not route.get("allow_proposed_with_implementation", False):
        return _blocked(reasons=["NODE_NOT_EXECUTABLE_AT_MATURITY"], **route_common)
    if not _implementation_available(root, implementation, context):
        return _blocked(reasons=["NODE_IMPLEMENTATION_UNAVAILABLE"], **route_common)

    if not instruction_ref or not (root / instruction_ref).is_file():
        return _blocked(reasons=["NODE_INSTRUCTION_MISSING"], **route_common)
    validator = _instruction_validator(root)
    if validator is None:
        return _blocked(reasons=["NODE_INSTRUCTION_INVALID"], **route_common)
    try:
        card = validator.load_data(root / instruction_ref)
        schema = validator.load_data(root / "schemas/node-architect/node-instruction.schema.json")
        report = validator.validate_instruction(
            card=card, schema=schema, descriptor=descriptor, registry_node=node,
            route=route, active_gate=gate, mode=mode,
        )
    except Exception:
        return _blocked(reasons=["NODE_INSTRUCTION_INVALID"], **route_common)
    if not report.valid:
        payload = _blocked(reasons=report.reason_codes, **route_common)
        payload.update({
            "instruction_digest": report.instruction_digest,
            "evidence_contract_valid": report.evidence_contract_valid,
            "log_contract_valid": report.log_contract_valid,
            "next_route_contract_valid": report.next_route_contract_valid,
            "mode_runtime_required": report.mode_runtime_required,
        })
        payload["decision_digest"] = _digest({k: v for k, v in payload.items() if k != "decision_digest"})
        return payload

    next_gate_result = resolve_next_gate_applicability(
        route_profile=profile,
        flow_profile=flow_profile,
        next_gate=route.get("next_gate"),
        context=context,
        root=root,
    )
    if next_gate_result["outcome"] != "PASS":
        return _blocked(reasons=[str(next_gate_result["reason_code"])], **route_common)

    reason_codes = ["ROUTE_SELECTED"]
    if route.get("next_gate") is not None:
        reason_codes.append(str(next_gate_result["reason_code"]))
    payload = _base_payload(**route_common)
    payload.update({
        "outcome": "ROUTE_SELECTED", "instruction_digest": report.instruction_digest,
        "instruction_validated": True,
        "evidence_contract_valid": report.evidence_contract_valid,
        "log_contract_valid": report.log_contract_valid,
        "next_route_contract_valid": report.next_route_contract_valid,
        "mode_runtime_required": report.mode_runtime_required,
        "next_node": route.get("next_node"), "next_action": route.get("next_action"),
        "next_gate": next_gate_result["next_gate"], "reason_code": "ROUTE_SELECTED",
        "reason_codes": reason_codes,
    })
    payload["decision_digest"] = _digest(payload)
    return payload


def _load(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--flow-profile", type=Path)
    parser.add_argument("--node-registry", type=Path, required=True)
    parser.add_argument("--graph-registry", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    args = parser.parse_args()
    decision = resolve_gate_node_route(
        profile=_load(args.profile),
        flow_profile=_load(args.flow_profile) if args.flow_profile else None,
        node_registry=_load(args.node_registry),
        graph_registry=_load(args.graph_registry),
        context=_load(args.context),
        root=args.root,
    )
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0 if decision["outcome"] == "ROUTE_SELECTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
