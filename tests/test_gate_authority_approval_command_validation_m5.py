"""M5 tests for replay-safe approval command validation (SCRUM-186)."""
from __future__ import annotations

import copy
import json
import os
import unittest

from tools.node_architect.approval_token_generation import generate_approval_request
from tools.node_architect.approval_command_validation import (
    validate_approval_command,
    REASON_VALID,
    REASON_INPUT_INVALID,
    REASON_TOKEN_MISMATCH,
    REASON_EXPIRED,
    REASON_HEAD_DRIFT,
    REASON_SCOPE_DRIFT,
    REASON_PR_STATE_INVALID,
    REASON_READBACK_UNAVAILABLE,
    REASON_ALREADY_CONSUMED,
    REASON_REPLAY_CONFLICT,
    REASON_G6_SCOPE_INVALID,
    REASON_ACTOR_MISMATCH,
    REASON_ACTOR_MISSING,
    REASON_TARGET_MISMATCH,
)

REQUEST_KWARGS = dict(
    task_id="SCRUM-186",
    repository="nhatnguyenquang1838-coder/gwc",
    gate="G2_EXECUTION",
    action="branch_worktree_file_commit_push",
    scope_identity={
        "base_sha": "7269a5219750b7c4fa7c5229eb95df395fd4712d",
        "head_sha": "7269a5219750b7c4fa7c5229eb95df395fd4712d",
        "branch": "hermes/scrum-186-approval-validation-20260805",
        "pr_number": None,
        "environment": None,
        "scope_hash": "sha256:c3aeacd2a68f9ad6da45a657cf21f21740262f0a063f654c99cc4fb8babda5b1",
    },
    authority_boundary_decision={"decision": "REQUIRE_APPROVAL",
                                 "requested_action": "branch_worktree_file_commit_push"},
    actor_target={"type": "user", "id": "U0BJRF5L99T"},
    issued_at="2026-08-05T13:10:00Z",
    expires_at="2026-08-06T13:10:00Z",
)

READBACK = dict(
    status="AVAILABLE",
    repository="nhatnguyenquang1838-coder/gwc",
    base_sha="7269a5219750b7c4fa7c5229eb95df395fd4712d",
    head_sha="7269a5219750b7c4fa7c5229eb95df395fd4712d",
    scope_hash="sha256:c3aeacd2a68f9ad6da45a657cf21f21740262f0a063f654c99cc4fb8babda5b1",
    action="branch_worktree_file_commit_push",
    branch=REQUEST_KWARGS["scope_identity"]["branch"],
    pr_number=REQUEST_KWARGS["scope_identity"]["pr_number"],
    current_actor=REQUEST_KWARGS["actor_target"],
    pr=None,
    environment=None,
    production_applicable=False,
    action_class=None,
)


def _request(**over):
    kw = copy.deepcopy(REQUEST_KWARGS)
    kw.update(over)
    return generate_approval_request(**kw)


def _readback(**over):
    rb = copy.deepcopy(READBACK)
    rb.update(over)
    return rb


class TestExactValid(unittest.TestCase):
    def test_exact_valid_response(self):
        req = _request()
        rb = _readback()
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-1")
        self.assertEqual(res["outcome"], "VALID")
        self.assertTrue(res["approval_valid"])
        self.assertEqual(res["replay_status"], "FIRST_SEEN")
        self.assertFalse(res["execution_authority_granted"])

    def test_idempotent_replay_same_event(self):
        req = _request()
        rb = _readback()
        first = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-1")
        second = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-1",
            prior_validation=first)
        self.assertEqual(second["replay_status"], "IDEMPOTENT_REPLAY")
        self.assertTrue(second["approval_valid"])


