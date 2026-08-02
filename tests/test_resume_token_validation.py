#!/usr/bin/env python3
"""Tests for runtime_checkpoint.resume-token-validation (M5_REPLAY_SAFE).

Covers: valid resume, expiry, tamper, task/scope mismatch, base/head drift,
missing checkpoint, and stale approval.
"""
import unittest
from datetime import datetime, timedelta, timezone

from tools.node_architect.resume_token_validation import (
    CurrentContext,
    Route,
    validate_resume_token,
)

BASE_SHA = "520aa1968a0809001e8994192278e52a59c86c61"
HEAD_SHA = "90f0533dc63a60816c295f06fff5aa94b5cf7525"
TASK_ID = "SCRUM-205"
REPO = "nhatnguyenquang1838-coder/gwc"


def _future_utc(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _past_utc(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _valid_token() -> dict:
    return {
        "schema_version": "0.1",
        "resume_token_id": "rt-SCRUM-205-001",
        "checkpoint_id": "cp-SCRUM-205-001",
        "issued_at_utc": _past_utc(1),
        "expires_at_utc": _future_utc(24),
        "next_gate": "G2_EXECUTION",
        "next_action": "resume_scoped_file_write",
        "requires_human_approval": False,
        "approval_command": None,
        "audit_projection": {"source_of_truth": False, "links": []},
    }


def _valid_checkpoint() -> dict:
    return {
        "schema_version": "0.1",
        "checkpoint_id": "cp-SCRUM-205-001",
        "task": {"id": TASK_ID, "title": "resume-token-validation", "risk_class": "R2"},
        "repository": {
            "full_name": REPO,
            "base_branch": "main",
            "base_sha": BASE_SHA,
            "working_branch": "chatgpt/scrum-205-resume-token-validation-m5-20260802",
        },
        "gate": {"current": "G2_EXECUTION", "status": "RUNNING", "source": "gwc_gate_evidence"},
        "execution_mode": "local_agent",
        "scope": {
            "files_read": ["core/node-architect/node-catalog/runtime_checkpoint/resume-token-validation.node.json"],
            "files_write": ["tools/node_architect/resume_token_validation.py"],
            "authorized_actions": ["modify_approved_files"],
            "excluded_actions": ["merge"],
        },
        "git_delivery": {
            "branch": "chatgpt/scrum-205-resume-token-validation-m5-20260802",
            "pr_number": None,
            "head_sha": HEAD_SHA,
            "ci_status": "not_started",
        },
        "validation": {"performed": [], "skipped": [], "evidence": []},
        "next_action": {
            "gate": "G2_EXECUTION",
            "action": "resume_scoped_file_write",
            "requires_human_approval": False,
        },
        "audit_projection": {"source_of_truth": False, "links": []},
        "created_at_utc": _past_utc(2),
    }


def _valid_ctx() -> CurrentContext:
    return CurrentContext(
        task_id=TASK_ID,
        repository_full_name=REPO,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        gate="G2_EXECUTION",
        scope_hash_16="f2064073432936ec",
    )


class ResumeTokenValidationTests(unittest.TestCase):
    """Tests for resume-token validation covering all required scenarios."""

    def test_valid_resume(self):
        """A valid token with matching checkpoint and context should route to RESUME."""
        decision = validate_resume_token(_valid_token(), _valid_checkpoint(), _valid_ctx())
        self.assertEqual(decision.route, Route.RESUME)
        self.assertFalse(decision.authority_granted)

    def test_expired_token(self):
        """An expired token should route to STOP_FAIL_CLOSED."""
        token = _valid_token()
        token["expires_at_utc"] = _past_utc(1)
        decision = validate_resume_token(token, _valid_checkpoint(), _valid_ctx())
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, "TOKEN_EXPIRED")

    def test_tampered_token_invalid_expiry(self):
        """A token with invalid expiry format should route to STOP_FAIL_CLOSED."""
        token = _valid_token()
        token["expires_at_utc"] = "not-a-date"
        decision = validate_resume_token(token, _valid_checkpoint(), _valid_ctx())
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, "TOKEN_TAMPERED")

    def test_missing_token(self):
        """An empty/missing token should route to STOP_FAIL_CLOSED."""
        decision = validate_resume_token({}, _valid_checkpoint(), _valid_ctx())
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, "TOKEN_MISSING")

    def test_task_mismatch(self):
        """A checkpoint with a different task ID should route to STOP_FAIL_CLOSED."""
        cp = _valid_checkpoint()
        cp["task"]["id"] = "SCRUM-999"
        decision = validate_resume_token(_valid_token(), cp, _valid_ctx())
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, "TASK_MISMATCH")

    def test_scope_mismatch_empty_files_write(self):
        """A checkpoint with empty files_write should route to RECONCILE_REQUIRED."""
        cp = _valid_checkpoint()
        cp["scope"]["files_write"] = []
        decision = validate_resume_token(_valid_token(), cp, _valid_ctx())
        self.assertEqual(decision.route, Route.RECONCILE_REQUIRED)
        self.assertEqual(decision.reason, "SCOPE_MISMATCH")

    def test_base_drift(self):
        """A checkpoint with a different base SHA should route to REAPPROVAL_REQUIRED."""
        cp = _valid_checkpoint()
        cp["repository"]["base_sha"] = "0" * 40
        decision = validate_resume_token(_valid_token(), cp, _valid_ctx())
        self.assertEqual(decision.route, Route.REAPPROVAL_REQUIRED)
        self.assertEqual(decision.reason, "BASE_DRIFT")

    def test_head_drift(self):
        """A checkpoint with a different head SHA should route to RECONCILE_REQUIRED."""
        cp = _valid_checkpoint()
        cp["git_delivery"]["head_sha"] = "1" * 40
        decision = validate_resume_token(_valid_token(), cp, _valid_ctx())
        self.assertEqual(decision.route, Route.RECONCILE_REQUIRED)
        self.assertEqual(decision.reason, "HEAD_DRIFT")

    def test_missing_checkpoint(self):
        """A missing checkpoint should route to RECONCILE_REQUIRED."""
        decision = validate_resume_token(_valid_token(), None, _valid_ctx())
        self.assertEqual(decision.route, Route.RECONCILE_REQUIRED)
        self.assertEqual(decision.reason, "MISSING_CHECKPOINT")

    def test_stale_approval(self):
        """An expired approval should route to REAPPROVAL_REQUIRED."""
        decision = validate_resume_token(
            _valid_token(),
            _valid_checkpoint(),
            _valid_ctx(),
            approval_expiry_utc=_past_utc(1),
        )
        self.assertEqual(decision.route, Route.REAPPROVAL_REQUIRED)
        self.assertEqual(decision.reason, "APPROVAL_EXPIRED")

    def test_checkpoint_id_mismatch(self):
        """A checkpoint with a different checkpoint_id should route to STOP_FAIL_CLOSED."""
        cp = _valid_checkpoint()
        cp["checkpoint_id"] = "different-cp-id"
        decision = validate_resume_token(_valid_token(), cp, _valid_ctx())
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, "TOKEN_TAMPERED")

    def test_gate_mismatch(self):
        """A checkpoint with a different gate should route to RECONCILE_REQUIRED."""
        cp = _valid_checkpoint()
        cp["gate"]["current"] = "G3_PR"
        decision = validate_resume_token(_valid_token(), cp, _valid_ctx())
        self.assertEqual(decision.route, Route.RECONCILE_REQUIRED)

    def test_replay_reuse_outside_policy(self):
        """A token that was already consumed should route to STOP_FAIL_CLOSED."""
        decision = validate_resume_token(
            _valid_token(),
            _valid_checkpoint(),
            _valid_ctx(),
            used_token_ids={"rt-SCRUM-205-001"},
        )
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, "REPLAY_REUSE_OUTSIDE_POLICY")

    def test_authority_never_granted(self):
        """Token validation must never set authority_granted=True."""
        decision = validate_resume_token(_valid_token(), _valid_checkpoint(), _valid_ctx())
        self.assertFalse(decision.authority_granted)

    def test_route_decision_is_deterministic(self):
        """The same inputs should produce the same route."""
        d1 = validate_resume_token(_valid_token(), _valid_checkpoint(), _valid_ctx())
        d2 = validate_resume_token(_valid_token(), _valid_checkpoint(), _valid_ctx())
        self.assertEqual(d1.route, d2.route)
        self.assertEqual(d1.reason, d2.reason)

    def test_route_decision_to_dict(self):
        """RouteDecision.to_dict should contain all required fields."""
        decision = validate_resume_token(_valid_token(), _valid_checkpoint(), _valid_ctx())
        d = decision.to_dict()
        self.assertIn("route", d)
        self.assertIn("reason", d)
        self.assertIn("token_id", d)
        self.assertIn("checkpoint_id", d)
        self.assertIn("validated_at_utc", d)
        self.assertIn("authority_granted", d)
        self.assertIn("evidence", d)
        self.assertFalse(d["authority_granted"])


if __name__ == "__main__":
    unittest.main()