from __future__ import annotations

import pytest

from tools.node_architect.plan_bound_runtime_executor import (
    PlanBoundRuntimeError,
    PlanBoundRuntimeExecutor,
    RuntimePlanStep,
)


def _plan_step(step_id: str, *, allowed_actions: tuple[str, ...] = (), edges: dict | None = None, node_instruction_ref: str = "") -> RuntimePlanStep:
    return RuntimePlanStep(
        step_id=step_id,
        semantic_action=step_id,
        allowed_actions=allowed_actions,
        edges=edges or {},
        node_instruction_ref=node_instruction_ref,
    )


def _plan(steps: dict[str, RuntimePlanStep], *, digest: str = "sha256:" + "a" * 64) -> dict:
    return {
        "runtime_plan_ref": "plan.test/r1",
        "revision": digest,
        "steps": {sid: s.to_dict() for sid, s in steps.items()},
    }


def test_rejects_missing_runtime_plan_ref():
    executor = PlanBoundRuntimeExecutor(plan={"revision": "sha256:" + "a" * 64, "steps": {}}, authority=None)
    with pytest.raises(PlanBoundRuntimeError, match="runtime_plan_ref"):
        executor.execute_step("inspect", {}, authority=None)


def test_rejects_stale_plan_digest():
    step = _plan_step("inspect", allowed_actions=("read",))
    plan = _plan({"inspect": step})
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=None)
    with pytest.raises(PlanBoundRuntimeError, match="plan digest"):
        executor.execute_step("inspect", {}, authority=None, expected_plan_digest="sha256:" + "b" * 64)


def test_rejects_undeclared_next_action():
    step = _plan_step("inspect", allowed_actions=("read",))
    plan = _plan({"inspect": step})
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=None)
    with pytest.raises(PlanBoundRuntimeError, match="undeclared"):
        executor.execute_step("inspect", {}, authority=None, requested_action="undeclared_action")


def test_rejects_authority_claim_by_executor():
    step = _plan_step("inspect", allowed_actions=("read",))
    plan = _plan({"inspect": step})
    executor = PlanBoundRuntimeExecutor(plan=plan, authority={"authority_granted": True})
    with pytest.raises(PlanBoundRuntimeError, match="authority"):
        executor.execute_step("inspect", {}, authority={"authority_granted": True})


def test_rejects_later_gate_authority_escalation():
    step = _plan_step("inspect", allowed_actions=("read",))
    plan = _plan({"inspect": step})
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=None)
    with pytest.raises(PlanBoundRuntimeError, match="later.gate"):
        executor.execute_step(
            "inspect",
            {},
            authority={"later_gate_authority": True, "gate": "G3_PR"},
        )


def test_rejects_outcome_not_declared_by_plan_edge():
    step = _plan_step(
        "inspect",
        allowed_actions=("read",),
        edges={"PASS": {"target": "validate", "kind": "continue"}},
    )
    plan = _plan({"inspect": step})
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=None)
    with pytest.raises(PlanBoundRuntimeError, match="edge"):
        executor.execute_step("inspect", {}, authority=None, outcome="UNDECLARED_OUTCOME")


def test_rejects_stale_step_id():
    step = _plan_step("inspect", allowed_actions=("read",))
    plan = _plan({"inspect": step})
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=None)
    with pytest.raises(PlanBoundRuntimeError, match="step"):
        executor.execute_step("stale_step", {}, authority=None)


def test_executes_valid_step_with_exact_readback():
    step = _plan_step(
        "inspect",
        allowed_actions=("read", "search"),
        node_instruction_ref="core/node-architect/node-instructions/reference/inspect.node-instruction.yaml",
    )
    plan = _plan({"inspect": step})
    authority = {
        "task_id": "SCRUM-674",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "runtimeplan/w5",
        "head_sha": "0e752b04c9f40a04fe402a4f25fcb12c8b9b4d72",
        "scope_hash": "sha256:" + "c" * 64,
        "gate": "G2_EXECUTION",
        "allowed_actions": ["read", "search"],
        "expires_at": "2026-12-31T00:00:00Z",
        "authority_id": "auth-001",
    }
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=authority)
    result = executor.execute_step("inspect", {"target": "README.md"}, authority=authority)

    assert result["runtime_plan_ref"] == "plan.test/r1"
    assert result["step_id"] == "inspect"
    assert result["node_instruction_ref"] == "core/node-architect/node-instructions/reference/inspect.node-instruction.yaml"
    assert result["authority_revalidated"] is True
    assert "evidence" in result
    assert result["evidence"]["readback_exact"] is not None


def test_rejects_effectful_step_without_authority_revalidation():
    step = _plan_step(
        "validate",
        allowed_actions=("branch", "commit"),
    )
    plan = _plan({"validate": step})
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=None)
    with pytest.raises(PlanBoundRuntimeError, match="authority"):
        executor.execute_step(
            "validate",
            {},
            authority=None,
            requested_action="commit",
        )
