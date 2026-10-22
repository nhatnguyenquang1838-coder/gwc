from __future__ import annotations

import copy

import pytest

from tools.node_architect.derive_task_authority import evaluate_parent_child_authority
from tools.node_architect.universal_run_authority import (
    AuthorityError,
    SelfGrantError,
    StaleAuthorityError,
    derive_child_authority,
    issue_authority,
    resolve_authority,
)

NOW = "2026-10-22T00:00:00Z"
PARENT = {
    "parent_run_id": "root-1",
    "run_id": "root-1",
    "repository": "org/repo",
    "branch": "feature/root",
    "head_sha": "a" * 40,
    "target": "pre-prod",
    "scope": ["tools/node_architect/a.py", "tests/a.py"],
    "risk_ceiling": "MEDIUM",
    "actions": ["G2_EXECUTION", "G3_REVIEW"],
    "actor": "agent-1",
    "issuer": "human-approver",
    "source": "human_approval",
    "revoked": False,
    "expires_at": "2030-01-01T00:00:00Z",
}
CHILD = {
    "child_run_id": "child-1",
    "parent_run_id": "root-1",
    "repository": "org/repo",
    "branch": "feature/root",
    "head_sha": "a" * 40,
    "target": "pre-prod",
    "scope": ["tools/node_architect/a.py"],
    "risk_ceiling": "LOW",
    "action": "G2_EXECUTION",
    "actor": "agent-1",
}


def grant(**overrides):
    claims = {**PARENT, **overrides}
    return issue_authority(
        task_id="task-1", authority_id="parent-auth", grantee="agent-1",
        action="G2_EXECUTION", issued_by="human-approver", issued_at="2026-01-01T00:00:00Z",
        expires_at=claims["expires_at"], claims=claims,
    )


def test_valid_parent_grant_derives_strict_subset_and_is_deterministic():
    parent = grant()
    first = derive_child_authority(parent, CHILD, root="/repo", now=NOW)
    second = derive_child_authority(parent, copy.deepcopy(CHILD), root="/repo", now=NOW)
    assert first == second
    assert first["schema"] == "derived-child-authority/v1"
    assert first["parent_grant_digest"] == parent.receipt_digest
    assert first["scope"] == CHILD["scope"]
    assert first["g4_g5_g6_authority_granted"] is False
    assert resolve_authority(task_id="task-1", action="G2_EXECUTION", receipts=[first], now=NOW)["granted"]


@pytest.mark.parametrize("override,child,code", [
    ({"revoked": True}, CHILD, "AUTHORITY_REVOKED"),
    ({"expires_at": "2020-01-01T00:00:00Z"}, CHILD, "AUTHORITY_STALE"),
    ({"branch": "other"}, CHILD, "AUTHORITY_SCOPE_DRIFT"),
    ({"repository": "other/repo"}, CHILD, "AUTHORITY_SCOPE_DRIFT"),
    ({"actions": ["G3_REVIEW"]}, CHILD, "AUTHORITY_ACTION_FORBIDDEN"),
    ({}, {**CHILD, "risk_ceiling": "HIGH"}, "AUTHORITY_RISK_ESCALATION"),
    ({}, {**CHILD, "scope": ["outside.py"]}, "AUTHORITY_SCOPE_DRIFT"),
])
def test_invalid_parent_or_escalated_child_fails_closed(override, child, code):
    with pytest.raises(AuthorityError) as err:
        derive_child_authority(grant(**override), child, root="/repo", now=NOW)
    assert err.value.code == code


def test_expired_parent_and_untrusted_receipt_reject():
    with pytest.raises(StaleAuthorityError):
        derive_child_authority(grant(expires_at="2020-01-01T00:00:00Z"), CHILD, root="/repo", now=NOW)
    with pytest.raises(AuthorityError):
        derive_child_authority({"artifact_type": "plan", **PARENT}, CHILD, root="/repo", now=NOW)


@pytest.mark.parametrize("change", [
    {"child_run_id": "root-1"},
    {"parent_run_id": "sibling-1"},
    {"actor": "other-agent"},
    {"head_sha": "b" * 40},
    {"target": "main"},
    {"risk_ceiling": "HIGH"},
])
def test_cross_lineage_actor_target_head_and_risk_escalation_reject(change):
    with pytest.raises(AuthorityError):
        derive_child_authority(grant(), {**CHILD, **change}, root="/repo", now=NOW)


def test_self_grant_sibling_descendant_and_untrusted_provenance_reject():
    for source in ("self_authored_file", "plan", "policy", "github_comment", "sibling", "descendant", "test_fixture", "untrusted_registry"):
        with pytest.raises((AuthorityError, SelfGrantError)):
            derive_child_authority(grant(source=source), CHILD, root="/repo", now=NOW)
    with pytest.raises(SelfGrantError):
        derive_child_authority(grant(issuer="child-1"), CHILD, root="/repo", now=NOW)


def test_replay_is_idempotent_but_conflicting_child_grant_is_denied():
    parent = grant()
    first = derive_child_authority(parent, CHILD, root="/repo", now=NOW)
    replay = derive_child_authority(parent, CHILD, root="/repo", now=NOW)
    assert first == replay
    conflicting = derive_child_authority(parent, {**CHILD, "scope": ["tests/a.py"]}, root="/repo", now=NOW)
    result = resolve_authority(task_id="task-1", action="G2_EXECUTION", receipts=[first, conflicting], now=NOW)
    assert result["decision"] == "DENIED"


def test_code_authority_never_grants_merge_deploy_or_production():
    derived = derive_child_authority(grant(), CHILD, root="/repo", now=NOW)
    for action in ("G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"):
        assert not resolve_authority(task_id="task-1", action=action, receipts=[derived], now=NOW)["granted"]
    assert derived["g4_g5_g6_authority_granted"] is False


def test_negative_decision_digest_is_deterministic():
    invalid_child = {**CHILD, "repository": "outside/repo"}
    first = evaluate_parent_child_authority(PARENT, invalid_child)
    second = evaluate_parent_child_authority(copy.deepcopy(PARENT), copy.deepcopy(invalid_child))
    assert first == second
    assert first["decision"] == "DENY"
    assert first["decision_digest"].startswith("sha256:")


def test_receipt_digests_are_canonical_and_bind_exact_decisions():
    parent = grant()
    result = derive_child_authority(parent, CHILD, root="/repo", now=NOW)
    assert result["decision_digest"].startswith("sha256:")
    assert result["receipt_digest"].startswith("sha256:")
    assert result["decision_digest"] == derive_child_authority(parent, copy.deepcopy(CHILD), root="/repo", now=NOW)["decision_digest"]
