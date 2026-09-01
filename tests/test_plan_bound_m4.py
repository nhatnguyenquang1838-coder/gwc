"""M4: W5 PlanBoundRuntimeExecutor — real GWC authority validator + digest fix.

Fixes the W1-W7 review BLOCKERs on W5:
- B1: ``expected_plan_digest`` was compared against the plan ``revision``
  field instead of ``runtime_plan_digest`` — the comparison was meaningless.
- B2: ``authority_revalidated=True`` merely on ``authority_id`` presence —
  no canonical GWC authority validator invocation (task/repo/head SHA/
  scope/gate/expiry). The "GWC authority plane preserved" invariant was
  not proven. M4 invokes ``check_authority_boundary`` and only sets
  revalidated when the validator permits the action.
- test SHA: fixture hardcoded ``head_sha=0e752b04`` (gwc main) instead of the
  W5 head — fixture now derives the live repo HEAD.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.node_architect.plan_bound_runtime_executor import (
    PlanBoundRuntimeError,
    PlanBoundRuntimeExecutor,
    RuntimePlanStep,
)


def _repo_head() -> str:
    return (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(Path(__file__).parents[1])
        ).stdout.strip()
        or "0" * 40
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
        "revision": "rev-1",
        "runtime_plan_digest": digest,
        "steps": {sid: s.to_dict() for sid, s in steps.items()},
    }


def _authority(*, allowed_actions: list[str] | None = None, gate: str = "G2_EXECUTION", **overrides) -> dict:
    value = {
        "task_id": "SCRUM-674",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "branch": "wave/planbound-auth/m4",
        "head_sha": _repo_head(),
        "base_sha": "0" * 40,
        "scope_hash": "sha256:" + "a" * 64,
        "gate": gate,
        "allowed_actions": allowed_actions or ["read", "search"],
        "excluded_actions": [],
        "expires_at": "2026-12-31T00:00:00Z",
        "authority_id": "auth-m4-001",
        "risk_class": "R1",
    }
    value.update(overrides)
    return value


def test_digest_compared_against_runtime_plan_digest_not_revision():
    """B1: expected_plan_digest must match runtime_plan_digest — a digest that
    matches the revision string must be REJECTED (comparison was wrong before)."""
    step = _plan_step("inspect", allowed_actions=("read",))
    plan = _plan({"inspect": step}, digest="sha256:" + "a" * 64)
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=None)
    with pytest.raises(PlanBoundRuntimeError, match="plan digest"):
        executor.execute_step(
            "inspect", {}, authority=None,
            expected_plan_digest="rev-1",  # revision string, NOT the digest
        )


def test_matching_runtime_plan_digest_passes():
    step = _plan_step("inspect", allowed_actions=("read",))
    plan = _plan({"inspect": step}, digest="sha256:" + "a" * 64)
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=None)
    result = executor.execute_step(
        "inspect", {}, authority=None, expected_plan_digest="sha256:" + "a" * 64
    )
    assert result["step_id"] == "inspect"


def test_authority_revalidation_invokes_real_validator_allowed():
    """B2: an effectful action with a scope that authorizes it is revalidated
    by the GWC boundary check."""
    step = _plan_step("commit", allowed_actions=("commit",))
    plan = _plan({"commit": step})
    authority = _authority(allowed_actions=["commit"], gate="G3_PR")
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=authority)
    result = executor.execute_step("commit", {}, authority=authority, requested_action="commit")
    assert result["authority_revalidated"] is True


def test_authority_revalidation_rejects_action_not_in_scope():
    """B2: an effectful action NOT authorized by the scope must fail-closed
    (previously authority_id presence alone set revalidated=True)."""
    step = _plan_step("merge", allowed_actions=("merge",))
    plan = _plan({"merge": step})
    authority = _authority(allowed_actions=["read"], gate="G2_EXECUTION")
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=authority)
    with pytest.raises(PlanBoundRuntimeError, match="authority"):
        executor.execute_step("merge", {}, authority=authority, requested_action="merge")


def test_authority_revalidation_rejects_expired_envelope():
    """B2: expired authority envelope fails closed at the GWC boundary."""
    step = _plan_step("commit", allowed_actions=("commit",))
    plan = _plan({"commit": step})
    authority = _authority(
        allowed_actions=["commit"], gate="G3_PR",
        expires_at="2026-01-01T00:00:00Z",  # already expired
    )
    executor = PlanBoundRuntimeExecutor(plan=plan, authority=authority)
    with pytest.raises(PlanBoundRuntimeError, match="authority"):
        executor.execute_step("commit", {}, authority=authority, requested_action="commit")


def test_test_fixture_uses_live_head_sha():
    """test SHA: the fixture must derive the live repo HEAD, never a stale
    hardcoded value (the old W5 test pinned gwc-main 0e752b04)."""
    head = _repo_head()
    live = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(Path(__file__).parents[1])
        ).stdout.strip()
    )
    assert len(head) == 40
    assert head == live
