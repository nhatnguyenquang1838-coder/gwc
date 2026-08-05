"""M4 tests for deterministic gate approval request generation (SCRUM-185)."""
from __future__ import annotations

import copy
import unittest

from tools.node_architect.approval_token_generation import (
    generate_approval_request,
    ApprovalRequestError,
    REASON_GENERATED,
    REASON_BOUNDARY_NOT_REQUESTED,
    REASON_GATE_ACTION_MISMATCH,
    REASON_BINDING_REQUIRED,
    REASON_EXPIRY_INVALID,
    REASON_G5_MANUAL_SCOPE_REQUIRED,
    REASON_G6_NOT_APPLICABLE,
)

BASE_SCOPE = {
    "task_id": "SCRUM-185",
    "repository": "nhatnguyenquang1838-coder/gwc",
    "gate": "G2_EXECUTION",
    "action": "branch_worktree_file_commit_push",
    "scope_identity": {
        "base_sha": "7269a5219750b7c4fa7c5229eb95df395fd4712d",
        "head_sha": "7269a5219750b7c4fa7c5229eb95df395fd4712d",
        "branch": "hermes/scrum-185-approval-token-20260805",
        "pr_number": None,
        "environment": None,
        "scope_hash": "sha256:9f3c1de6b0aa4d5eb2c78f0a1d64e3b5c8971a2e40db6f8c5a3b1e7d29c04f68",
    },
    "authority_boundary_decision": {
        "decision": "REQUIRE_APPROVAL",
        "requested_action": "branch_worktree_file_commit_push",
        "production_scope_applicable": False,
    },
    "actor_target": {"type": "user", "id": "U0BJRF5L99T", "display_name": "Nhat"},
    "issued_at": "2026-08-05T13:05:00Z",
    "expires_at": "2026-08-06T13:05:00Z",
}


def _valid_kwargs(**overrides):
    kw = copy.deepcopy(BASE_SCOPE)
    kw.update(overrides)
    return kw


class TestDeterministicGeneration(unittest.TestCase):
    def test_generates_when_boundary_requires_approval(self):
        req = generate_approval_request(**_valid_kwargs())
        self.assertEqual(req["artifact_type"], "gate-approval-request")
        self.assertEqual(req["primary_reason_code"], REASON_GENERATED)
        self.assertFalse(req["authority_granted"])
        self.assertFalse(req["consumed"])

    def test_deterministic_same_input_same_token(self):
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs())
        self.assertEqual(a["approval_token"], b["approval_token"])
        self.assertEqual(a["approval_command"], b["approval_command"])
        self.assertEqual(a["request_digest"], b["request_digest"])

    def test_exact_command_grammar(self):
        req = generate_approval_request(**_valid_kwargs())
        parts = req["approval_command"].split(" ")
        self.assertEqual(5, len(parts))
        gate_short, task_id, token, expires = parts[1], parts[2], parts[3], parts[4]
        self.assertEqual(gate_short, "G2")
        self.assertEqual(task_id, "SCRUM-185")
        self.assertEqual(token, req["approval_token"])
        self.assertEqual(expires, req["expires_at"])
        self.assertTrue(all(c in "0123456789abcdef" for c in token))
        self.assertEqual(len(token), 64)

    def test_token_is_non_secret_content_hash(self):
        req = generate_approval_request(**_valid_kwargs())
        # 64-hex, derived from content, not a random/bearer secret.
        self.assertRegex(req["approval_token"], r"^[0-9a-f]{64}$")
        self.assertNotIn("secret", req["approval_command"].lower())


class TestDriftRejection(unittest.TestCase):
    def test_scope_hash_change_changes_token(self):
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs(
            scope_identity={**BASE_SCOPE["scope_identity"],
                            "scope_hash": "sha256:" + "a" * 64}))
        self.assertNotEqual(a["approval_token"], b["approval_token"])

    def test_head_change_changes_token(self):
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs(
            scope_identity={**BASE_SCOPE["scope_identity"],
                            "head_sha": "0" * 40}))
        self.assertNotEqual(a["approval_token"], b["approval_token"])

    def test_action_change_changes_token(self):
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs(
            action="merge_auto_merge",
            authority_boundary_decision={"decision": "REQUIRE_APPROVAL",
                                         "requested_action": "merge_auto_merge"}))
        self.assertNotEqual(a["approval_token"], b["approval_token"])


class TestValidationRules(unittest.TestCase):
    def test_boundary_not_requested_rejected(self):
        with self.assertRaises(ApprovalRequestError) as ctx:
            generate_approval_request(**_valid_kwargs(
                authority_boundary_decision={"decision": "ALLOW_PREPARATION",
                                             "requested_action": "branch_worktree_file_commit_push"}))
        self.assertIn(REASON_BOUNDARY_NOT_REQUESTED, str(ctx.exception))

    def test_gate_action_mismatch_rejected(self):
        with self.assertRaises(ApprovalRequestError) as ctx:
            generate_approval_request(**_valid_kwargs(action="merge_auto_merge"))
        self.assertIn(REASON_GATE_ACTION_MISMATCH, str(ctx.exception))

    def test_missing_binding_rejected(self):
        bad_scope = {k: v for k, v in BASE_SCOPE["scope_identity"].items() if k != "base_sha"}
        with self.assertRaises(ApprovalRequestError) as ctx:
            generate_approval_request(**_valid_kwargs(scope_identity=bad_scope))
        self.assertIn(REASON_BINDING_REQUIRED, str(ctx.exception))

    def test_invalid_ttl_rejected(self):
        with self.assertRaises(ApprovalRequestError) as ctx:
            generate_approval_request(**_valid_kwargs(expires_at="2026-08-05T12:00:00Z"))
        self.assertIn(REASON_EXPIRY_INVALID, str(ctx.exception))

    def test_g4_requires_pr_head_binding(self):
        with self.assertRaises(ApprovalRequestError) as ctx:
            generate_approval_request(**_valid_kwargs(
                gate="G4_MERGE",
                scope_identity={**BASE_SCOPE["scope_identity"], "pr_number": None}))
        self.assertIn(REASON_BINDING_REQUIRED, str(ctx.exception))

    def test_g5_requires_environment(self):
        with self.assertRaises(ApprovalRequestError) as ctx:
            generate_approval_request(**_valid_kwargs(
                gate="G5_DEPLOY",
                scope_identity={**BASE_SCOPE["scope_identity"], "environment": None}))
        self.assertIn(REASON_G5_MANUAL_SCOPE_REQUIRED, str(ctx.exception))

    def test_g6_not_applicable_rejected(self):
        with self.assertRaises(ApprovalRequestError) as ctx:
            generate_approval_request(**_valid_kwargs(
                gate="G6_PRODUCTION_DATA",
                action="production_config_change",
                authority_boundary_decision={"decision": "REQUIRE_APPROVAL",
                                             "requested_action": "production_config_change",
                                             "production_scope_applicable": False}))
        self.assertIn(REASON_G6_NOT_APPLICABLE, str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
