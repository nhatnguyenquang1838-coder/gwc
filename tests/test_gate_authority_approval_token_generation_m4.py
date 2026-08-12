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
    REASON_INPUT_INVALID,
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
        gate_short, approval_request_id, scope_hash_short, expires = parts[1], parts[2], parts[3], parts[4]
        self.assertEqual(gate_short, "G2")
        # approval_request_id must be lowercase and schema-valid
        self.assertEqual(approval_request_id, req["approval_request_id"])
        self.assertTrue(approval_request_id.islower())
        # scope_hash_short must be exactly 16 lowercase hex — NOT the 64-hex token
        self.assertEqual(scope_hash_short, req["scope_hash_short"])
        self.assertRegex(scope_hash_short, r"^[0-9a-f]{16}$")
        self.assertNotEqual(scope_hash_short, req["approval_token"])
        # expiry must be second-precision UTC
        self.assertEqual(expires, req["expires_at"])
        self.assertRegex(expires, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        # Full 64-hex token must NOT appear in the command (non-secret integrity evidence only)
        self.assertNotIn(req["approval_token"], req["approval_command"])

    def test_token_is_non_secret_content_hash(self):
        req = generate_approval_request(**_valid_kwargs())
        # 64-hex, derived from content, not a random/bearer secret.
        self.assertRegex(req["approval_token"], r"^[0-9a-f]{64}$")
        self.assertNotIn("secret", req["approval_command"].lower())

    def test_scope_hash_short_exposed_and_bound(self):
        req = generate_approval_request(**_valid_kwargs())
        scope_hash = req["scope_hash"]
        expected_short = scope_hash.replace("sha256:", "")[:16]
        self.assertEqual(req["scope_hash_short"], expected_short)
        # Command binds the 16-hex short, not the full token
        cmd_parts = req["approval_command"].split(" ")
        self.assertEqual(cmd_parts[3], req["scope_hash_short"])
        self.assertNotEqual(req["scope_hash_short"], req["approval_token"])

    def test_approval_request_id_deterministic_and_lowercase(self):
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs())
        self.assertEqual(a["approval_request_id"], b["approval_request_id"])
        # Must be lowercase and schema-valid
        self.assertTrue(a["approval_request_id"].islower())
        self.assertRegex(a["approval_request_id"], r"^[a-z0-9][a-z0-9._-]{2,120}$")
        # Command uses the exact same request ID
        cmd_id = a["approval_command"].split(" ")[2]
        self.assertEqual(cmd_id, a["approval_request_id"])

    def test_equivalent_inputs_render_identical_output(self):
        """Deterministic equivalence / non-duplication: same inputs => identical artifact."""
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs())
        self.assertEqual(a["approval_command"], b["approval_command"])
        self.assertEqual(a["approval_token"], b["approval_token"])
        self.assertEqual(a["request_digest"], b["request_digest"])
        self.assertEqual(a["approval_request_id"], b["approval_request_id"])


class TestDriftRejection(unittest.TestCase):
    def test_scope_hash_change_changes_token(self):
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs(
            scope_identity={**BASE_SCOPE["scope_identity"],
                            "scope_hash": "sha256:" + "a" * 64}))
        self.assertNotEqual(a["approval_token"], b["approval_token"])

    def test_target_drift_invalidates_command(self):
        """Target drift (base_sha/head_sha) must change token AND command.

        base_sha/head_sha are inputs to the canonical binding string that
        derives the token, so target drift propagates through request_id
        into the human approval_command.
        """
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs(
            scope_identity={**BASE_SCOPE["scope_identity"],
                            "head_sha": "0" * 40}))
        # Target/input change => token/digest/request_id/command must all change
        self.assertNotEqual(a["approval_token"], b["approval_token"])
        self.assertNotEqual(a["approval_command"], b["approval_command"])
        self.assertNotEqual(a["approval_request_id"], b["approval_request_id"])

    def test_action_change_changes_token(self):
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs(
            action="merge_auto_merge",
            authority_boundary_decision={"decision": "REQUIRE_APPROVAL",
                                         "requested_action": "merge_auto_merge"}))
        self.assertNotEqual(a["approval_token"], b["approval_token"])

    def test_scope_hash_change_invalidates_command(self):
        """Material drift must change the command, not just the token."""
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs(
            scope_identity={**BASE_SCOPE["scope_identity"],
                            "scope_hash": "sha256:" + "a" * 64}))
        self.assertNotEqual(a["approval_command"], b["approval_command"])
        self.assertNotEqual(a["approval_request_id"], b["approval_request_id"])
        self.assertNotEqual(a["scope_hash_short"], b["scope_hash_short"])

    def test_actor_change_invalidates_command(self):
        """Actor drift must change token, request_id, AND command (Rule 8).

        approval_request_id is derived from the token (which binds actor +
        target + base/head/scope/action/expiry), so actor drift propagates
        into the human command.
        """
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs(
            actor_target={"type": "user", "id": "DIFFERENT_ACTOR",
                          "display_name": "Other"}))
        # Actor is part of canonical binding => token/digest/request_id/command must all change
        self.assertNotEqual(a["approval_token"], b["approval_token"])
        self.assertNotEqual(a["request_digest"], b["request_digest"])
        self.assertNotEqual(a["approval_request_id"], b["approval_request_id"])
        self.assertNotEqual(a["approval_command"], b["approval_command"])

    def test_expiry_change_invalidates_command(self):
        """Expiry drift must change the command."""
        a = generate_approval_request(**_valid_kwargs())
        b = generate_approval_request(**_valid_kwargs(
            expires_at="2026-08-12T13:05:00Z"))
        self.assertNotEqual(a["approval_command"], b["approval_command"])
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

    def test_invalid_task_id_chars_rejected(self):
        """task_id with spaces, !, &, slash must fail-closed (no sanitization)."""
        for bad_task_id in ["SCRUM 308!", "SCRU&M-308", "SCRUM/308", "SCRUM@308"]:
            with self.assertRaises(ApprovalRequestError) as ctx:
                generate_approval_request(**_valid_kwargs(task_id=bad_task_id))
            self.assertIn(REASON_INPUT_INVALID, str(ctx.exception))

    def test_overlength_task_id_rejected(self):
        """task_id > 100 chars must fail-closed, not collide via truncation."""
        long_task_id = "A" * 101
        with self.assertRaises(ApprovalRequestError) as ctx:
            generate_approval_request(**_valid_kwargs(task_id=long_task_id))
        self.assertIn(REASON_INPUT_INVALID, str(ctx.exception))

    def test_valid_task_id_accepted(self):
        """Existing SCRUM-308 / SCRUM-185 format remains valid."""
        for good_task_id in ["SCRUM-308", "SCRUM-185", "SCRUM-185.2", "task_abc-123"]:
            req = generate_approval_request(**_valid_kwargs(task_id=good_task_id))
            self.assertRegex(req["approval_request_id"], r"^[a-z0-9][a-z0-9._-]{2,120}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
