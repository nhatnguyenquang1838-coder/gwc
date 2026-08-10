"""Resolve the exact active compiled Flow x Policy profile from the activation pointer.

Activation is a pointer to one immutable ``compiled_digest``. Rollback changes
the pointer to another previously registered COMPATIBLE digest; it never
rewrites Workflow, Policy or historical evidence. This module is pure and
performs no execution.

Activation is valid only while the immutable compiled artifact remains bound to
the exact live Workflow/Policy/registry/gate-lifecycle sources it was compiled
against. Self-consistency of the compiled artifact alone is insufficient.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from typing import Any, Mapping

from tools.node_architect.compile_flow_policy_profile import (
    GATE_LIFECYCLE_PATH,
    compute_compiled_digest,
)
from tools.node_architect.validate_flow_profile_workflow import compile_workflow_projection

ACTIVATION_PATH = "core/node-architect/flow-policy-activation-registry.json"
PROFILE_REGISTRY_PATH = "core/node-architect/profile-registry.json"
POLICY_REGISTRY_PATH = "core/node-architect/gate-applicability-policy-registry.json"
NODE_REGISTRY_PATH = "core/node-architect/node-registry.json"
SCENARIO_REGISTRY_PATH = "core/node-architect/scenario-registry.json"
GRAPH_REGISTRY_PATH = "core/node-architect/runtime-graph-registry.json"
ROUTE_PROFILE_PATH = "core/node-architect/gate-node-route-profile.json"


def _canonical_digest(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _text_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(root: Path, relative_path: str) -> Mapping[str, Any]:
    value = json.loads((root / relative_path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{relative_path} is not a JSON object")
    return value


def _verify_source_bindings(*, profile: Mapping[str, Any], root: Path) -> list[str]:
    """Verify the active compiled profile still binds the exact live source set.

    The compiled profile is immutable evidence, but activation is a live choice.
    A registry, Workflow, Policy, gate lifecycle or legacy compatibility
    projection may advance after compilation. Activation must therefore fail
    closed until a new compatible compiled profile is produced and selected.
    """
    reasons: list[str] = []

    try:
        profile_registry = _read_json(root, PROFILE_REGISTRY_PATH)
        policy_registry = _read_json(root, POLICY_REGISTRY_PATH)
        node_registry = _read_json(root, NODE_REGISTRY_PATH)
        scenario_registry = _read_json(root, SCENARIO_REGISTRY_PATH)
        graph_registry = _read_json(root, GRAPH_REGISTRY_PATH)
        route_profile = _read_json(root, ROUTE_PROFILE_PATH)
        gate_lifecycle_text = (root / GATE_LIFECYCLE_PATH).read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return ["ACTIVE_COMPILED_SOURCE_UNREADABLE"]

    workflow_binding = profile.get("workflow")
    workflow_binding = workflow_binding if isinstance(workflow_binding, Mapping) else {}
    flow_id = str(workflow_binding.get("id") or "")
    flow_version = str(workflow_binding.get("version") or "")
    flow_revision = str(workflow_binding.get("revision") or "")
    workflow_digest = str(workflow_binding.get("workflow_digest") or "")

    candidates = [
        item for item in profile_registry.get("profiles", [])
        if isinstance(item, Mapping) and str(item.get("id") or "") == flow_id
    ]
    if len(candidates) != 1:
        reasons.append("ACTIVE_WORKFLOW_SOURCE_UNRESOLVED")
    else:
        flow = candidates[0]
        if str(flow.get("version") or "") != flow_version:
            reasons.append("ACTIVE_WORKFLOW_VERSION_DRIFT")
        if str(flow.get("revision") or "") != flow_revision:
            reasons.append("ACTIVE_WORKFLOW_REVISION_DRIFT")
        try:
            live_workflow_digest = compile_workflow_projection(dict(flow))["workflow_digest"]
        except Exception:
            live_workflow_digest = ""
            reasons.append("ACTIVE_WORKFLOW_RECOMPILE_FAILED")
        if live_workflow_digest != workflow_digest:
            reasons.append("ACTIVE_WORKFLOW_DIGEST_DRIFT")

    policy_binding = profile.get("policy")
    policy_binding = policy_binding if isinstance(policy_binding, Mapping) else {}
    if _canonical_digest(policy_registry) != str(policy_binding.get("registry_digest") or ""):
        reasons.append("ACTIVE_POLICY_REGISTRY_DIGEST_DRIFT")
    if str(policy_registry.get("registry_id") or "") != str(policy_binding.get("registry_id") or ""):
        reasons.append("ACTIVE_POLICY_REGISTRY_ID_DRIFT")
    if str(policy_registry.get("revision") or "") != str(policy_binding.get("revision") or ""):
        reasons.append("ACTIVE_POLICY_REGISTRY_REVISION_DRIFT")

    live_policies = {
        str(item.get("id")): item
        for item in policy_registry.get("policies", [])
        if isinstance(item, Mapping) and item.get("id")
    }
    policy_refs = policy_binding.get("policy_refs")
    policy_refs = policy_refs if isinstance(policy_refs, Mapping) else {}
    for gate, binding in policy_refs.items():
        if not isinstance(binding, Mapping):
            reasons.append("ACTIVE_POLICY_REF_BINDING_INVALID")
            continue
        ref = str(binding.get("policy_ref") or "")
        live = live_policies.get(ref)
        if live is None:
            reasons.append("ACTIVE_POLICY_REF_UNRESOLVED")
            continue
        if str(live.get("version") or "") != str(binding.get("policy_version") or ""):
            reasons.append("ACTIVE_POLICY_VERSION_DRIFT")
        if _canonical_digest(live) != str(binding.get("policy_digest") or ""):
            reasons.append("ACTIVE_POLICY_DIGEST_DRIFT")

    bindings = profile.get("bindings")
    bindings = bindings if isinstance(bindings, Mapping) else {}
    live_registry_digests = {
        "node_registry_digest": _canonical_digest(node_registry),
        "scenario_registry_digest": _canonical_digest(scenario_registry),
        "graph_registry_digest": _canonical_digest(graph_registry),
    }
    for field, live_digest in live_registry_digests.items():
        if live_digest != str(bindings.get(field) or ""):
            reasons.append("ACTIVE_COMPILED_REGISTRY_BINDING_STALE")
            break

    if _text_digest(gate_lifecycle_text) != str(bindings.get("gate_lifecycle_digest") or ""):
        reasons.append("ACTIVE_GATE_LIFECYCLE_DIGEST_DRIFT")

    compiled = profile.get("compiled")
    compiled = compiled if isinstance(compiled, Mapping) else {}
    if str(route_profile.get("revision") or "") != str(compiled.get("legacy_route_projection_revision") or ""):
        reasons.append("ACTIVE_LEGACY_ROUTE_PROJECTION_DRIFT")
    if str(route_profile.get("workflow_profile_ref") or "") != flow_id:
        reasons.append("ACTIVE_LEGACY_ROUTE_WORKFLOW_BINDING_DRIFT")

    return list(dict.fromkeys(reasons))


def resolve_active_compiled_profile(
    *, activation_registry: Mapping[str, Any], root: Path,
) -> dict[str, Any]:
    """Return the active compiled profile plus a fail-closed activation decision."""
    reasons: list[str] = []
    active = str(activation_registry.get("active_compiled_profile") or "")
    entries = [
        item for item in activation_registry.get("registered", [])
        if isinstance(item, Mapping) and item.get("compiled_digest") == active
    ]
    if len(entries) != 1:
        return {"outcome": "BLOCKED", "reason_codes": ["ACTIVE_COMPILED_PROFILE_UNREGISTERED"],
                "compiled_profile": None, "compiled_digest": active or None}
    entry = entries[0]
    if str(entry.get("status")) != "COMPATIBLE":
        reasons.append("ACTIVE_COMPILED_PROFILE_NOT_COMPATIBLE")

    path = root / str(entry.get("profile_ref") or "")
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"outcome": "BLOCKED", "reason_codes": ["ACTIVE_COMPILED_PROFILE_UNREADABLE"],
                "compiled_profile": None, "compiled_digest": active}

    if str(profile.get("compiled_digest") or "") != active:
        reasons.append("ACTIVE_COMPILED_PROFILE_DIGEST_DRIFT")
    expected = compute_compiled_digest(
        workflow_digest=str(profile.get("workflow", {}).get("workflow_digest") or ""),
        policy=profile.get("policy", {}),
        bindings=profile.get("bindings", {}),
        compiler_version=str(profile.get("compiler_version") or ""),
    )
    if expected != active:
        reasons.append("ACTIVE_COMPILED_PROFILE_RECOMPUTE_MISMATCH")
    if str(profile.get("result", {}).get("status")) != "COMPATIBLE":
        reasons.append("ACTIVE_COMPILED_PROFILE_NOT_COMPATIBLE")

    reasons.extend(_verify_source_bindings(profile=profile, root=root))

    unique = list(dict.fromkeys(reasons))
    return {
        "outcome": "ACTIVE" if not unique else "BLOCKED",
        "reason_codes": unique or ["FLOW_POLICY_PROFILE_ACTIVE"],
        "compiled_profile": profile if not unique else None,
        "compiled_digest": active,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    registry = json.loads((args.root / ACTIVATION_PATH).read_text(encoding="utf-8"))
    result = resolve_active_compiled_profile(activation_registry=registry, root=args.root)
    printable = {k: v for k, v in result.items() if k != "compiled_profile"}
    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "ACTIVE" else 2


__all__ = [
    "resolve_active_compiled_profile",
    "ACTIVATION_PATH",
    "PROFILE_REGISTRY_PATH",
    "POLICY_REGISTRY_PATH",
    "NODE_REGISTRY_PATH",
    "SCENARIO_REGISTRY_PATH",
    "GRAPH_REGISTRY_PATH",
    "ROUTE_PROFILE_PATH",
]


if __name__ == "__main__":
    raise SystemExit(main())
