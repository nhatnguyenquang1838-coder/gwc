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

MATURITY = {"experimental": 0, "candidate": 0.5, "pilot": 1, "stable": 2}
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
        "compiled_profile_digest": None, "workflow_digest": None,
        "policy_registry_digest": None, "policy_ref": None, "policy_digest": None,
        "applicability": None, "applicability_decision_digest": None,
        "context_digest": None, "evidence_digest": None,
        "skipped_gates": [], "traversed_nodes": [],
        "terminal": None, "terminal_reason": None,
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
    if any(not descriptor.get(key) for key in ("node_id", "node_type", "authority_boundary", "gates")):
        return _blocked(reasons=["NODE_CONTRACT_INCOMPLETE"], **route_common)
    # Deterministic descriptor-to-runtime identity bridge: the catalog descriptor id
    # is kebab-case (validation-quality-ci-evidence-capture) while the runtime/card/
    # registry/route identifiers are dotted (validation_quality.ci-evidence-capture).
    # Reconcile them via the shared bridge so the catalog descriptor is never mutated.
    vin = _instruction_validator(root)
    if vin is not None and hasattr(vin, "bridge_node_identity"):
        id_match = vin.bridge_node_identity(descriptor.get("node_id")) == vin.bridge_node_identity(node_id)
    else:
        id_match = descriptor.get("node_id") == node_id
    if not id_match or gate not in descriptor.get("gates", []):
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


# ---------------------------------------------------------------------------
# Compiled Flow x Policy route resolution (SCRUM-394 P1-C)
#
# This is the sole runtime route decision path. Routes come from the compiled
# profile's closed route table (projected from Flow edges/conditions) and never
# from caller-supplied ``next_nodes``/``terminal_disposition``. Policy semantics
# are consumed from the Policy v2 applicability decision and are not
# reimplemented here.
# ---------------------------------------------------------------------------

FLOW_FAIL_CODES = {
    "COMPILED_PROFILE_MISSING", "COMPILED_PROFILE_NOT_COMPATIBLE",
    "COMPILED_PROFILE_DIGEST_DRIFT", "COMPILED_PROFILE_BINDING_STALE",
    "WORKFLOW_PARTICIPANT_UNBOUND", "WORKFLOW_GATE_CONTEXT_MISMATCH",
    "WORKFLOW_NEXT_ROUTE_DEAD_END", "WORKFLOW_NEXT_ROUTE_AMBIGUOUS",
    "WORKFLOW_TRAVERSAL_LOOP", "GATE_APPLICABILITY_BLOCKED",
    "AUTHORITY_REQUIREMENTS_UNSATISFIED", "EVIDENCE_REQUIREMENTS_UNSATISFIED",
    "POLICY_PROHIBITED_ACTION", "TERMINAL_ACCEPTANCE_UNMET",
    "TERMINAL_ACCEPTANCE_UNKNOWN", "POLICY_DECISION_PROVENANCE_MISMATCH",
    "WORKFLOW_SOURCE_DIGEST_DRIFT",
}
FAIL_CODES.update(FLOW_FAIL_CODES)

_MAX_TRAVERSAL_STEPS = 128


def _participant_gate_map(flow_profile: Mapping[str, Any]) -> dict[str, str | None]:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return {}
    result: dict[str, str | None] = {}
    for item in workflow.get("participants", []):
        if not isinstance(item, Mapping) or not item.get("participant"):
            continue
        gate = item.get("gate")
        result[str(item["participant"])] = str(gate) if gate else None
    return result


def _terminal_map(flow_profile: Mapping[str, Any]) -> dict[str, str]:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return {}
    return {
        str(item["node"]): str(item.get("outcome") or "TERMINAL")
        for item in workflow.get("terminal_nodes", [])
        if isinstance(item, Mapping) and item.get("node")
    }


