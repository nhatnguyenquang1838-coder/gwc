"""Compile one Workflow composition against one Policy registry into a static profile.

Layer boundary (SCRUM-394 P1-C):

    workflow_digest = hash(Workflow composition semantics only)   # Flow lane
    policy_digest   = hash(Policy semantics only)                 # Policy lane
    compiled_digest = hash(workflow_digest + policy digests
                           + exact registry/gate-lifecycle bindings
                           + compiler version)                    # this lane

The compiler is pure and side-effect free. It produces a static
``flow-policy-compiled-profile``: an immutable proof that one exact Workflow
revision and one exact Policy revision can be activated together, plus the
closed route table derived from Flow edges. It carries no live execution
state, grants no authority and reimplements no Policy semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from typing import Any, Mapping, Sequence

from tools.node_architect.validate_flow_policy_compatibility import (
    validate_flow_policy_compatibility,
)
from tools.node_architect.validate_flow_profile_workflow import (
    CANONICAL_GATES,
    canonical_edge_kind,
    compile_workflow_projection,
)

COMPILER_VERSION = "flow-policy-compiler/1.0.0"
COMPILED_SCHEMA_VERSION = "1.0.0"
GATE_LIFECYCLE_PATH = "core/GATE_LIFECYCLE_CONTRACT_v1.0.md"
GATE_LIFECYCLE_REVISION = "1.0"

_COMPOSITION_REGISTRIES = ("node", "scenario", "graph")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _participant_gates(flow_profile: Mapping[str, Any]) -> dict[str, str | None]:
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return {}
    gates: dict[str, str | None] = {}
    for item in _mappings(workflow.get("participants")):
        name = item.get("participant")
        if not name:
            continue
        gate = item.get("gate")
        gates[str(name)] = str(gate) if gate else None
    return gates


def _binding_digest(flow_profile: Mapping[str, Any], registry: str) -> str | None:
    for item in _mappings(flow_profile.get("registry_bindings")):
        if item.get("registry") == registry:
            value = item.get("digest")
            return str(value) if value else None
    return None


def _gate_lifecycle_digest(root: Path | None) -> str:
    if root is None:
        return _text_digest(GATE_LIFECYCLE_REVISION)
    path = root / GATE_LIFECYCLE_PATH
    try:
        return _text_digest(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return _text_digest(GATE_LIFECYCLE_REVISION)


def compile_route_table(flow_profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Closed, deterministic route table projected from Flow edges only."""
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return []
    gates = _participant_gates(flow_profile)
    rows: list[dict[str, Any]] = []
    for edge in _mappings(workflow.get("edges")):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target:
            continue
        kind = canonical_edge_kind(str(edge.get("kind") or "")) or "blocked"
        condition = edge.get("condition_id")
        rows.append({
            "source": source,
            "target": target,
            "kind": kind,
            "condition_id": str(condition) if condition else None,
            "runtime_executable": bool(edge.get("runtime_executable")),
            "source_gate": gates.get(source),
            "target_gate": gates.get(target),
        })
    rows.sort(key=lambda row: (row["source"], row["target"], row["kind"], row["condition_id"] or ""))
    return rows


