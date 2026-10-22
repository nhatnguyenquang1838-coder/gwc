from __future__ import annotations

import copy

from tools.node_architect.universal_run_authority import derive_child_authority, issue_authority
from tools.node_architect.authority_boundary_check import route_g2_effect

NOW = "2026-10-22T00:00:00Z"
CHILD = {
    "child_run_id": "child-1", "parent_run_id": "root-1", "repository": "org/repo",
    "branch": "feature/root", "head_sha": "a" * 40, "target": "pre-prod",
    "scope": ["tools/node_architect/a.py"], "risk_ceiling": "MEDIUM",
    "action": "G2_EXECUTION", "actor": "agent-1",
}


def derived_receipt():
    claims = {
        "run_id": "root-1", "repository": "org/repo", "branch": "feature/root",
        "head_sha": "a" * 40, "target": "pre-prod", "scope": ["tools/node_architect/a.py", "tests/a.py"],
        "risk_ceiling": "MEDIUM", "actions": ["G2_EXECUTION"], "actor": "agent-1",
        "issuer": "human-approver", "source": "human_approval", "revoked": False,
        "expires_at": "2030-01-01T00:00:00Z",
    }
    parent = issue_authority(
        task_id="task-1", authority_id="root-auth", grantee="agent-1", action="G2_EXECUTION",
        issued_by="human-approver", issued_at="2026-01-01T00:00:00Z",
        expires_at=claims["expires_at"], claims=claims,
    )
    return derive_child_authority(parent, CHILD, root="/repo", now=NOW)


def route(**changes):
    args = {
        "task_id": "task-1", "run_id": "child-1", "action": "G2_EXECUTION",
        "effect_closure": ["tools/node_architect/a.py"], "risk_class": "R2",
        "repository": "org/repo", "branch": "feature/root", "head_sha": "a" * 40,
        "target": "pre-prod", "receipts": [derived_receipt()], "now": NOW,
        "protected_effect": False,
    }
    args.update(changes)
    return route_g2_effect(**args)


def test_derived_r2_without_independent_parent_anchor_holds_exact_effect():
    result = route()
    assert result["routing_decision"] == "HITL_REQUIRED"
    assert result["effect_decision"] == "EFFECT_HOLD"
    assert "mode" not in result
    assert result["approval_envelope"]["action"] == "G2_EXECUTION"
    assert result["affected_effects"] == ["tools/node_architect/a.py"]
    assert result["control_loop"] == "CONTINUE_INDEPENDENT_EFFECTS"


def test_r2_without_valid_derived_authority_holds_exact_effect():
    for receipts in ([], [dict(derived_receipt(), expires_at="2020-01-01T00:00:00Z")]):
        result = route(receipts=receipts)
        assert result["routing_decision"] == "HITL_REQUIRED"
        assert result["effect_decision"] == "EFFECT_HOLD"
        assert result["approval_envelope"]["action"] == "G2_EXECUTION"
        assert result["affected_effects"] == ["tools/node_architect/a.py"]
        assert result["control_loop"] == "CONTINUE_INDEPENDENT_EFFECTS"


def test_r3_and_unknown_risk_fail_closed_for_effect():
    assert route(risk_class="R3")["routing_decision"] == "HITL_REQUIRED"
    assert route(risk_class="RX")["effect_decision"] == "DENIED"


def test_protected_effect_denied_even_with_code_authority_and_sibling_is_independent():
    assert route(protected_effect=True)["effect_decision"] == "DENIED"
    # Caller cannot downgrade a protected action by supplying protected_effect=False.
    assert route(action="merge_approved_pr")["effect_decision"] == "DENIED"
    assert route(effect_closure=[".gwc/active/selector.json"])["effect_decision"] == "DENIED"
    sibling = route(effect_closure=["tests/a.py"])
    assert sibling["routing_decision"] == "HITL_REQUIRED"
    assert sibling["effect_decision"] == "EFFECT_HOLD"


def test_receipt_scope_binding_and_closure_tampering_reject():
    assert route(head_sha="b" * 40)["effect_decision"] == "EFFECT_HOLD"
    assert route(effect_closure=["tools/node_architect/a.py", "outside.py"])["effect_decision"] == "EFFECT_HOLD"
    receipt = derived_receipt()
    receipt["branch"] = "other"
    assert route(receipts=[receipt])["effect_decision"] == "EFFECT_HOLD"