def _edge_eligible(row: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    """Deterministic Flow discriminator; no caller-supplied route choice."""
    if row.get("runtime_executable") is not True:
        return False
    kind = str(row.get("kind") or "")
    if kind == "continue":
        return True
    if kind == "conditional":
        conditions = context.get("conditions")
        condition_id = str(row.get("condition_id") or "")
        return isinstance(conditions, Mapping) and conditions.get(condition_id) is True
    if kind in {"retry", "compensate", "blocked", "human_required", "terminal"}:
        return context.get("transition_kind") == kind
    return False


def _successors(route_table: Any, node: str, context: Mapping[str, Any]) -> tuple[list[str], str | None]:
    rows = [
        row for row in (route_table or [])
        if isinstance(row, Mapping) and row.get("source") == node and _edge_eligible(row, context)
    ]
    targets = list(dict.fromkeys(str(row.get("target")) for row in rows if row.get("target")))
    if not targets:
        return [], "WORKFLOW_NEXT_ROUTE_DEAD_END"
    if len(targets) > 1:
        return targets, "WORKFLOW_NEXT_ROUTE_AMBIGUOUS"
    return targets, None


def _unsatisfied(items: Any) -> bool:
    return isinstance(items, list) and any(
        isinstance(item, Mapping) and item.get("satisfied") is False for item in items
    )


def _enforce_required(decision: Mapping[str, Any], context: Mapping[str, Any]) -> list[str]:
    """Consume the Policy v2 decision; never re-derive Policy semantics."""
    reasons: list[str] = []
    requested = context.get("requested_action")
    prohibited = {str(item) for item in decision.get("prohibited_actions", []) if item}
    if requested is not None and str(requested) in prohibited:
        reasons.append("POLICY_PROHIBITED_ACTION")
    if _unsatisfied(decision.get("authority_requirements")):
        reasons.append("AUTHORITY_REQUIREMENTS_UNSATISFIED")
    if _unsatisfied(decision.get("evidence_requirements")):
        reasons.append("EVIDENCE_REQUIREMENTS_UNSATISFIED")
    return reasons


def _terminal_reasons(decision: Mapping[str, Any] | None) -> list[str]:
    if decision is None:
        return ["TERMINAL_ACCEPTANCE_UNKNOWN"]
    acceptance = decision.get("terminal_acceptance")
    if not isinstance(acceptance, Mapping):
        return ["TERMINAL_ACCEPTANCE_UNKNOWN"]
    if acceptance.get("accepted") is True:
        return []
    return ["TERMINAL_ACCEPTANCE_UNMET"]


def resolve_compiled_flow_route(
    *, compiled_profile: Mapping[str, Any], flow_profile: Mapping[str, Any],
    policy_registry: Mapping[str, Any], current_node: str,
    context: Mapping[str, Any], root: Path,
) -> dict[str, Any]:
    """Resolve the next deterministic Flow step under the bound Policy.

    Emits the canonical ``gate-node-route-decision`` artifact. ``NOT_APPLICABLE``
    skips its gate and traversal continues to the next applicable gate; it is
    never terminal by itself. A real Workflow terminal requires Policy
    ``terminal_acceptance``. Zero or ambiguous legal routes fail closed.
    """
    task_id = str(context.get("task_id", ""))
    gate_map = _participant_gate_map(flow_profile)
    current_gate = str(context.get("gate") or gate_map.get(current_node) or "GATE_NEUTRAL")
    action = str(context.get("requested_action") or "workflow_route_resolution")
    mode = str(context.get("workflow_mode", "normal"))
    common = dict(
        task_id=task_id, gate=current_gate, requested_action=action, mode=mode,
        profile_id=str(compiled_profile.get("profile_id", "")),
        profile_revision=str(compiled_profile.get("revision", "")),
        graph_revision=str(compiled_profile.get("bindings", {}).get("graph_registry_digest", "")),
        current_node=current_node,
    )

    workflow_digest = str(compiled_profile.get("workflow", {}).get("workflow_digest") or "") or None
    policy_registry_digest = str(compiled_profile.get("policy", {}).get("registry_digest") or "") or None
    compiled_digest = str(compiled_profile.get("compiled_digest") or "") or None
    evidence_digest = _digest({"evidence": context.get("evidence")})
    context_digest = _digest(dict(context))

    def emit(outcome: str, *, reasons: list[str], next_node: str | None = None,
             next_gate: str | None = None, applicability: str | None = None,
             applicability_decision: Mapping[str, Any] | None = None,
             skipped: list[str] | None = None, traversed: list[str] | None = None,
             terminal: bool | None = None, terminal_reason: str | None = None) -> dict[str, Any]:
        codes = list(dict.fromkeys(reasons)) or ["ROUTE_SELECTED"]
        payload = _base_payload(**common)
        payload.update({
            "outcome": outcome,
            "reason_code": codes[0], "reason_codes": codes,
            "next_node": next_node, "next_gate": next_gate,
            "next_action": context.get("next_action") if outcome == "ROUTE_SELECTED" else None,
            "compiled_profile_digest": compiled_digest,
            "workflow_digest": workflow_digest,
            "policy_registry_digest": policy_registry_digest,
            "policy_ref": str(applicability_decision.get("policy_ref")) if applicability_decision and applicability_decision.get("policy_ref") else None,
            "policy_digest": str(applicability_decision.get("policy_digest")) if applicability_decision and applicability_decision.get("policy_digest") else None,
            "applicability": applicability,
            "applicability_decision_digest": str(applicability_decision.get("decision_digest")) if applicability_decision and applicability_decision.get("decision_digest") else None,
            "context_digest": context_digest,
            "evidence_digest": evidence_digest,
            "skipped_gates": list(dict.fromkeys(skipped or [])),
            "traversed_nodes": list(traversed or []),
            "terminal": terminal,
            "terminal_reason": terminal_reason,
        })
        payload["decision_digest"] = _digest({k: v for k, v in payload.items() if k != "decision_digest"})
        return payload

    # --- exact compiled binding verification -------------------------------
    if not compiled_profile:
        return emit("BLOCKED", reasons=["COMPILED_PROFILE_MISSING"])
    if str(compiled_profile.get("result", {}).get("status")) != "COMPATIBLE":
        return emit("BLOCKED", reasons=["COMPILED_PROFILE_NOT_COMPATIBLE"])

    from tools.node_architect.compile_flow_policy_profile import compute_compiled_digest

    expected_digest = compute_compiled_digest(
        workflow_digest=str(workflow_digest or ""),
        policy=compiled_profile.get("policy", {}),
        bindings=compiled_profile.get("bindings", {}),
        compiler_version=str(compiled_profile.get("compiler_version") or ""),
    )
    if expected_digest != compiled_digest:
        return emit("BLOCKED", reasons=["COMPILED_PROFILE_DIGEST_DRIFT"])
    declared_workflow = flow_profile.get("compiled")
    declared_workflow_digest = declared_workflow.get("workflow_digest") if isinstance(declared_workflow, Mapping) else None
    if declared_workflow_digest != workflow_digest:
        return emit("BLOCKED", reasons=["COMPILED_PROFILE_BINDING_STALE"])
    # Live Workflow projection recompute: a declared digest that was frozen or
    # tampered while the live Flow composition moved must fail closed here,
    # even though declared == compiled above.
    from tools.node_architect.validate_flow_profile_workflow import (
        compile_workflow_projection,
    )

    try:
        live_workflow_digest = compile_workflow_projection(dict(flow_profile))["workflow_digest"]
    except Exception:
        return emit("BLOCKED", reasons=["WORKFLOW_SOURCE_DIGEST_DRIFT"])
    if live_workflow_digest != workflow_digest:
        return emit("BLOCKED", reasons=["WORKFLOW_SOURCE_DIGEST_DRIFT"])
    if _digest(policy_registry) != policy_registry_digest:
        return emit("BLOCKED", reasons=["COMPILED_PROFILE_BINDING_STALE"])

    if current_node not in gate_map:
        return emit("BLOCKED", reasons=["WORKFLOW_PARTICIPANT_UNBOUND"])
    bound_gate = gate_map.get(current_node)
    if context.get("gate") and bound_gate and str(context["gate"]) != bound_gate:
        return emit("BLOCKED", reasons=["WORKFLOW_GATE_CONTEXT_MISMATCH"])

    evaluator = _gate_applicability_evaluator(root)
    if evaluator is None:
        return emit("BLOCKED", reasons=["GATE_APPLICABILITY_BLOCKED"])

    def applicability_for(gate: str | None) -> Mapping[str, Any] | None:
        if not gate:
            return None
        try:
            return evaluator.evaluate_gate_applicability(
                flow_profile=flow_profile, policy_registry=policy_registry,
                gate=gate, context=dict(context),
            )
        except Exception:
            return None

    route_table = compiled_profile.get("compiled", {}).get("route_table", [])
    terminals = _terminal_map(flow_profile)

    # --- current gate ------------------------------------------------------
    current_decision = applicability_for(bound_gate)
    current_applicability: str | None = None
    if bound_gate:
        if current_decision is None:
            return emit("BLOCKED", reasons=["GATE_APPLICABILITY_BLOCKED"])
        if str(current_decision.get("policy_registry_digest") or "") != policy_registry_digest:
            return emit("BLOCKED", reasons=["POLICY_DECISION_PROVENANCE_MISMATCH"],
                        applicability_decision=current_decision)
        current_applicability = str(current_decision.get("decision") or "BLOCKED")
        if current_applicability == "BLOCKED":
            return emit("BLOCKED", reasons=["GATE_APPLICABILITY_BLOCKED"],
                        applicability="BLOCKED", applicability_decision=current_decision)
        if current_applicability == "REQUIRED":
            unmet = _enforce_required(current_decision, context)
            if unmet:
                return emit("BLOCKED", reasons=unmet, applicability="REQUIRED",
                            applicability_decision=current_decision)

    # --- terminal node -----------------------------------------------------
    if current_node in terminals:
        unmet = _terminal_reasons(current_decision)
        if unmet:
            return emit("BLOCKED", reasons=unmet, applicability=current_applicability,
                        applicability_decision=current_decision, terminal=True,
                        terminal_reason=unmet[0])
        return emit("TERMINAL", reasons=["WORKFLOW_TERMINAL_ACCEPTED"],
                    applicability=current_applicability,
                    applicability_decision=current_decision, terminal=True,
                    terminal_reason=terminals[current_node])

    # --- deterministic traversal to the next applicable gate ---------------
    skipped: list[str] = []
    # A current-node bound gate resolved NOT_APPLICABLE is an explicit skip and
    # must be recorded before traversal starts.
    if bound_gate and current_applicability == "NOT_APPLICABLE":
        skipped.append(str(bound_gate))
    traversed: list[str] = []
    visited = {current_node}
    node = current_node
    first_target: str | None = None
    for _ in range(_MAX_TRAVERSAL_STEPS):
        targets, route_error = _successors(route_table, node, context)
        if route_error:
            return emit("BLOCKED", reasons=[route_error], applicability=current_applicability,
                        applicability_decision=current_decision, skipped=skipped,
                        traversed=traversed)
        node = targets[0]
        if node in visited:
            return emit("BLOCKED", reasons=["WORKFLOW_TRAVERSAL_LOOP"],
                        applicability=current_applicability,
                        applicability_decision=current_decision, skipped=skipped,
                        traversed=traversed)
        visited.add(node)
        traversed.append(node)
        if first_target is None:
            first_target = node

        gate = gate_map.get(node)
        decision = applicability_for(gate)
        if gate:
            if decision is None:
                return emit("BLOCKED", reasons=["GATE_APPLICABILITY_BLOCKED"],
                            skipped=skipped, traversed=traversed)
            applicability = str(decision.get("decision") or "BLOCKED")
            if applicability == "BLOCKED":
                return emit("BLOCKED", reasons=["GATE_APPLICABILITY_BLOCKED"],
                            applicability="BLOCKED", applicability_decision=decision,
                            skipped=skipped, traversed=traversed)
            if applicability == "NOT_APPLICABLE":
                # Explicit gate skip: continue deterministic Flow traversal.
                skipped.append(gate)
                if node in terminals:
                    unmet = _terminal_reasons(decision)
                    if unmet:
                        return emit("BLOCKED", reasons=unmet, applicability=applicability,
                                    applicability_decision=decision, skipped=skipped,
                                    traversed=traversed, terminal=True, terminal_reason=unmet[0])
                    return emit("TERMINAL", reasons=["WORKFLOW_TERMINAL_ACCEPTED"],
                                next_node=first_target, applicability=applicability,
                                applicability_decision=decision, skipped=skipped,
                                traversed=traversed, terminal=True,
                                terminal_reason=terminals[node])
                continue
            # Boundary semantics: a traversed REQUIRED gate is the stop point.
            # The resolver returns the route to it and does NOT traverse
            # through it, and never enforces that future gate's authority /
            # evidence / prohibited-action requirements in this call.
            # Enforcement happens only when that gate/node becomes current.
            if applicability == "REQUIRED":
                return emit("ROUTE_SELECTED", reasons=["ROUTE_SELECTED", "NEXT_GATE_REQUIRED"],
                            next_node=first_target, next_gate=gate, applicability=applicability,
                            applicability_decision=decision, skipped=skipped,
                            traversed=traversed, terminal=False)
            # Any other/unknown applicability value fails closed.
            return emit("BLOCKED", reasons=["GATE_APPLICABILITY_BLOCKED"],
                        applicability=applicability, applicability_decision=decision,
                        skipped=skipped, traversed=traversed)

        if node in terminals:
            unmet = _terminal_reasons(applicability_for(gate_map.get(node)))
            if unmet:
                return emit("BLOCKED", reasons=unmet, skipped=skipped,
                            traversed=traversed, terminal=True, terminal_reason=unmet[0])
            return emit("TERMINAL", reasons=["WORKFLOW_TERMINAL_ACCEPTED"],
                        next_node=first_target, skipped=skipped, traversed=traversed,
                        terminal=True, terminal_reason=terminals[node])

    return emit("BLOCKED", reasons=["WORKFLOW_TRAVERSAL_LOOP"], skipped=skipped,
                traversed=traversed)


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
