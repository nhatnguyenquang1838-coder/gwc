"""Canonical native checkpoint-document recovery.

Regression: the canonical durable checkpoint produced by
``universal_run_persistence.make_checkpoint_document`` (schema
``gwc.universal-run.run-state-checkpoint.v2``) carries the top-level keys
``runtime_plan`` / ``run_state`` / ``node_allocation``. The documented recovery
entry point ``recover_from_native_checkpoint`` only read ``plan`` + ``run_state``,
so the canonical document could not be fed to it — every real checkpoint was
rejected with ``NATIVE_CHECKPOINT_BINDING_INVALID``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.node_architect.q0_native_bootstrap import build_native_q0_bootstrap
from tools.node_architect.universal_run_continuation import recover_from_native_checkpoint
from tools.node_architect.universal_run_persistence import make_checkpoint_document
from tools.node_architect.universal_runtime_profile import load_universal_v2_default_profile

PLAN_REF = "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json"
ROOT = Path(__file__).resolve().parents[1]


def _genesis_binding():
    plan = json.loads((ROOT / PLAN_REF).read_text(encoding="utf-8"))
    dag = {"nodes": [{"id": f"W{i}", "predecessors": [] if i == 1 else [f"W{i - 1}"]} for i in range(1, 7)]}
    return build_native_q0_bootstrap(
        execution_plan=plan, execution_plan_ref=PLAN_REF,
        candidate_sha="03136918bb8104421635123189c689b765b4633a",
        base_sha="f560db71705d89d0ded2a5efbcaeb4c7c4dafab8",
        dag=dag, created_at="2026-10-29T00:00:00Z",
        created_by={"id": "unit", "role": "executor"},
    )


def test_recover_accepts_canonical_checkpoint_document():
    binding = _genesis_binding()
    document = make_checkpoint_document(
        run_state=binding["run_state"],
        runtime_plan=binding["runtime_plan"],
        node_allocation=binding["node_allocation"],
    )

    controller = recover_from_native_checkpoint(
        profile=load_universal_v2_default_profile(),
        checkpoint=document,
        node_allocation=document["node_allocation"],
    )

    assert controller.runtime_plan["digest"] == binding["runtime_plan"]["digest"]
    assert controller.run_state["state_digest"] == binding["run_state"]["state_digest"]
    assert controller.run_state["node_allocation_id"] == binding["run_state"]["node_allocation_id"]
    assignment = controller.assign_current_action()
    assert assignment["actor"] == "EXECUTOR"
    assert assignment["action"] == "q0_understand"
    assert assignment["gate"] == "UR.G0"


def test_recover_still_accepts_legacy_plan_key():
    binding = _genesis_binding()
    controller = recover_from_native_checkpoint(
        profile=load_universal_v2_default_profile(),
        checkpoint={"plan": binding["runtime_plan"], "run_state": binding["run_state"]},
        node_allocation=binding["node_allocation"],
    )
    assert controller.runtime_plan["digest"] == binding["runtime_plan"]["digest"]


def test_recover_rejects_a_non_checkpoint_projection():
    with pytest.raises(ValueError, match="NATIVE_CHECKPOINT_BINDING_INVALID"):
        recover_from_native_checkpoint(
            profile={},
            checkpoint={"mailbox_cursor": {"seq": "C91", "active_gate": "G1"}},
            node_allocation={},
        )


def test_recover_rejects_a_document_without_a_run_state():
    with pytest.raises(ValueError, match="NATIVE_CHECKPOINT_BINDING_INVALID"):
        recover_from_native_checkpoint(profile={}, checkpoint={"runtime_plan": {}}, node_allocation={})
