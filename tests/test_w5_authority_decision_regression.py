from __future__ import annotations

import pytest

from tools.node_architect import authority_boundary_check
from tools.node_architect.plan_bound_runtime_executor import (
    PlanBoundRuntimeError,
    PlanBoundRuntimeExecutor,
)


def test_require_approval_never_counts_as_revalidated_execution_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    """A preparation/approval decision is not executable authority."""

    def require_approval(**_kwargs):
        return {
            "decision": "REQUIRE_APPROVAL",
            "primary_reason_code": "GATE_HUMAN_APPROVAL_REQUIRED",
        }

    monkeypatch.setattr(
        authority_boundary_check,
        "check_authority_boundary",
        require_approval,
    )

    plan = {
        "runtime_plan_ref": "runtime-plan/SCRUM-674/r1",
        "runtime_plan_digest": "sha256:" + "a" * 64,
        "steps": {
            "STEP-001": {
                "allowed_actions": ["file"],
                "edges": {},
                "node_instruction_ref": "core/node-architect/node-instructions/gate/file.node-instruction.yaml",
            }
        },
    }
    authority = {
        "authority_id": "authority-awaiting-g2",
        "task_id": "SCRUM-674",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": "1" * 40,
        "head_sha": "2" * 40,
        "scope_hash": "sha256:" + "3" * 64,
        "gate": "G1_ALIGNMENT",
        "allowed_actions": ["file"],
        "excluded_actions": [],
        "risk_class": "R2",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "evaluated_at": "2026-09-03T12:00:00+00:00",
    }

    executor = PlanBoundRuntimeExecutor(plan, authority)
    with pytest.raises(PlanBoundRuntimeError, match="authority revalidation failed"):
        executor.execute_step(
            "STEP-001",
            {},
            authority,
            expected_plan_digest=plan["runtime_plan_digest"],
            requested_action="file",
        )
