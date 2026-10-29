#!/usr/bin/env python3
"""Universal Runtime v2 epoch cut-over — RED/GREEN regression suite.

Proves the UNIVERSAL_V2 control-plane incidents fixed on the Q0 development
lane:

1. Fresh universal-runtime boot never enters legacy G0/G1 as a parent.
2. Missing legacy G0/G1 task artifacts never block the Universal parent.
3. Legacy WAIT/HOLD cannot stop or pause the Universal controller.
4. Legacy NEXT cannot move the Universal cursor.
5. A legacy-policy conflict with Universal v2 is a branch-local defect,
   never a HITL request.
6. A missing Universal component is GWC_RUNTIME_DEFECT, never a legacy
   fallback.
7. A self-remediable defect does not request Human.
8. A missing technical artifact does not request Human.
9. The Controller never dispatches the Executor for read-only confirmation.
10. Repeated WAIT ticks are idempotent (no new Executor traffic).
11. Multiple Q0 defects remain on the same Q0 branch/worktree.
12. A fresh boot from the lane selects Universal v2 development mode
    deterministically.
13. The C91/E52 incident scenario advances beyond the old failure state and
    no longer ends at NEEDS_EXACT_HITL.

Pure / read-only: does not mutate repository, mailbox, or external state.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

MODULE_NAME = "tools.node_architect.universal_run_epoch"

UNIVERSAL_V2 = "UNIVERSAL_V2_DEVELOPMENT"
BRANCH = "fix/SCRUM-781-q0-canonical"


def _mod():
    try:
        import importlib
        return importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as exc:  # pragma: no cover - RED state
        pytest.fail(f"RED contract missing: {MODULE_NAME} ({exc})")
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"RED contract unavailable: {type(exc).__name__}: {exc}")


# --- 1. epoch resolution ---------------------------------------------------

def test_fresh_boot_selects_universal_v2_development():
    m = _mod()
    decision = m.resolve_runtime_epoch(task_id="SCRUM-781", branch=BRANCH)
    assert decision["runtime_epoch"] == UNIVERSAL_V2
    assert decision["normative"] is True
    assert decision["legacy_runtime_entry_forbidden"] is True


def test_universal_epoch_has_no_legacy_fallback_default():
    m = _mod()
    decision = m.resolve_runtime_epoch(task_id="SCRUM-781", branch=BRANCH)
    assert decision["legacy_fallback"] is False
    assert decision["route"] == "UNIVERSAL_V2"


def test_universal_epoch_never_routes_into_legacy_g01():
    m = _mod()
    result = m.route_universal_request(
        runtime_epoch=UNIVERSAL_V2,
        requested_gate="G1",
        requested_action="ALIGNMENT",
    )
    assert result["outcome"] == "LEGACY_ROUTE_FORBIDDEN"


def test_universal_epoch_allows_namespaced_universal_gate():
    m = _mod()
    result = m.route_universal_request(
        runtime_epoch=UNIVERSAL_V2,
        requested_gate="UR.G1",
        requested_action="PLAN",
    )
    assert result["outcome"] == "UNIVERSAL_ROUTE_ALLOWED"


# --- 2. legacy G0/G1 irrelevance -------------------------------------------

def test_missing_legacy_g01_artifacts_do_not_block_universal():
    m = _mod()
    finding = m.classify_legacy_g01_absence(
        runtime_epoch=UNIVERSAL_V2,
        legacy_artifacts_present=False,
        universal_native_state_valid=True,
    )
    assert finding["classification"] in ("LEGACY_COMPATIBILITY_FINDING", "LEGACY_COMPATIBILITY_DEFECT")
    assert finding["blocks_universal_parent"] is False


def test_legacy_g01_absence_never_becomes_needs_exact_hitl():
    m = _mod()
    replay = m.replay_c91_incident(
        runtime_epoch=UNIVERSAL_V2,
        legacy_g01_package_present=False,
        universal_native_state_valid=True,
    )
    assert replay["outcome"] == "UNIVERSAL_CONTINUES"
    assert "NEEDS_EXACT_HITL" not in replay["reason_codes"]
    assert replay["advance_beyond_old_failure"] is True


# --- 3/4. WAIT / NEXT isolation --------------------------------------------

def test_legacy_wait_cannot_stop_universal_controller():
    m = _mod()
    verdict = m.control_loop_verdict(runtime_epoch=UNIVERSAL_V2, blocker="WAIT")
    assert verdict["control_loop_continue"] is True
    assert verdict["never_generic_stop"] is True


def test_legacy_next_cannot_advance_universal_cursor():
    m = _mod()
    verdict = m.classify_cursor_update(
        runtime_epoch=UNIVERSAL_V2,
        cursor_source="LEGACY_NEXT",
        proposed_gate="G2",
    )
    assert verdict["cursor_moved"] is False
    assert verdict["reason_code"] == "LEGACY_NEXT_CANNOT_ADVANCE_UNIVERSAL_CURSOR"


def test_effect_hold_does_not_stop_control_loop():
    m = _mod()
    state = m.effect_hold_does_not_stop_control_loop(
        effect_hold=True, control_loop_continue=True,
    )
    assert state["invariant"] is True
    assert state["effect_hold"] is True
    assert state["control_loop_continue"] is True


# --- 5. legacy policy conflict ---------------------------------------------

def test_legacy_policy_conflict_is_branch_local_defect_not_hitl():
    m = _mod()
    verdict = m.classify_blocker(kind="LEGACY_POLICY_CONFLICT")
    assert verdict["class"] == "LEGACY_POLICY_CONFLICT"
    assert verdict["action"] == "FIX_BRANCH_LOCAL_POLICY_ENTRY_POINT"
    assert verdict["requires_human"] is False


# --- 6. missing universal component ----------------------------------------

def test_missing_universal_component_is_runtime_defect_not_legacy_fallback():
    m = _mod()
    verdict = m.classify_blocker(kind="MISSING_RUNTIME_COMPONENT")
    assert verdict["class"] == "MISSING_RUNTIME_COMPONENT"
    assert verdict["action"] == "GWC_RUNTIME_DEFECT_SELF_REPAIR"
    assert verdict["legacy_fallback"] is False
    assert verdict["requires_human"] is False


# --- 7/8. no HITL for self-remediable / technical gap -----------------------

def test_self_remediable_defect_does_not_request_human():
    m = _mod()
    verdict = m.classify_blocker(kind="SELF_REMEDIABLE")
    assert verdict["requires_human"] is False
    assert verdict["action"] == "CONTINUE_AUTONOMOUS"


def test_missing_technical_artifact_is_controller_owned_no_human():
    m = _mod()
    verdict = m.classify_blocker(kind="MISSING_TECHNICAL_ARTIFACT")
    assert verdict["requires_human"] is False
    assert verdict["action"] == "SELF_REMEDIATE"
    assert verdict["owner"] == "CONTROLLER"


def test_validation_failure_retries_without_human():
    m = _mod()
    verdict = m.classify_blocker(kind="VALIDATION_FAILURE")
    assert verdict["requires_human"] is False
    assert verdict["action"] in ("DIAGNOSE_FIX_RERUN", "CONTINUE_AUTONOMOUS")


def test_human_only_at_true_authority_boundary():
    m = _mod()
    for hard in ("HARD_AUTHORITY_BOUNDARY", "TRUE_HUMAN_DECISION"):
        verdict = m.classify_blocker(kind=hard)
        assert verdict["requires_human"] is True
        assert verdict["action"] in ("HOLD_EFFECT_ONLY", "REQUEST_HUMAN")


# --- 9. Executor read-only ping-pong ---------------------------------------

def test_controller_never_dispatches_executor_readonly_confirmation():
    m = _mod()
    verdict = m.guard_executor_readonly_confirm(
        runtime_epoch=UNIVERSAL_V2,
        next_action="readonly_confirmation",
        work_is_effect=False,
    )
    assert verdict["permitted"] is False
    assert verdict["reason_code"] == "CONTROLLER_READONLY_PINGPONG_FORBIDDEN"


def test_controller_may_dispatch_executor_for_effect_work():
    m = _mod()
    verdict = m.guard_executor_readonly_confirm(
        runtime_epoch=UNIVERSAL_V2,
        next_action="authorized_fix",
        work_is_effect=True,
    )
    assert verdict["permitted"] is True


# --- 10. WAIT idempotency ---------------------------------------------------

def test_wait_tick_is_idempotent():
    m = _mod()
    first = m.classify_wait_tick(runtime_epoch=UNIVERSAL_V2, fingerprint="abc", controller_next="X")
    second = m.classify_wait_tick(runtime_epoch=UNIVERSAL_V2, fingerprint="abc", controller_next="X")
    assert first["idempotent"] is True
    assert second["fingerprint"] == first["fingerprint"]
    assert second["generated_executor_traffic"] is False


# --- 11. single Q0 lineage --------------------------------------------------

def test_multiple_q0_defects_use_same_branch_and_worktree():
    m = _mod()
    base = m.assess_q0_lineage(run_id="scrum781-q0-20260920T074727Z")
    defect1 = m.assess_q0_lineage(run_id="scrum781-q0-20260920T074727Z",
                                  defect="Q0-01-red")
    defect2 = m.assess_q0_lineage(run_id="scrum781-q0-20260920T074727Z",
                                  defect="Q0-02-green")
    assert defect1["branch"] == base["branch"] == BRANCH
    assert defect2["worktree"] == defect1["worktree"] == base["worktree"]
    assert base["single_lineage"] is True


def test_defect_corrections_are_additive_commits():
    m = _mod()
    verdict = m.assert_additive_commit(evidence_sha="a" * 40, new_sha="b" * 40)
    assert verdict["additive"] is True
    assert verdict["correction_commit_allowed"] is True


# --- 12/13. branch-level AGENTS bootstrap + replay --------------------------

def test_fresh_boot_override_errors_on_unknown_epoch():
    m = _mod()
    with pytest.raises(ValueError):
        m.resolve_runtime_epoch(task_id="UNKNOWN", branch="auto/OTHER")


def test_c91_e52_scenario_advances_beyond_old_failure():
    m = _mod()
    replay = m.replay_c91_incident(
        runtime_epoch=UNIVERSAL_V2,
        legacy_g01_package_present=False,
        universal_native_state_valid=True,
    )
    assert replay["outcome"] == "UNIVERSAL_CONTINUES"
    assert replay["first_state_beyond_failure"] is not None
    assert replay["reason_codes"] == ["UNIVERSAL_V2_NORMATIVE", "LEGACY_G01_COMPATIBILITY_FINDING"]
    assert replay["controller_next"] not in (None, "")


# --- wire-in: gate-node route guard (legacy gate forbidden under V2) --------

def test_gate_route_guard_blocks_legacy_gate_under_universal_v2():
    from tools.node_architect.resolve_gate_node_route import resolve_gate_node_route

    result = resolve_gate_node_route(
        profile={"profile_id": "gwc", "revision": "r", "bound_graph_revision": "g",
                 "bound_node_registry_revision": "n", "routes": []},
        node_registry={"revision": {"revision_id": "n"}, "nodes": []},
        graph_registry={"revision": {"revision_id": "g"}},
        context={
            "task_id": "SCRUM-781", "gate": "G1", "requested_action": "ALIGNMENT",
            "workflow_mode": "normal", "runtime_epoch": UNIVERSAL_V2,
            "repository": "nhatnguyenquang1838-coder/gwc", "base_sha": "a" * 40,
            "working_branch": BRANCH, "scope_hash": "b" * 40,
        },
        root=Path(__file__).resolve().parents[1],
    )
    assert result["outcome"] == "BLOCKED"
    assert "UNIVERSAL_V2_LEGACY_ROUTE_FORBIDDEN" in result["reason_codes"]


def test_gate_route_guard_does_not_block_non_universal_epoch():
    from tools.node_architect.resolve_gate_node_route import resolve_gate_node_route

    # Without the UNIVERSAL_V2 epoch, the router keeps its pre-existing
    # behavior (missing route -> NODE_ROUTE_MISSING), not the V2 guard.
    result = resolve_gate_node_route(
        profile={"profile_id": "gwc", "revision": "r", "bound_graph_revision": "g",
                 "bound_node_registry_revision": "n", "routes": []},
        node_registry={"revision": {"revision_id": "n"}, "nodes": []},
        graph_registry={"revision": {"revision_id": "g"}},
        context={
            "task_id": "SCRUM-781", "gate": "G1", "requested_action": "ALIGNMENT",
            "workflow_mode": "normal", "repository": "nhatnguyenquang1838-coder/gwc",
            "base_sha": "a" * 40, "working_branch": BRANCH, "scope_hash": "b" * 40,
        },
        root=Path(__file__).resolve().parents[1],
    )
    assert result["outcome"] == "BLOCKED"
    assert "UNIVERSAL_V2_LEGACY_ROUTE_FORBIDDEN" not in result["reason_codes"]
    assert "NODE_ROUTE_MISSING" in result["reason_codes"]
