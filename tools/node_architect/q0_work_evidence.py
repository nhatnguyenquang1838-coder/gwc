"""Source-bound derivative CF/work contracts, not gate or qualification receipts.

This producer/consumer separates engineering prerequisite topology from future
certification/Human milestones. It never advances a RunState, stamps matrix PASS,
authenticates evidence, or grants effects. Historical native candidate identity
and current analysis-source identity are deliberately separate hash domains.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from .q0_native_g1_admission import _allocation_digest, _dag_order, _seal
from .universal_run_controller import UniversalController


class Q0WorkEvidenceError(ValueError):
    """Stable derivative binding failure, never a Human approval request."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise Q0WorkEvidenceError(code)


_MAPPING = {
    "CF-PRECHECK": ["NATIVE-PLAN-ACTIVATION", "W1", "W2", "W3"],
    "CF-RED": ["W4"],
    "CF-FIX": ["W4"],
    "CF-LOAD": ["W4", "W5"],
    "CF-REPLAY": ["W4"],
    "CF-CERTIFY": ["W5"],
}
_PREREQUISITES = ["NATIVE-PLAN-ACTIVATION", "W1", "W2", "W3", "W4"]


def _leaves(execution_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    leaves: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(node: Mapping[str, Any]) -> None:
        _require(isinstance(node, Mapping), "CF_PLAN_INVALID")
        name = node.get("id")
        if not isinstance(name, str) or not name or name in seen:
            raise Q0WorkEvidenceError("CF_PLAN_INVALID")
        seen.add(name)
        if node.get("atomic") is True:
            leaves.append(copy.deepcopy(dict(node)))
        for child in node.get("children", []):
            visit(child)

    visit(execution_plan.get("recursive_plan", {}))
    _require({leaf["id"] for leaf in leaves} == set(_MAPPING), "CF_LEAF_COVERAGE_INVALID")
    expected_order = list(_MAPPING)
    for leaf in leaves:
        index = expected_order.index(leaf["id"])
        predecessors = [] if index == 0 else [expected_order[index - 1]]
        _require(leaf.get("depends_on", []) == predecessors, "CF_PREDECESSOR_INVALID")
        requirements = leaf.get("evidence_requirements")
        _require(isinstance(requirements, list) and bool(requirements)
                 and all(isinstance(r, str) and bool(r.strip()) for r in requirements),
                 "CF_ACCEPTANCE_REQUIRED")
    return leaves


def build_cf_work_contract(
    *, native_binding: Mapping[str, Any], execution_plan: Mapping[str, Any],
    work_frontier: Mapping[str, Any], source_head: str, decision_ref: str,
) -> dict[str, Any]:
    """Compile an explicit new derivative without mutating sealed native inputs."""
    _require(isinstance(source_head, str) and re.fullmatch(r"[0-9a-f]{40}", source_head) is not None,
             "ANALYSIS_SOURCE_HEAD_REQUIRED")
    _require(isinstance(decision_ref, str) and bool(decision_ref.strip()), "DECISION_REF_REQUIRED")
    controller = UniversalController.from_manifest(profile=native_binding["profile"], manifest=native_binding)
    plan, state, allocation = controller.runtime_plan, controller.run_state, controller.node_allocation
    _require(execution_plan.get("run_id") == state["run_id"], "CF_RUN_MISMATCH")
    _require(execution_plan.get("branch") == plan["source_binding"]["branch"], "CF_BRANCH_MISMATCH")
    _require(execution_plan.get("runtime_epoch") == "UNIVERSAL_V2_DEVELOPMENT", "CF_EPOCH_MISMATCH")
    _dag_order(plan)
    leaves = _leaves(execution_plan)
    nodes = copy.deepcopy(plan["dag"]["nodes"])
    node_ids = {node["id"] for node in nodes}
    _require(set(_PREREQUISITES) | {"W5", "W6"} == node_ids, "WORK_NODE_COVERAGE_INVALID")
    items = work_frontier.get("items")
    if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
        raise Q0WorkEvidenceError("WORK_OBJECTIVES_INVALID")
    objectives = {}
    for item in items:
        name, objective = item.get("id"), item.get("objective")
        if not isinstance(name, str) or name in objectives or not isinstance(objective, str) or not objective.strip():
            raise Q0WorkEvidenceError("WORK_OBJECTIVES_INVALID")
        _require(item.get("plan_node_id") == name, "WORK_OBJECTIVES_INVALID")
        objectives[name] = objective
    _require(node_ids <= set(objectives), "WORK_OBJECTIVES_MISSING")
    body = {
        "schema_id": "gwc.q0.cf-work-evidence-contract.v1",
        "schema_version": 1,
        "artifact_type": "DERIVATIVE_ENGINEERING_EVIDENCE_CONTRACT",
        "producer": "tools.node_architect.q0_work_evidence:build_cf_work_contract",
        "consumer": "tools.node_architect.q0_work_evidence:validate_cf_work_contract",
        "run_id": state["run_id"],
        "source_bindings": {
            "analysis_source_head": source_head,
            "native_candidate_sha": state["execution_refs"]["candidate_sha"],
            "runtime_plan_digest": plan["digest"],
            "node_allocation_id": allocation["node_allocation_id"],
            "node_allocation_digest": _allocation_digest(allocation),
            "native_state_digest": state["state_digest"],
            "execution_plan_content_digest": _seal(execution_plan),
            "objective_source_content_digest": _seal(work_frontier),
        },
        "decision_ref": decision_ref,
        "work_dag": nodes,
        "objectives": {node_id: objectives[node_id] for node_id in sorted(node_ids)},
        "qualification_prerequisites": list(_PREREQUISITES),
        "milestones": {"W5": "NOT_YET_DUE", "W6": "NOT_YET_DUE"},
        "completion_axes": {
            "engineering_prerequisites_complete": None,
            "qualification_ready": None,
            "certification_complete": None,
            "human_handoff_accepted": None,
        },
        "leaves": [{
            "cf_leaf": leaf["id"],
            "cf_predecessors": leaf.get("depends_on", []),
            "native_work_ids": list(_MAPPING[leaf["id"]]),
            "acceptance_requirements": leaf["evidence_requirements"],
            "completion_status": "EVIDENCE_REQUIRED",
        } for leaf in leaves],
        "qualification_results": {},
        "qualification_accepted": False,
        "authority_granted": False,
        "executed_effects": [],
        "compatibility": "DERIVATIVE_ONLY_NO_NATIVE_PLAN_OR_MATRIX_SEMANTICS_CHANGED",
    }
    return {**body, "contract_digest": _seal(body)}


def validate_cf_work_contract(
    contract: Any, *, native_binding: Mapping[str, Any], execution_plan: Mapping[str, Any],
    work_frontier: Mapping[str, Any], source_head: str, decision_ref: str,
) -> dict[str, Any]:
    """Compare against independent current source inputs, never self-derived expectations.

    This consumes a derivative BINDING only, not CF completion or UR gate evidence.
    Content hashes are integrity checks, not approval or issuer authentication.
    """
    _require(isinstance(contract, Mapping), "CF_CONTRACT_INVALID")
    body = {key: value for key, value in contract.items() if key != "contract_digest"}
    _require(contract.get("contract_digest") == _seal(body), "CF_CONTRACT_SEAL_INVALID")
    expected = build_cf_work_contract(native_binding=native_binding, execution_plan=execution_plan,
                                      work_frontier=work_frontier, source_head=source_head,
                                      decision_ref=decision_ref)
    _require(dict(contract) == expected, "CF_CONTRACT_BINDING_MISMATCH")
    return {"contract_valid": True, "contract_digest": contract["contract_digest"],
            "qualification_accepted": False, "authority_granted": False,
            "consumption_kind": "DERIVATIVE_BINDING_ONLY_NOT_COMPLETION"}
