#!/usr/bin/env python3
"""Universal Runtime v2 — transport-decoupled continuation driver.

RED/GREEN regression suite for the continuation repair:

1. INTERNAL CONTROLLER TRANSITION NEEDS NO TRANSPORT
2. EXPECTED_EXECUTOR_SEQ_NULL SEMANTICS (blocks dispatch, not Controller)
3. A2A NOT POLLED IS NOT A RUNTIME BLOCKER
4. CROSS-ACTOR TRANSITION USES TRANSPORT
5. CROSS-ACTOR TRANSPORT FAILURE IS LOCALIZED
6. MAILBOX IS NOT RUN CURSOR (native RunState wins)
7. C91 + E53 REPLAY (receipt consumed once, successor persisted, no Human)
8. HEARTBEAT DERIVES FROM NATIVE STATE
9. GOAL DERIVES FROM NATIVE STATE (stale legacy text invalidated)
10. RESTART RECOVERY (native cursor, no mailbox prose)
11. TRANSPORT SWAP CONFORMANCE (same decision under A2A vs local adapter)
12. SAME FINGERPRINT STALL GUARD (runnable internal work -> liveness defect)

Pure / read-only: the driver is transport-neutral; adapters are injected and
counted, never executed against a real external system.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

MOD = "tools.node_architect.universal_run_continuation"

UNIVERSAL_V2 = "UNIVERSAL_V2_DEVELOPMENT"
RUN_ID = "scrum781-q0-20260920T074727Z"
LEGACY_HITL_UNIVERSAL_CONTINUES = "UNIVERSAL_CONTINUES"
FIRST_STATE = "UR.G1_TYPED_CONTROLLER_NEXT"


def _m():
    try:
        import importlib
        return importlib.import_module(MOD)
    except ModuleNotFoundError as exc:  # pragma: no cover - RED state
        pytest.fail(f"RED contract missing: {MOD} ({exc})")
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"RED contract unavailable: {type(exc).__name__}: {exc}")


def _plan_and_state(m):
    plan = m.create_or_recover_runtime_plan(
        run_id=RUN_ID, revision=1, target_contract_ref="scrq0-canonical",
        node_allocations=["ur.g0", "ur.g1", "ur.g2"],
    )
    run_state = m.create_initial_run_state(
        run_id=RUN_ID, sequence=1, active_gate="UR.G1",
        execution_refs={}, future_contract_refs={},
    )
    # UR.G1 transition already satisfied by the E53 cut-over receipt
    run_state["gate_evidence"] = {"CUTOVER_RECEIPT": "E53"}
    return plan, run_state


# --- 1. internal transition needs no transport ------------------------------

def test_internal_controller_transition_needs_no_transport():
    m = _m()
    plan, run_state = _plan_and_state(m)
    result = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan,
        run_state=run_state,
        history_controller={"seq": "C91", "status": "NEEDS_EXACT_HITL", "expected_executor_seq": None},
        executor_receipts={"E53": {"kind": "UNIVERSAL_V2_DEVELOPMENT_PROMOTION_RECEIPT"}},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert result["control_loop_continue"] is True
    assert result["next_owner"] == "CONTROLLER"
    assert result["typed_next"]
    assert result["runtime_progressed"] is True
    assert result["a2a_call_count"] == 0
    assert result["needs_human"] is False


# --- 2. expected_executor_seq null only blocks dispatch ---------------------

def test_expected_executor_seq_null_only_blocks_executor_dispatch():
    m = _m()
    e53 = {"E53": {"kind": "UNIVERSAL_V2_DEVELOPMENT_PROMOTION_RECEIPT"}}
    plan, run_state = _plan_and_state(m)
    result = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan,
        run_state=run_state,
        history_controller={"seq": "C91", "status": "NEEDS_EXACT_HITL", "expected_executor_seq": None},
        executor_receipts=e53,
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert result["executor_dispatch"] is False
    assert result["controller_progression"] is True


# --- 3. A2A not polled is not a runtime blocker -----------------------------

def test_a2a_not_polled_is_not_runtime_blocker():
    m = _m()
    plan, run_state = _plan_and_state(m)
    result = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan,
        run_state=run_state,
        history_controller={"seq": "C91", "transport_polled": False},
        executor_receipts={},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        not_polled_by_contract=True,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert result["runtime_progressed"] is True
    assert result["a2a_call_count"] == 0


# --- 4. cross-actor transition uses transport -------------------------------

def test_cross_actor_transition_uses_transport():
    m = _m()
    plan, run_state = _plan_and_state(m)
    calls = {"calls": 0}

    def adapter(message):
        calls["calls"] += 1
        return {"delivered": True, "receipt": "transport-receipt-1", "message": message}

    result = m.execute_cross_actor_transition(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan,
        run_state=run_state,
        owner="EXECUTOR",
        typed_next="APPLY_BOUNDED_FIX",
        transport_adapter=adapter,
        transport_available=True,
    )
    assert result["actor_selected"] == "EXECUTOR"
    assert result["typed_next"] == "APPLY_BOUNDED_FIX"
    assert result["transport_required"] is True
    assert result["delivered"] is True
    assert result["transport_receipt"] == "transport-receipt-1"
    assert calls["calls"] == 1


# --- 5. cross-actor transport failure is localized --------------------------

def test_cross_actor_transport_failure_is_localized():
    m = _m()
    plan, run_state = _plan_and_state(m)
    result = m.execute_cross_actor_transition(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan,
        run_state=run_state,
        owner="EXECUTOR",
        typed_next="APPLY_BOUNDED_FIX",
        transport_adapter=None,
        transport_available=False,
    )
    assert result["transport_unavailable"] is True
    assert result["outcome"] == "TRANSPORT_UNAVAILABLE"
    # internal Controller work remains runnable; runtime stays Universal V2
    assert result["legacy_fallback"] is False
    assert result["runtime_epoch"] == UNIVERSAL_V2


# --- 6. mailbox is not run cursor -------------------------------------------

def test_mailbox_is_not_run_cursor():
    m = _m()
    native = m.create_initial_run_state(
        run_id=RUN_ID, sequence=9, active_gate="UR.G2",
        execution_refs={}, future_contract_refs={},
    )
    proj = m.reconcile_mailbox_projection(
        runtime_epoch=UNIVERSAL_V2,
        native_run_state=native,
        mailbox_cursor={"seq": "C91", "gate": "G1", "status": "NEEDS_EXACT_HITL"},
    )
    assert proj["native_wins"] is True
    assert proj["mailbox_classification"] == "HISTORICAL_LEGACY_PROJECTION"
    assert proj["cursor"]["sequence"] == 9
    assert proj["cursor"]["active_gate"] == "UR.G2"


# --- 7. C91 + E53 replay ----------------------------------------------------

def test_c91_e53_replay_consumes_receipt_and_persists_successor():
    m = _m()
    plan, run_state = _plan_and_state(m)
    result = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan,
        run_state=run_state,
        history_controller={"seq": "C91", "status": "NEEDS_EXACT_HITL",
                            "expected_executor_seq": None, "legacy": True},
        executor_receipts={"E53": {"kind": "UNIVERSAL_V2_DEVELOPMENT_PROMOTION_RECEIPT"}},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert result["c91_classification"] == "HISTORICAL_LEGACY_INCIDENT_EVIDENCE"
    assert result["consumed_receipts"] == ("E53",)
    assert result["needs_human"] is False
    assert result["first_state_beyond_failure"] == FIRST_STATE
    assert result["typed_next"]
    assert result["successor_run_state"] is not None


def test_newer_executor_receipt_consumed_exactly_once():
    m = _m()
    plan, run_state = _plan_and_state(m)
    r1 = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan, run_state=run_state,
        history_controller={"seq": "C91"},
        executor_receipts={"E53": {"kind": "UNIVERSAL_V2_DEVELOPMENT_PROMOTION_RECEIPT"}},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    r2 = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan, run_state=run_state,
        history_controller={"seq": "C91"},
        executor_receipts={"E53": {"kind": "UNIVERSAL_V2_DEVELOPMENT_PROMOTION_RECEIPT"}},
        consumer_cursor={"consumed_receipts": r1["consumed_receipts"]},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert r1["consumed_receipts"] == ("E53",)
    assert r2["consumed_receipts"] == ("E53",)
    assert r2["new_receipts_consumed"] == 0


# --- 8. heartbeat derives from native state ---------------------------------

def test_heartbeat_derives_from_native_state():
    m = _m()
    plan, run_state = _plan_and_state(m)
    result = m.derive_liveness_controls(
        runtime_epoch=UNIVERSAL_V2,
        run_state=run_state,
        internal_controller_work_runnable=True,
        mailbox_expected_executor_seq=None,
        a2a_not_polled=True,
    )
    assert result["heartbeat_state"] == "RUNNABLE"
    assert result["goal_state"] == "ACTIVE"
    assert result["pause_reason"] is None


# --- 9. goal derives from native state --------------------------------------

def test_stale_legacy_goal_is_invalidated_after_v2_cutover():
    m = _m()
    result = m.derive_goal_text(
        runtime_epoch=UNIVERSAL_V2,
        legacy_goal_text="waiting for Nhat's exact G1 package/decision/approval to proceed",
    )
    assert "waiting for Nhat's exact G1 package" not in result
    assert result.strip() != ""


# --- 10. restart recovery ---------------------------------------------------

def test_restart_recovers_universal_cursor_not_c91_hold():
    m = _m()
    plan = m.create_or_recover_runtime_plan(
        run_id=RUN_ID, revision=2, target_contract_ref="scrq0-canonical",
        node_allocations=["ur.g0", "ur.g1", "ur.g2"],
    )
    recovered = m.recover_after_restart(
        runtime_epoch=UNIVERSAL_V2,
        run_id=RUN_ID,
        plan_digest=plan["digest"],
        saved_cursor=8,
        observed_cursor=8,
        mailbox_cursor={"seq": "C91", "status": "NEEDS_EXACT_HITL"},
    )
    assert recovered["cursor"] == 8
    assert recovered["recovered_from_mailbox"] is False
    assert recovered["c91_hold_restored"] is False
    assert recovered["ok"] is True


# --- 11. transport swap conformance -----------------------------------------

def test_transport_swap_conformance():
    m = _m()
    plan, run_state = _plan_and_state(m)

    def a2a_adapter(message):
        return {"delivered": True, "receipt": "a2a-receipt", "message": message}

    def local_adapter(message):
        return {"delivered": True, "receipt": "local-receipt", "message": message}

    r_a2a = m.execute_cross_actor_transition(
        runtime_epoch=UNIVERSAL_V2, plan=plan, run_state=run_state,
        owner="EXECUTOR", typed_next="APPLY_BOUNDED_FIX",
        transport_adapter=a2a_adapter, transport_available=True,
    )
    r_local = m.execute_cross_actor_transition(
        runtime_epoch=UNIVERSAL_V2, plan=plan, run_state=run_state,
        owner="EXECUTOR", typed_next="APPLY_BOUNDED_FIX",
        transport_adapter=local_adapter, transport_available=True,
    )
    assert r_a2a["actor_selected"] == r_local["actor_selected"] == "EXECUTOR"
    assert r_a2a["typed_next"] == r_local["typed_next"] == "APPLY_BOUNDED_FIX"
    assert r_a2a["decision_digest"] == r_local["decision_digest"]


# --- 12. same fingerprint stall guard ---------------------------------------

def test_same_fingerprint_with_runnable_internal_work_cannot_stall_two_ticks():
    m = _m()
    plan, run_state = _plan_and_state(m)

    def tick(fingerprint, runnable):
        return m.detect_stall(
            runtime_epoch=UNIVERSAL_V2,
            fingerprint=fingerprint,
            runnable_internal_work=runnable,
            consecutive_observed=1,
        )

    t1 = tick("fp-1", True)
    # a second tick with the same fingerprint and runnable internal work
    t2 = m.detect_stall(
        runtime_epoch=UNIVERSAL_V2,
        fingerprint="fp-1",
        runnable_internal_work=True,
        consecutive_observed=2,
    )
    assert t1["noop_ok"] is True
    assert t2["noop_ok"] is False
    assert t2["liveness_defect"] is True
    assert t2["advice"] == "RUN_CONTROLLER_RECONCILER"


# --- counter-only advance is fake progress — evidence gating ----------------

def test_no_counter_only_advance_without_gate_evidence():
    m = _m()
    plan, _ = _plan_and_state(m)
    # run_state already at UR.G2 but with NO verification evidence
    rs = m.create_initial_run_state(
        run_id=RUN_ID, sequence=2, active_gate="UR.G2",
        execution_refs={}, future_contract_refs={},
    )
    result = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan, run_state=rs,
        history_controller={"seq": "C91", "status": "NEEDS_EXACT_HITL"},
        executor_receipts={},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert result["runtime_progressed"] is False
    assert result["typed_next"] == "AWAIT_GATE_EVIDENCE"
    assert result["gate_advanced"] is False
    assert result["evidence_gap"] == ["VERIFICATION_RECEIPT"]
    # sequence must NOT move without evidence
    assert result["successor_run_state"]["sequence"] == 2
    assert result["successor_run_state"]["active_gate"] == "UR.G2"


def test_gate_advance_requires_verification_receipt():
    m = _m()
    plan, _ = _plan_and_state(m)
    rs = m.create_initial_run_state(
        run_id=RUN_ID, sequence=2, active_gate="UR.G2",
        execution_refs={}, future_contract_refs={},
    )
    rs["gate_evidence"] = {"VERIFICATION_RECEIPT": "VR-001"}
    result = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan, run_state=rs,
        history_controller={"seq": "C91"},
        executor_receipts={},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert result["runtime_progressed"] is True
    assert result["gate_advanced"] is True
    assert result["successor_run_state"]["sequence"] == 3
    assert result["successor_run_state"]["active_gate"] == "UR.G3"


def test_g3_to_g4_integrate_requires_integration_receipt():
    m = _m()
    plan, _ = _plan_and_state(m)
    rs = m.create_initial_run_state(
        run_id=RUN_ID, sequence=3, active_gate="UR.G3",
        execution_refs={}, future_contract_refs={},
    )
    rs["gate_evidence"] = {}
    result = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan, run_state=rs,
        history_controller={"seq": "C91"},
        executor_receipts={},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert result["typed_next"] == "AWAIT_GATE_EVIDENCE"
    assert "INTEGRATION_RECEIPT" in result["evidence_gap"]


# --- no-readonly pingpong / no analyzer / no human reapproval ----------------

def test_controller_does_not_dispatch_executor_readonly_confirmation():
    m = _m()
    verdict = m.gate_executor_dispatch(
        runtime_epoch=UNIVERSAL_V2,
        typed_next="readonly_confirmation",
        work_is_effect=False,
    )
    assert verdict["permitted"] is False
    assert verdict["reason_code"] == "CONTROLLER_READONLY_PINGPONG_FORBIDDEN"


def test_no_analyzer_required_for_controller_internal_transition():
    m = _m()
    plan, run_state = _plan_and_state(m)
    result = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan, run_state=run_state,
        history_controller={"seq": "C91"},
        executor_receipts={},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert result["analyzer_required"] is False
    assert result["needs_human"] is False


def test_no_human_reapproval_for_existing_universal_v2_mandate():
    m = _m()
    plan, run_state = _plan_and_state(m)
    result = m.reconcile_controller_continuation(
        runtime_epoch=UNIVERSAL_V2,
        plan=plan, run_state=run_state,
        history_controller={"seq": "C91", "status": "NEEDS_EXACT_HITL"},
        executor_receipts={"E53": {"kind": "UNIVERSAL_V2_DEVELOPMENT_PROMOTION_RECEIPT"}},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        actor=f"dwa/default:{RUN_ID}",
    )
    assert result["requires_reapproval"] is False


def test_tick_driver_advances_equivalent_414_415_scenario():
    m = _m()
    plan, run_state = _plan_and_state(m)
    tick1 = m.run_universal_controller_tick(
        plan=plan,
        run_state=run_state,
        history_controller={"seq": "C91", "status": "NEEDS_EXACT_HITL", "expected_executor_seq": None},
        executor_receipts={"E53": {"kind": "UNIVERSAL_V2_DEVELOPMENT_PROMOTION_RECEIPT"}},
        consumer_cursor={"consumed_receipts": ()},
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        not_polled_by_contract=True,
    )
    assert tick1["tick_outcome"] == "CONTROLLER_INTERNAL_ADVANCE"
    assert tick1["a2a_call_count"] == 0
    assert tick1["heartbeat"] == "RUNNABLE"
    assert tick1["goal"] == "ACTIVE"
    assert tick1["first_state_beyond_failure"] == FIRST_STATE

    # second tick, same mailbox fingerprint, receipt already consumed
    tick2 = m.run_universal_controller_tick(
        plan=plan,
        run_state=tick1["successor_run_state"],
        history_controller={"seq": "C91", "status": "NEEDS_EXACT_HITL", "expected_executor_seq": None},
        executor_receipts={"E53": {"kind": "UNIVERSAL_V2_DEVELOPMENT_PROMOTION_RECEIPT"}},
        consumer_cursor=tick1["consumer_cursor"],
        transport_profile="A2A_GPT_EXCHANGE_ONLY",
        transport_available=False,
        not_polled_by_contract=True,
    )
    assert tick2["new_receipts_consumed"] == 0  # consumed exactly once
    assert tick2["a2a_call_count"] == 0
    assert tick2["tick_outcome"] == "CONTROLLER_INTERNAL_ADVANCE"
