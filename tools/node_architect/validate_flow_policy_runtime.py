"""Validate exact activation of one Workflow + Policy pair for runtime use."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from tools.node_architect.validate_flow_policy_compatibility import validate_flow_policy_compatibility
from tools.node_architect.validate_flow_profile_workflow import validate_flow_profile_workflow


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _callable_exists(root: Path, ref: str) -> bool:
    path_text, sep, symbol = ref.partition(":")
    path = root / path_text
    if not sep or not symbol.isidentifier() or not path.is_file():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol
        for node in tree.body
    )


def validate_flow_policy_runtime(
    *, runtime_profile: Mapping[str, Any], flow_profile: Mapping[str, Any],
    policy_registry: Mapping[str, Any], route_profile: Mapping[str, Any], root: Path,
) -> dict[str, Any]:
    reasons: list[str] = []

    try:
        schema = json.loads((root / "schemas/runtime/flow-policy-runtime-profile.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(runtime_profile), key=lambda item: list(item.path))
        if errors:
            reasons.append("RUNTIME_PROFILE_SCHEMA_INVALID")
    except Exception:
        reasons.append("RUNTIME_PROFILE_SCHEMA_UNAVAILABLE")

    flow_result = validate_flow_profile_workflow(dict(flow_profile), root=root)
    if flow_result.get("outcome") != "PASS":
        reasons.append("WORKFLOW_CONTRACT_INVALID")
    compatibility = validate_flow_policy_compatibility(flow_profile=flow_profile, policy_registry=policy_registry)
    if not compatibility.get("compatible"):
        reasons.extend(str(code) for code in compatibility.get("reason_codes", []))

    workflow_binding = runtime_profile.get("workflow") if isinstance(runtime_profile.get("workflow"), Mapping) else {}
    declared_compiled = flow_profile.get("compiled") if isinstance(flow_profile.get("compiled"), Mapping) else {}
    if workflow_binding.get("profile_id") != flow_profile.get("id"):
        reasons.append("RUNTIME_WORKFLOW_ID_DRIFT")
    if workflow_binding.get("revision") != flow_profile.get("revision"):
        reasons.append("RUNTIME_WORKFLOW_REVISION_DRIFT")
    if workflow_binding.get("workflow_digest") != declared_compiled.get("workflow_digest"):
        reasons.append("RUNTIME_WORKFLOW_DIGEST_DRIFT")

    policy_binding = runtime_profile.get("policy") if isinstance(runtime_profile.get("policy"), Mapping) else {}
    if policy_binding.get("registry_id") != policy_registry.get("registry_id"):
        reasons.append("RUNTIME_POLICY_ID_DRIFT")
    if policy_binding.get("revision") != policy_registry.get("revision"):
        reasons.append("RUNTIME_POLICY_REVISION_DRIFT")
    if policy_binding.get("registry_digest") != _digest(policy_registry):
        reasons.append("RUNTIME_POLICY_DIGEST_DRIFT")

    route_binding = runtime_profile.get("route_profile") if isinstance(runtime_profile.get("route_profile"), Mapping) else {}
    if route_binding.get("profile_id") != route_profile.get("profile_id"):
        reasons.append("RUNTIME_ROUTE_PROFILE_ID_DRIFT")
    if route_binding.get("revision") != route_profile.get("revision"):
        reasons.append("RUNTIME_ROUTE_PROFILE_REVISION_DRIFT")
    if route_profile.get("workflow_profile_ref") != flow_profile.get("id"):
        reasons.append("RUNTIME_ROUTE_WORKFLOW_BINDING_MISMATCH")

    runtime = runtime_profile.get("runtime") if isinstance(runtime_profile.get("runtime"), Mapping) else {}
    for field, reason in (
        ("adapter_ref", "RUNTIME_ADAPTER_UNAVAILABLE"),
        ("compatibility_validator_ref", "RUNTIME_COMPATIBILITY_VALIDATOR_UNAVAILABLE"),
    ):
        ref = runtime.get(field)
        if not isinstance(ref, str) or not _callable_exists(root, ref):
            reasons.append(reason)
    schema_ref = runtime.get("decision_schema_ref")
    if not isinstance(schema_ref, str) or not (root / schema_ref).is_file():
        reasons.append("RUNTIME_DECISION_SCHEMA_UNAVAILABLE")
    else:
        try:
            Draft202012Validator.check_schema(json.loads((root / schema_ref).read_text(encoding="utf-8")))
        except Exception:
            reasons.append("RUNTIME_DECISION_SCHEMA_INVALID")

    if runtime_profile.get("status") != "active":
        reasons.append("RUNTIME_PROFILE_NOT_ACTIVE")

    unique = list(dict.fromkeys(reasons))
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_type": "flow-policy-runtime-activation-decision",
        "runtime_profile_id": str(runtime_profile.get("profile_id") or "unbound"),
        "runtime_profile_revision": str(runtime_profile.get("revision") or "unbound"),
        "workflow_digest": str(declared_compiled.get("workflow_digest") or "unbound"),
        "policy_registry_digest": _digest(policy_registry),
        "compatibility_digest": str(compatibility.get("decision_digest") or _digest(compatibility)),
        "outcome": "ACTIVATABLE" if not unique else "BLOCKED",
        "reason_codes": unique or ["FLOW_POLICY_RUNTIME_ACTIVATABLE"],
    }
    payload["decision_digest"] = _digest(payload)
    return payload


__all__ = ["validate_flow_policy_runtime"]