def compile_terminal_bindings(flow_profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Terminal nodes bound to the Policy that owns their terminal acceptance."""
    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, Mapping):
        return []
    gates = _participant_gates(flow_profile)
    gate_policy = {
        str(item.get("gate")): str(item.get("policy_ref") or "") or None
        for item in _mappings(workflow.get("gate_bindings"))
        if item.get("gate")
    }
    rows: list[dict[str, Any]] = []
    for item in _mappings(workflow.get("terminal_nodes")):
        node = str(item.get("node") or "")
        if not node:
            continue
        gate = gates.get(node)
        rows.append({
            "node": node,
            "outcome": str(item.get("outcome") or "TERMINAL"),
            "gate": gate,
            "policy_ref": gate_policy.get(gate) if gate else None,
        })
    rows.sort(key=lambda row: row["node"])
    return rows


def compute_compiled_digest(*, workflow_digest: str, policy: Mapping[str, Any],
                            bindings: Mapping[str, Any],
                            compiler_version: str = COMPILER_VERSION) -> str:
    """Cross-layer identity.

    Deliberately bound to identity inputs only (workflow digest, exact Policy
    digests, exact registry/gate-lifecycle bindings, compiler version) so that
    the digest is stable for a re-compilation of the same inputs and changes
    whenever any bound layer changes.
    """
    return _digest({
        "compiler_version": compiler_version,
        "workflow_digest": workflow_digest,
        "policy": {
            "registry_id": policy.get("registry_id"),
            "revision": policy.get("revision"),
            "registry_digest": policy.get("registry_digest"),
            "policy_refs": policy.get("policy_refs"),
        },
        "bindings": dict(bindings),
    })


def compile_flow_policy_profile(
    *, flow_profile: Mapping[str, Any], policy_registry: Mapping[str, Any],
    route_profile: Mapping[str, Any], root: Path | None = None,
    profile_id: str = "gwc-flow-policy-compiled-v1",
    revision: str | None = None,
) -> dict[str, Any]:
    """Return the static compiled profile for one exact Flow/Policy pair."""
    compatibility = validate_flow_policy_compatibility(
        flow_profile=flow_profile, policy_registry=policy_registry,
    )
    reasons = [str(code) for code in compatibility.get("reason_codes", [])]
    compatible = bool(compatibility.get("compatible"))

    declared = flow_profile.get("compiled")
    declared_digest = declared.get("workflow_digest") if isinstance(declared, Mapping) else None
    try:
        expected_digest = compile_workflow_projection(dict(flow_profile))["workflow_digest"]
    except Exception:
        expected_digest = None
        compatible = False
        reasons.append("WORKFLOW_COMPILE_FAILED")
    workflow_digest = str(declared_digest or expected_digest or "unbound")
    if expected_digest and declared_digest and declared_digest != expected_digest:
        compatible = False
        reasons.append("WORKFLOW_COMPILED_DIGEST_DRIFT")

    workflow = flow_profile.get("workflow")
    workflow = workflow if isinstance(workflow, Mapping) else {}
    policies = {str(item.get("id")): item for item in _mappings(policy_registry.get("policies")) if item.get("id")}
    policy_refs: dict[str, dict[str, str]] = {}
    for binding in _mappings(workflow.get("gate_bindings")):
        gate = str(binding.get("gate") or "")
        ref = str(binding.get("policy_ref") or "")
        if gate not in CANONICAL_GATES:
            compatible = False
            reasons.append("NON_CANONICAL_GATE")
            continue
        policy = policies.get(ref)
        if policy is None:
            compatible = False
            reasons.append("GATE_POLICY_MISSING")
            continue
        policy_refs[gate] = {
            "policy_ref": ref,
            "policy_version": str(policy.get("version") or "unbound"),
            "policy_digest": _digest(policy),
        }
    if set(policy_refs) != set(CANONICAL_GATES):
        compatible = False
        reasons.append("GATE_POLICY_COVERAGE_INCOMPLETE")

    policy_block = {
        "registry_id": str(policy_registry.get("registry_id") or "unbound"),
        "revision": str(policy_registry.get("revision") or "unbound"),
        "registry_digest": _digest(policy_registry),
        "policy_refs": policy_refs,
    }

    bindings: dict[str, Any] = {}
    for registry in _COMPOSITION_REGISTRIES:
        digest = _binding_digest(flow_profile, registry)
        if digest is None:
            compatible = False
            reasons.append("COMPOSITION_BINDING_MISSING")
        bindings[f"{registry}_registry_digest"] = digest or ("sha256:" + "0" * 64)
    bindings["gate_lifecycle_revision"] = GATE_LIFECYCLE_REVISION
    bindings["gate_lifecycle_digest"] = _gate_lifecycle_digest(root)

    legacy_revision = str(route_profile.get("revision") or "unbound")
    if str(route_profile.get("workflow_profile_ref") or "") != str(flow_profile.get("id") or ""):
        compatible = False
        reasons.append("LEGACY_ROUTE_PROJECTION_UNBOUND")

    unique = [code for code in dict.fromkeys(reasons) if code != "FLOW_POLICY_COMPATIBLE"]
    profile: dict[str, Any] = {
        "schema_version": COMPILED_SCHEMA_VERSION,
        "artifact_type": "flow-policy-compiled-profile",
        "compiler_version": COMPILER_VERSION,
        "profile_id": profile_id,
        "revision": revision or str(flow_profile.get("revision") or "unbound"),
        "workflow": {
            "id": str(flow_profile.get("id") or "unbound"),
            "version": str(flow_profile.get("version") or "unbound"),
            "revision": str(flow_profile.get("revision") or "unbound"),
            "workflow_digest": workflow_digest,
        },
        "policy": policy_block,
        "bindings": bindings,
        "compiled": {
            "route_table": compile_route_table(flow_profile),
            "terminal_acceptance_bindings": compile_terminal_bindings(flow_profile),
            "legacy_route_projection_revision": legacy_revision,
        },
        "result": {
            "status": "COMPATIBLE" if compatible and not unique else "BLOCKED",
            "reason_codes": unique or ["FLOW_POLICY_COMPILED"],
        },
    }
    profile["compiled_digest"] = compute_compiled_digest(
        workflow_digest=workflow_digest, policy=policy_block, bindings=bindings,
    )
    return profile


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--flow-profile-id", default="full-flow-v3")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    registry = _load(args.root / "core/node-architect/profile-registry.json")
    flow = next(item for item in registry["profiles"] if item.get("id") == args.flow_profile_id)
    policy = _load(args.root / "core/node-architect/gate-applicability-policy-registry.json")
    route = _load(args.root / "core/node-architect/gate-node-route-profile.json")
    profile = compile_flow_policy_profile(
        flow_profile=flow, policy_registry=policy, route_profile=route, root=args.root,
    )
    text = json.dumps(profile, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if profile["result"]["status"] == "COMPATIBLE" else 2


__all__ = [
    "compile_flow_policy_profile",
    "compile_route_table",
    "compile_terminal_bindings",
    "compute_compiled_digest",
    "COMPILER_VERSION",
]


if __name__ == "__main__":
    raise SystemExit(main())