class TestRejection(unittest.TestCase):
    def test_whitespace_fuzzy_rejected(self):
        req = _request()
        rb = _readback()
        # trailing extra token breaks the exact 4-field grammar
        bad = req["approval_command"] + " EXTRA"
        res = validate_approval_command(
            approval_request=req, human_response=bad,
            current_readback=rb, event_id_or_idempotency_key="evt-2")
        self.assertEqual(res["outcome"], "INVALID")
        self.assertEqual(res["primary_reason_code"], REASON_INPUT_INVALID)

    def test_token_tamper_rejected(self):
        req = _request()
        rb = _readback()
        parts = req["approval_command"].split(" ")
        req_id, scope_short, exp = parts[2], parts[3], parts[4]
        # Tamper the 16-hex scope_hash_short (command binds the short, not the 64-hex token)
        tampered_scope = "f" * 16
        tampered = f"APPROVE G2 {req_id} {tampered_scope} {exp}"
        res = validate_approval_command(
            approval_request=req, human_response=tampered,
            current_readback=rb, event_id_or_idempotency_key="evt-3")
        self.assertEqual(res["outcome"], "INVALID")
        self.assertEqual(res["primary_reason_code"], REASON_TOKEN_MISMATCH)

    def test_expired_rejected(self):
        req = _request(expires_at="2026-08-06T13:10:00Z")
        rb = _readback()
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-4",
            validated_at="2026-08-08T00:00:00Z")
        self.assertEqual(res["primary_reason_code"], REASON_EXPIRED)

    def test_head_drift_rejected(self):
        req = _request()
        rb = _readback(head_sha="0" * 40)
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-5")
        self.assertEqual(res["primary_reason_code"], REASON_HEAD_DRIFT)

    def test_scope_drift_rejected(self):
        req = _request()
        rb = _readback(scope_hash="sha256:" + "b" * 64)
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-6")
        self.assertEqual(res["primary_reason_code"], REASON_SCOPE_DRIFT)

    def test_g4_draft_pr_rejected(self):
        req = _request(gate="G4_MERGE", scope_identity={
            **REQUEST_KWARGS["scope_identity"], "pr_number": 221})
        rb = _readback(pr={"open": True, "draft": True, "state": "open",
                          "head_sha": REQUEST_KWARGS["scope_identity"]["head_sha"]},
                       pr_number=221)
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-7")
        self.assertEqual(res["primary_reason_code"], REASON_PR_STATE_INVALID)

    def test_readback_unavailable_blocked(self):
        req = _request()
        rb = _readback(status="UNAVAILABLE")
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-8")
        self.assertEqual(res["outcome"], "BLOCKED")
        self.assertEqual(res["primary_reason_code"], REASON_READBACK_UNAVAILABLE)

    def test_cross_event_reuse_rejected(self):
        req = _request()
        rb = _readback()
        first = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-9")
        second = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-10",
            prior_validation=first)
        self.assertEqual(second["primary_reason_code"], REASON_ALREADY_CONSUMED)

    def test_g6_scope_invalid_rejected(self):
        req = _request(gate="G6_PRODUCTION_DATA",
                       action="production_config_change",
                       authority_boundary_decision={"decision": "REQUIRE_APPROVAL",
                                                    "requested_action": "production_config_change",
                                                    "production_scope_applicable": True},
                       scope_identity={**REQUEST_KWARGS["scope_identity"],
                                       "environment": "prod"})
        rb = _readback(production_applicable=False, environment="prod",
                       action="production_config_change")
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-11")
        self.assertEqual(res["primary_reason_code"], REASON_G6_SCOPE_INVALID)

    def test_wrong_actor_rejected(self):
        req = _request()
        rb = _readback(current_actor={"type": "user", "id": "U0000000000000"})
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-15")
        self.assertEqual(res["primary_reason_code"], REASON_ACTOR_MISMATCH)

    def test_actor_missing_rejected(self):
        req = _request()
        rb = _readback(current_actor=None)
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-16")
        self.assertEqual(res["primary_reason_code"], REASON_ACTOR_MISMATCH)

    def test_wrong_action_rejected(self):
        req = _request()
        rb = _readback(action="different_action")
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-17")
        self.assertEqual(res["primary_reason_code"], REASON_TARGET_MISMATCH)

    def test_wrong_branch_rejected(self):
        req = _request()
        rb = _readback(branch="refs/heads/wrong-branch")
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-18")
        self.assertEqual(res["primary_reason_code"], REASON_TARGET_MISMATCH)


class TestReadbackUnavailable(unittest.TestCase):
    """Verify that a BLOCKED UNAVAILABLE result is still schema-valid."""

    def test_blocked_result_schema_valid(self):
        jsonschema = _import_jsonschema()
        schema = _load_validation_schema()
        req = _request()
        rb = _readback(status="UNAVAILABLE")
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-schema-blocked")
        jsonschema.validate(res, schema)


class TestSchemaConformance(unittest.TestCase):
    """Every validator result must conform to gate-approval-validation.schema.json."""

    def test_valid_result_conforms(self):
        jsonschema = _import_jsonschema()
        schema = _load_validation_schema()
        req = _request()
        rb = _readback()
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-schema-valid")
        jsonschema.validate(res, schema)

    def test_invalid_result_conforms(self):
        jsonschema = _import_jsonschema()
        schema = _load_validation_schema()
        req = _request()
        rb = _readback(head_sha="0" * 40)
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-schema-invalid")
        jsonschema.validate(res, schema)

    def test_authority_granted_always_false(self):
        req = _request()
        rb = _readback()
        res = validate_approval_command(
            approval_request=req, human_response=req["approval_command"],
            current_readback=rb, event_id_or_idempotency_key="evt-auth-false")
        self.assertFalse(res["execution_authority_granted"])
        self.assertFalse(res["merge_authority_granted"])
        self.assertFalse(res["deployment_authority_granted"])
        self.assertFalse(res["production_authority_granted"])


def _import_jsonschema():
    try:
        import jsonschema
        return jsonschema
    except ImportError:
        raise unittest.SkipTest("jsonschema not available")


def _load_validation_schema():
    here = os.path.dirname(os.path.abspath(__file__))
    schema_path = os.path.normpath(
        os.path.join(here, "..", "schemas", "gate-approval-validation.schema.json"))
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    unittest.main(verbosity=2)
