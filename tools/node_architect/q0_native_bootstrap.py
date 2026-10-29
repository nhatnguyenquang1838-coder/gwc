"""Source-bound, non-authorizing Q0 native genesis for an absent native store.

R3 is an engineering execution contract, not a progressed Universal RunState.
Never infer completed gates from it or migrate an engineering/host checkpoint.
Existing native state must be continued/recovered, never passed to this producer.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Mapping

from .q0_qualification import Q0_RUNTIME_EPOCH, q0_qualification_profile
from .universal_run_controller import UniversalController, _digest
from .universal_run_kernel import UNIVERSAL_PROFILE, initial_run_state
from .universal_run_persistence import _canonical_bytes, _write_immutable, make_checkpoint_document
from .universal_run_topology import create_node_allocation
from .universal_runtime_profile import load_universal_v2_default_profile


def build_native_q0_bootstrap(
    *, execution_plan: Mapping[str, Any], execution_plan_ref: str,
    candidate_sha: str, base_sha: str, dag: Mapping[str, Any],
    created_at: str, created_by: Mapping[str, Any],
) -> dict[str, Any]:
    """Create only unpassed UR.G0 genesis; no recovered cursor or authority."""
    contract = copy.deepcopy(dict(execution_plan))
    if not (
        contract.get("schema_id") == "gwc.scrum781.q0-execution-plan.v3"
        and contract.get("runtime_epoch") == Q0_RUNTIME_EPOCH
        and contract.get("workflow_mode") == "q0_live_qualification"
        and contract.get("contract_mode") == "EXECUTE"
        and str(contract.get("run_id", "")).startswith("scrum781-q0-")
        and str(contract.get("branch", "")).startswith("fix/SCRUM-781-q0-")
        and contract.get("scope", {}).get("max_children") == 0
        and contract.get("integration_ceiling") == "draft_pr_only"
    ):
        raise ValueError("Q0_BOOTSTRAP_CONTRACT_INVALID")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)
               for value in (candidate_sha, base_sha)):
        raise ValueError("Q0_BOOTSTRAP_SOURCE_INVALID")
    if not execution_plan_ref or not created_at or not created_by:
        raise ValueError("Q0_BOOTSTRAP_PROVENANCE_REQUIRED")
    # Reuse native G1 DAG validation; do not claim any planned entry executed.
    from .q0_native_g1_admission import _dag_order
    _dag_order({"dag": dag})
    profile = load_universal_v2_default_profile()
    qualification = q0_qualification_profile()
    run_id = contract["run_id"]
    allocation_id = f"{run_id}:q0.qualification-campaign:native-genesis"
    allocation = create_node_allocation(
        record_id=f"{run_id}:native-genesis-allocation", run_id=run_id,
        node_allocation_id=allocation_id, kind="WORK", requirement="REQUIRED",
        created_at=created_at, created_by=created_by,
        source_refs=["q0.qualification-campaign", execution_plan_ref, candidate_sha],
    )
    plan = {
        "schema_id": "gwc.universal-run.runtime-plan.v2", "schema_version": 2,
        "run_id": run_id, "revision": 1, "previous_digest": None,
        "runtime_epoch": Q0_RUNTIME_EPOCH,
        "runtime_default_profile_digest": profile["profile_digest"],
        "qualification_profile_digest": qualification["profile_digest"],
        "target_contract_ref": execution_plan_ref,
        "node_allocations": [allocation_id], "dag": copy.deepcopy(dict(dag)),
        "source_binding": {"repository": contract["source_repo"], "branch": contract["branch"],
                           "pre_head_sha": candidate_sha, "base_sha": base_sha},
    }
    plan["digest"] = _digest(plan, "digest")
    allocation_ref = f"native-genesis://{run_id}/allocation#record_id={allocation['record_id']}"
    genesis = initial_run_state(UNIVERSAL_PROFILE)
    state = {
        "schema_id": "gwc.universal-run.run-state.v2", "schema_version": 2,
        "run_id": run_id, "sequence": 1,
        "active_gate": next(gate for gate, status in genesis["gate_states"].items() if status == "ACTIVE"),
        "terminal_state": genesis["terminal_state"],
        "runtime_epoch": Q0_RUNTIME_EPOCH, "runtime_plan_digest": plan["digest"],
        "node_allocation_id": allocation_id, "node_allocation_ref": allocation_ref,
        "execution_refs": {"runtime_plan_digest": plan["digest"], "node_allocation_id": allocation_id,
                           "node_allocation_ref": allocation_ref, "candidate_sha": candidate_sha,
                           "base_sha": base_sha, "branch": contract["branch"],
                           "qualification_profile_digest": qualification["profile_digest"]},
        "gate_evidence": {}, "consumed_receipts": [], "next_owner": "EXECUTOR",
        "typed_next": "EXECUTE_Q0_UNDERSTANDING", "evidence_gap": ["UNDERSTANDING_RECEIPT"],
        "authority_granted": False, "executed_effects": [],
        "bootstrap_provenance": {"kind": "ABSENT_NATIVE_STATE_GENESIS",
                                 "execution_plan_ref": execution_plan_ref,
                                 "execution_plan_digest": _digest(contract, "digest"),
                                 "execution_plan_projected_gate": contract.get("current_gate"),
                                 "created_at": created_at, "created_by": dict(created_by)},
    }
    state["state_digest"] = _digest(state, "state_digest")
    binding = {"profile": profile, "runtime_plan": plan, "node_allocation": allocation, "run_state": state}
    UniversalController.from_manifest(profile=profile, manifest=binding)
    return binding


def materialize_native_q0_bootstrap(*, binding: Mapping[str, Any], path: str | Path) -> dict[str, Any]:
    """Install immutable genesis only; an existing different state fails closed."""
    controller = UniversalController.from_manifest(profile=binding["profile"], manifest=binding)
    state = controller.run_state
    if state.get("sequence") != 1 or state.get("active_gate") != "UR.G0" or state.get("consumed_receipts"):
        raise ValueError("Q0_BOOTSTRAP_NOT_GENESIS")
    document = make_checkpoint_document(run_state=state, runtime_plan=controller.runtime_plan,
                                        node_allocation=controller.node_allocation)
    payload = _canonical_bytes(document) + b"\n"
    file_sha, replay = _write_immutable(Path(path), payload, conflict_code="Q0_BOOTSTRAP_EXISTING_NATIVE_STATE")
    return {"path": str(path), "file_sha256": file_sha, "checkpoint_digest": document["checkpoint_digest"],
            "state_digest": state["state_digest"], "sequence": 1, "active_gate": "UR.G0",
            "idempotent_replay": replay, "authority_granted": False, "executed_effects": []}
