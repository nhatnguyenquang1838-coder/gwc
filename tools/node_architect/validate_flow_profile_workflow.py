"""Flow-only Workflow contract validator and deterministic compiler.

Scope (SCRUM-392, lane P1-A):
    Flow Profile v2 == Workflow composition contract.

This module owns COMPOSITION checks only:
    * membership of nodes/scenarios in the bound registries
    * typed edge totality
    * deterministic entry/terminal reachability
    * cycle legality (only retry/compensate/reconciliation cycles allowed)
    * canonical gate binding or explicit gate_neutral for every participant
    * gate bindings expressed exclusively by ``policy_ref``
    * registry revision/digest binding (stale composition fails closed)
    * v1 compatibility / deterministic migration
    * deterministic compiled workflow digest

It MUST NOT evaluate gate applicability, authority, evidence acceptance,
prohibited actions, terminal acceptance, or any live runtime state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

CANONICAL_GATES = (
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION_DATA",
)

# v2 canonical typed edge semantics.
V2_EDGE_KINDS = (
    "continue",
    "conditional",
    "retry",
    "compensate",
    "blocked",
    "human_required",
    "terminal",
)

# v1 edge kinds retained for backward compatibility, mapped deterministically.
V1_EDGE_KIND_MAP = {
    "runtime": "continue",
    "dependency": "continue",
    "conditional": "conditional",
    "history": "continue",
    "human_authority": "human_required",
}

CYCLE_LEGAL_KINDS = frozenset({"retry", "compensate"})

PROJECTION_VERSION = "2.0.0"

# Registries whose content identity IS Workflow composition semantics.
# 'policy' is intentionally excluded: Policy content identity belongs to the
# Policy lane digest, and the combined identity to the P1-C compiled profile.
COMPOSITION_REGISTRIES = frozenset({"node", "scenario", "graph"})

REGISTRY_PATHS = {
    "node": "core/node-architect/node-registry.json",
    "scenario": "core/node-architect/scenario-registry.json",
    "graph": "core/node-architect/runtime-graph-registry.json",
    "policy": "core/node-architect/gate-applicability-policy-registry.json",
}

REGISTRY_ID_KEYS = ("registry_id", "graph_id")


class FlowContractError(Exception):
    """Raised for CLI-level failures (unreadable inputs)."""


def _finding(code: str, message: str, **detail: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "message": message}
    if detail:
        item["detail"] = detail
    return item


def canonical_edge_kind(kind: str) -> str | None:
    """Deterministically map any accepted edge kind to the v2 canonical set."""
    if kind in V2_EDGE_KINDS:
        return kind
    return V1_EDGE_KIND_MAP.get(kind)


def file_digest(path: Path) -> str:
    """sha256 over the canonical JSON projection of a registry file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def compile_workflow_projection(flow_profile: dict[str, Any]) -> dict[str, Any]:
    """Deterministic compiled projection of the workflow composition.

    Layer boundary (P1-C reconciliation, SCRUM-392):

        workflow_digest = hash(Workflow composition semantics only)
        policy_digest   = hash(Policy semantics only)          # Policy lane
        compiled_digest = hash(workflow + policy + bindings)   # P1-C lane

    Therefore this projection covers workflow structure plus the *composition*
    registry bindings (node/scenario/graph) only. ``policy_ref`` is carried as
    an opaque Flow composition reference; the Policy registry content
    revision/digest is deliberately excluded so that a Policy-only revision
    never mutates Workflow identity. Flow-profile ``revision`` is excluded for
    the same reason: it is release metadata, not composition semantics.
    """
    workflow = flow_profile.get("workflow") or {}
    projection = {
        "projection_version": PROJECTION_VERSION,
        "flow_id": flow_profile.get("id"),
        "flow_version": flow_profile.get("version"),
        "entry_nodes": sorted(workflow.get("entry_nodes", [])),
        "terminal_nodes": sorted(
            (item["node"], item["outcome"]) for item in workflow.get("terminal_nodes", [])
        ),
        "edges": sorted(
            (
                edge["source"],
                edge["target"],
                canonical_edge_kind(edge["kind"]) or edge["kind"],
                bool(edge.get("runtime_executable")),
                edge.get("condition_id"),
            )
            for edge in workflow.get("edges", [])
        ),
        "participants": sorted(
            (
                item["participant"],
                item["participant_kind"],
                item.get("gate") or "GATE_NEUTRAL",
            )
            for item in workflow.get("participants", [])
        ),
        "gate_bindings": sorted(
            (item["gate"], item["policy_ref"]) for item in workflow.get("gate_bindings", [])
        ),
        "registry_bindings": sorted(
            (item["registry"], item["registry_id"], item["revision"], item["digest"])
            for item in flow_profile.get("registry_bindings", [])
            if item["registry"] in COMPOSITION_REGISTRIES
        ),
    }
    blob = json.dumps(projection, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = "sha256:" + hashlib.sha256(blob).hexdigest()
    return {"projection": projection, "workflow_digest": digest}


def _registry_ids(payload: dict[str, Any]) -> str | None:
    for key in REGISTRY_ID_KEYS:
        if key in payload:
            return payload[key]
    return None


def _registry_revision(payload: dict[str, Any]) -> str | None:
    revision = payload.get("revision")
    if isinstance(revision, dict):
        return revision.get("revision_id")
    return revision


def _detect_illegal_cycles(edges: Iterable[dict[str, Any]]) -> list[list[str]]:
    """Return cycles that traverse only non-retry/non-compensate edges."""
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        kind = canonical_edge_kind(edge["kind"]) or edge["kind"]
        if kind in CYCLE_LEGAL_KINDS and edge.get("cycle_allowed") is True:
            continue
        adjacency.setdefault(edge["source"], []).append(edge["target"])

    cycles: list[list[str]] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for nxt in adjacency.get(node, []):
            if state.get(nxt, 0) == 0:
                visit(nxt)
            elif state.get(nxt) == 1:
                cycles.append(stack[stack.index(nxt):] + [nxt])
        stack.pop()
        state[node] = 2

    for node in list(adjacency):
        if state.get(node, 0) == 0:
            visit(node)
    return cycles


def validate_flow_profile_workflow(
    flow_profile: dict[str, Any],
    *,
    node_registry: dict[str, Any] | None = None,
    scenario_registry: dict[str, Any] | None = None,
    graph_registry: dict[str, Any] | None = None,
    policy_registry: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Validate the Flow (= Workflow) composition contract. Fails closed."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]

    def load(name: str, given: dict[str, Any] | None) -> dict[str, Any]:
        if given is not None:
            return given
        return json.loads((root / REGISTRY_PATHS[name]).read_text(encoding="utf-8"))

    node_registry = load("node", node_registry)
    scenario_registry = load("scenario", scenario_registry)
    graph_registry = load("graph", graph_registry)
    policy_registry = load("policy", policy_registry)

    findings: list[dict[str, Any]] = []
    version = str(flow_profile.get("version", ""))
    is_v2 = version.startswith("2.")

    if not is_v2:
        return {
            "outcome": "PASS",
            "reason_code": "FLOW_PROFILE_V1_COMPATIBLE",
            "flow_id": flow_profile.get("id"),
            "version": version,
            "findings": [],
            "compiled": None,
        }

    workflow = flow_profile.get("workflow")
    if not isinstance(workflow, dict):
        findings.append(_finding("WORKFLOW_CONTRACT_MISSING", "v2 flow profile has no workflow block"))
        return {
            "outcome": "BLOCKED",
            "reason_code": "WORKFLOW_CONTRACT_MISSING",
            "flow_id": flow_profile.get("id"),
            "version": version,
            "findings": findings,
            "compiled": None,
        }

    node_ids = {item["id"] for item in node_registry.get("nodes", []) if isinstance(item, dict)}
    node_ids.update(item for item in node_registry.get("nodes", []) if isinstance(item, str))
    scenario_ids = {
        item.get("id")
        for item in scenario_registry.get("scenarios", [])
        if isinstance(item, dict)
    }
    policy_ids = {item["id"] for item in policy_registry.get("policies", [])}

    entry_nodes = list(workflow.get("entry_nodes", []))
    terminal_items = list(workflow.get("terminal_nodes", []))
    terminal_nodes = [item["node"] for item in terminal_items]
    edges = list(workflow.get("edges", []))
    participants = list(workflow.get("participants", []))

    # --- membership -------------------------------------------------------
    referenced: set[str] = set(entry_nodes) | set(terminal_nodes)
    for edge in edges:
        referenced.add(edge["source"])
        referenced.add(edge["target"])
    unknown = sorted(referenced - node_ids)
    if unknown:
        findings.append(
            _finding("WORKFLOW_NODE_NOT_IN_REGISTRY", "workflow references unknown nodes", nodes=unknown)
        )

    # --- typed edge totality ---------------------------------------------
    for edge in edges:
        canonical = canonical_edge_kind(edge["kind"])
        if canonical is None:
            findings.append(
                _finding("WORKFLOW_EDGE_KIND_UNTYPED", "edge kind is not mappable to v2 semantics", edge=edge)
            )
            continue
        if canonical == "conditional" and not edge.get("condition_id"):
            findings.append(
                _finding("WORKFLOW_CONDITIONAL_EDGE_UNBOUND", "conditional edge lacks condition_id", edge=edge)
            )
        if canonical in CYCLE_LEGAL_KINDS and edge.get("cycle_allowed") is not True:
            findings.append(
                _finding(
                    "WORKFLOW_CYCLE_EDGE_NOT_DECLARED",
                    "retry/compensate edge must declare cycle_allowed=true",
                    edge=edge,
                )
            )

    # --- reachability -----------------------------------------------------
    if not entry_nodes:
        findings.append(_finding("WORKFLOW_ENTRY_MISSING", "no entry nodes declared"))
    forward: dict[str, list[str]] = {}
    backward: dict[str, list[str]] = {}
    for edge in edges:
        forward.setdefault(edge["source"], []).append(edge["target"])
        backward.setdefault(edge["target"], []).append(edge["source"])

    def closure(seeds: Iterable[str], graph: dict[str, list[str]]) -> set[str]:
        seen: set[str] = set()
        stack = list(seeds)
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(graph.get(cur, []))
        return seen

    reachable = closure(entry_nodes, forward)
    orphans = sorted(referenced - reachable)
    if orphans:
        findings.append(
            _finding("WORKFLOW_ORPHAN_NODE", "nodes unreachable from entry set", nodes=orphans)
        )

    co_reachable = closure(terminal_nodes, backward)
    dead_ends = sorted(reachable - co_reachable)
    if dead_ends:
        findings.append(
            _finding(
                "WORKFLOW_TERMINAL_UNREACHABLE",
                "nodes cannot reach any declared terminal node",
                nodes=dead_ends,
            )
        )

    for item in terminal_items:
        if forward.get(item["node"]):
            findings.append(
                _finding(
                    "WORKFLOW_TERMINAL_NOT_TERMINAL",
                    "terminal node has outgoing edges",
                    node=item["node"],
                )
            )

    # --- cycles -----------------------------------------------------------
    for cycle in _detect_illegal_cycles(edges):
        findings.append(
            _finding("WORKFLOW_INVALID_CYCLE", "cycle is not typed as retry/compensation", cycle=cycle)
        )

    # --- participants: gate binding or explicit gate_neutral --------------
    declared_participants = {item["participant"] for item in participants}
    missing_participants = sorted(referenced - declared_participants)
    if missing_participants:
        findings.append(
            _finding(
                "WORKFLOW_PARTICIPANT_UNDECLARED",
                "executable participants missing gate binding declaration",
                participants=missing_participants,
            )
        )
    for item in participants:
        has_gate = "gate" in item
        neutral = item.get("gate_neutral") is True
        if has_gate == neutral:
            findings.append(
                _finding(
                    "WORKFLOW_PARTICIPANT_GATE_AMBIGUOUS",
                    "participant must declare exactly one of gate or gate_neutral=true",
                    participant=item.get("participant"),
                )
            )
        elif has_gate and item["gate"] not in CANONICAL_GATES:
            findings.append(
                _finding(
                    "WORKFLOW_PARTICIPANT_GATE_INVALID",
                    "participant gate is not canonical G0..G6",
                    participant=item.get("participant"),
                    gate=item.get("gate"),
                )
            )
        kind = item.get("participant_kind")
        pid = item.get("participant")
        if kind == "node" and pid not in node_ids:
            findings.append(
                _finding("WORKFLOW_PARTICIPANT_NOT_IN_REGISTRY", "unknown node participant", participant=pid)
            )
        if kind == "scenario" and pid not in scenario_ids:
            findings.append(
                _finding(
                    "WORKFLOW_PARTICIPANT_NOT_IN_REGISTRY", "unknown scenario participant", participant=pid
                )
            )

    # --- gate bindings by policy_ref only ---------------------------------
    bindings = list(workflow.get("gate_bindings", []))
    bound_gates = {item["gate"] for item in bindings}
    if bound_gates != set(CANONICAL_GATES):
        findings.append(
            _finding(
                "WORKFLOW_GATE_BINDING_INCOMPLETE",
                "gate bindings must cover exactly G0..G6",
                gates=sorted(bound_gates),
            )
        )
    for binding in bindings:
        extra = set(binding) - {"gate", "policy_ref"}
        if extra:
            findings.append(
                _finding(
                    "WORKFLOW_INLINE_POLICY_FORBIDDEN",
                    "gate binding may only carry gate and policy_ref",
                    gate=binding.get("gate"),
                    extra=sorted(extra),
                )
            )
        ref = binding.get("policy_ref")
        if not ref:
            findings.append(
                _finding("WORKFLOW_POLICY_REF_MISSING", "gate binding lacks policy_ref", gate=binding.get("gate"))
            )
        elif ref not in policy_ids:
            findings.append(
                _finding(
                    "WORKFLOW_POLICY_REF_UNRESOLVED",
                    "policy_ref does not resolve in the bound policy registry",
                    gate=binding.get("gate"),
                    policy_ref=ref,
                )
            )

    if flow_profile.get("policy_registry_ref") != policy_registry.get("registry_id"):
        findings.append(
            _finding(
                "POLICY_REGISTRY_BINDING_MISMATCH",
                "flow profile is not bound to the supplied policy registry",
                expected=policy_registry.get("registry_id"),
                actual=flow_profile.get("policy_registry_ref"),
            )
        )

    # --- registry revision/digest binding ---------------------------------
    live = {
        "node": node_registry,
        "scenario": scenario_registry,
        "graph": graph_registry,
        "policy": policy_registry,
    }
    ref_field = {
        "node": "node_registry_ref",
        "scenario": "scenario_registry_ref",
        "graph": "graph_registry_ref",
        "policy": "policy_registry_ref",
    }
    declared_bindings = {item["registry"]: item for item in flow_profile.get("registry_bindings", [])}
    for name, payload in live.items():
        binding = declared_bindings.get(name)
        if binding is None:
            findings.append(
                _finding("REGISTRY_BINDING_MISSING", "registry not bound by version/revision/digest", registry=name)
            )
            continue
        if binding["registry_id"] != _registry_ids(payload):
            findings.append(
                _finding(
                    "REGISTRY_BINDING_ID_MISMATCH",
                    "bound registry id differs from live registry",
                    registry=name,
                    expected=_registry_ids(payload),
                    actual=binding["registry_id"],
                )
            )
        if binding["revision"] != _registry_revision(payload):
            findings.append(
                _finding(
                    "REGISTRY_BINDING_STALE",
                    "bound registry revision is stale",
                    registry=name,
                    expected=_registry_revision(payload),
                    actual=binding["revision"],
                )
            )
        if binding["schema_version"] != payload.get("schema_version"):
            findings.append(
                _finding(
                    "REGISTRY_BINDING_SCHEMA_DRIFT",
                    "bound registry schema_version drifted",
                    registry=name,
                    expected=payload.get("schema_version"),
                    actual=binding["schema_version"],
                )
            )
        if binding["registry_id"] != flow_profile.get(ref_field[name]):
            findings.append(
                _finding(
                    "REGISTRY_REF_BINDING_MISMATCH",
                    "top-level registry ref disagrees with registry_bindings",
                    registry=name,
                )
            )
        live_digest = "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if binding["digest"] != live_digest:
            findings.append(
                _finding(
                    "REGISTRY_BINDING_DIGEST_MISMATCH",
                    "bound registry digest does not match live content",
                    registry=name,
                    expected=live_digest,
                    actual=binding["digest"],
                )
            )

    # --- compatibility ----------------------------------------------------
    compatibility = flow_profile.get("compatibility")
    if not isinstance(compatibility, dict):
        findings.append(_finding("COMPATIBILITY_METADATA_MISSING", "v2 profile lacks compatibility metadata"))
    else:
        if compatibility.get("v1_compatible") is True and compatibility.get("migration") != "none":
            findings.append(
                _finding(
                    "COMPATIBILITY_DECLARATION_INCONSISTENT",
                    "v1_compatible=true requires migration=none",
                )
            )
        if compatibility.get("v1_compatible") is False and compatibility.get("migration") != "deterministic_upgrade":
            findings.append(
                _finding(
                    "COMPATIBILITY_MIGRATION_UNDEFINED",
                    "non v1-compatible profile must declare deterministic_upgrade migration",
                )
            )

    # --- compiled digest --------------------------------------------------
    compiled = compile_workflow_projection(flow_profile)
    declared_compiled = flow_profile.get("compiled")
    if isinstance(declared_compiled, dict):
        if declared_compiled.get("workflow_digest") != compiled["workflow_digest"]:
            findings.append(
                _finding(
                    "WORKFLOW_DIGEST_MISMATCH",
                    "declared compiled workflow digest does not match recomputation",
                    expected=compiled["workflow_digest"],
                    actual=declared_compiled.get("workflow_digest"),
                )
            )
        if declared_compiled.get("projection_version") != PROJECTION_VERSION:
            findings.append(
                _finding(
                    "WORKFLOW_PROJECTION_VERSION_DRIFT",
                    "compiled projection_version drifted",
                    expected=PROJECTION_VERSION,
                    actual=declared_compiled.get("projection_version"),
                )
            )

    outcome = "PASS" if not findings else "BLOCKED"
    reason_code = "WORKFLOW_CONTRACT_VALID" if outcome == "PASS" else findings[0]["code"]
    return {
        "outcome": outcome,
        "reason_code": reason_code,
        "flow_id": flow_profile.get("id"),
        "version": version,
        "findings": findings,
        "compiled": compiled,
    }


def validate_profile_registry(
    profile_registry: dict[str, Any], *, root: Path | None = None, **registries: Any
) -> dict[str, Any]:
    """Validate every profile in a profile registry."""
    results = [
        validate_flow_profile_workflow(profile, root=root, **registries)
        for profile in profile_registry.get("profiles", [])
    ]
    outcome = "PASS" if all(item["outcome"] == "PASS" for item in results) else "BLOCKED"
    return {"outcome": outcome, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Flow Profile v2 workflow contract")
    parser.add_argument(
        "--profile-registry",
        default="core/node-architect/profile-registry.json",
        help="path to the profile registry",
    )
    parser.add_argument("--root", default=None, help="repository root")
    parser.add_argument("--emit-digest", action="store_true", help="print compiled workflow digests only")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else Path(__file__).resolve().parents[2]
    registry_path = Path(args.profile_registry)
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - CLI guard
        raise FlowContractError(f"cannot read {registry_path}: {exc}") from exc

    result = validate_profile_registry(payload, root=root)
    if args.emit_digest:
        for item in result["results"]:
            compiled = item.get("compiled") or {}
            print(f"{item['flow_id']}\t{compiled.get('workflow_digest')}")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["outcome"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
