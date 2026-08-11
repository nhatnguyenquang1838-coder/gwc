"""NA81 current-task tests for SCRUM-328 (runtime_checkpoint.resume-token-validation).

Current-task requirement -> code -> test evidence map:

  Brief: validate a resume token against its integrity, expiry, checkpoint,
  task/run, exact head and scope bindings before continuation.  Stale, tampered,
  replay-conflicting or mismatched tokens must be rejected deterministically;
  token validity cannot create new authority.

  | # | Requirement (current brief)                     | Code (delta)                                         | Test (na81)                                          |
  |---|--------------------------------------------------|------------------------------------------------------|------------------------------------------------------|
  | 1 | valid token + run + integrity pass               | token_digest check + run binding + scope_hash prefix | test_valid_token_with_run_and_integrity_passes       |
  | 2 | tampered token_digest rejected                   | 14b token_digest mismatch -> TOKEN_TAMPERED          | test_tampered_token_digest_mismatch                   |
  | 3 | wrong run_id rejected                            | 5b run_id mismatch -> RUN_MISMATCH                   | test_run_id_mismatch_rejected                        |
  | 4 | scope_hash prefix mismatch rejected              | 8b scope_hash prefix check -> SCOPE_HASH_MISMATCH    | test_scope_hash_prefix_mismatch_rejected             |
  | 5 | replay conflict rejected                         | used_token_ids -> REPLAY_REUSE_OUTSIDE_POLICY         | test_replay_conflict_current_task_rejected           |
  | 6 | authority escalation in token body rejected       | 14c authority field scan -> AUTHORITY_ESCALATION      | test_authority_escalation_rejected                   |
  | 7 | authority never granted in RouteDecision         | RouteDecision.authority_granted=False hard-coded      | test_no_authority_expansion_in_route_decision        |
  | 8 | backward compat: legacy token (no run_id/digest)  | all new checks are conditional on presence           | test_legacy_token_without_run_id_still_resumes       |

These cover the current brief's test matrix that the historical M5 suite does NOT
prove for SCRUM-328.
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from node_architect.resume_token_validation import (  # noqa: E402
    AUTHORITY_ESCALATION,
    CurrentContext,
    Route,
    SCOPE_HASH_MISMATCH,
    RUN_MISMATCH,
    validate_resume_token,
)
from node_architect.generate_resume_token import digest, generate_resume_token  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "520aa1968a0809001e8994192278e52a59c86c61"
HEAD_SHA = "90f0533dc63a60816c295f06fff5aa94b5cf7525"
TASK_ID = "SCRUM-328"
REPO = "nhatnguyenquang1838-coder/gwc"


def _future_utc(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _past_utc(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _valid_checkpoint() -> dict:
    return {
        "schema_version": "0.1",
        "checkpoint_id": "cp-scrum-328-1",
        "task": {"id": TASK_ID, "title": "resume-token-validation", "risk_class": "R2"},
        "repository": {
            "full_name": REPO,
            "base_branch": "pre-prod",
            "base_sha": BASE_SHA,
            "working_branch": "auto/SCRUM-328-na81-20260810",
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
            "branch": "auto/SCRUM-328-na81-20260810",
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


def _make_valid_token_with_digest(run_id: str = "scrum-328-na81-1") -> dict:
    token = generate_resume_token(
        checkpoint=_valid_checkpoint(),
        task_id=TASK_ID,
        run_id=run_id,
        scope_hash="sha256:" + "a" * 64,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        state_digest="sha256:" + "b" * 64,
        lease_token="lease-328",
        fencing_token="fence-328",
        issued_at_utc=_past_utc(1),
        expires_at_utc=_future_utc(24),
    )
    return token


def _valid_ctx(**overrides) -> CurrentContext:
    defaults = dict(
        task_id=TASK_ID,
        repository_full_name=REPO,
        base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        gate="G2_EXECUTION",
        scope_hash_16="f2064073432936ec",
        run_id="scrum-328-na81-1",
    )
    defaults.update(overrides)
    return CurrentContext(**defaults)


class SCRUM328NA81Tests(unittest.TestCase):
    """NA81 requirement->code->test evidence map for SCRUM-328."""

    def setUp(self) -> None:
        self.cp = _valid_checkpoint()

    # --- 1. valid token + run + integrity passes ---------------------------

    def test_valid_token_with_run_and_integrity_passes(self):
        token = _make_valid_token_with_digest(run_id="scrum-328-na81-1")
        ctx = _valid_ctx(run_id="scrum-328-na81-1", scope_hash_16=token["scope_hash"][:16])
        decision = validate_resume_token(token, self.cp, ctx)
        self.assertEqual(decision.route, Route.RESUME)
        self.assertFalse(decision.authority_granted)

    # --- 2. tampered token_digest rejected ---------------------------------

    def test_tampered_token_digest_mismatch(self):
        token = _make_valid_token_with_digest()
        token["next_action"] = "merge"  # mutate body without updating digest
        ctx = _valid_ctx(scope_hash_16=None)
        decision = validate_resume_token(token, self.cp, ctx)
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, "TOKEN_TAMPERED")
        self.assertIn("token_digest mismatch", decision.evidence.get("detail", ""))

    # --- 3. wrong run_id rejected ------------------------------------------

    def test_run_id_mismatch_rejected(self):
        token = _make_valid_token_with_digest(run_id="scrum-328-na81-A")
        ctx = _valid_ctx(run_id="scrum-328-na81-B")
        decision = validate_resume_token(token, self.cp, ctx)
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, RUN_MISMATCH)
        self.assertEqual(decision.evidence.get("token_run_id"), "scrum-328-na81-A")
        self.assertEqual(decision.evidence.get("context_run_id"), "scrum-328-na81-B")

    # --- 4. scope_hash prefix mismatch rejected ---------------------------

    def test_scope_hash_prefix_mismatch_rejected(self):
        token = _make_valid_token_with_digest()
        token["scope_hash"] = "sha256:" + "b" * 64  # wrong scope
        ctx = _valid_ctx(scope_hash_16="f2064073432936ec")
        decision = validate_resume_token(token, self.cp, ctx)
        self.assertEqual(decision.route, Route.RECONCILE_REQUIRED)
        self.assertEqual(decision.reason, SCOPE_HASH_MISMATCH)
        self.assertEqual(decision.evidence.get("context_scope_hash_16"), "f2064073432936ec")

    # --- 5. replay conflict rejected ---------------------------------------

    def test_replay_conflict_current_task_rejected(self):
        token = _make_valid_token_with_digest()
        ctx = _valid_ctx(scope_hash_16=None)
        decision = validate_resume_token(
            token, self.cp, ctx, used_token_ids={token["resume_token_id"]}
        )
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, "REPLAY_REUSE_OUTSIDE_POLICY")

    # --- 6. authority escalation in token body rejected --------------------

    def test_authority_escalation_rejected(self):
        token = _make_valid_token_with_digest()
        token["authority_granted"] = True  # tampered authority field
        # recompute digest so token integrity check passes and authority check fires
        body = {k: v for k, v in token.items() if k != "token_digest"}
        token["token_digest"] = digest(body)
        ctx = _valid_ctx(scope_hash_16=None)
        decision = validate_resume_token(token, self.cp, ctx)
        self.assertEqual(decision.route, Route.STOP_FAIL_CLOSED)
        self.assertEqual(decision.reason, AUTHORITY_ESCALATION)
        self.assertIn("authority_granted", decision.evidence.get("detail", ""))

    # --- 7. authority never granted in RouteDecision ----------------------

    def test_no_authority_expansion_in_route_decision(self):
        token = _make_valid_token_with_digest()
        ctx = _valid_ctx()
        decision = validate_resume_token(token, self.cp, ctx)
        self.assertFalse(decision.authority_granted)
        d = decision.to_dict()
        for key in (
            "authority_granted",
            "write_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        ):
            self.assertFalse(d.get(key), msg=key)

    # --- 8. backward compat: legacy token without run_id / digest ----------

    def test_legacy_token_without_run_id_still_resumes(self):
        token = {
            "resume_token_id": "rt-SCRUM-328-legacy",
            "checkpoint_id": "cp-scrum-328-1",
            "issued_at_utc": _past_utc(1),
            "expires_at_utc": _future_utc(24),
            "next_gate": "G2_EXECUTION",
            "next_action": "resume_scoped_file_write",
            "requires_human_approval": False,
            "approval_command": None,
            "audit_projection": {"source_of_truth": False, "links": []},
        }
        ctx = CurrentContext(
            task_id=TASK_ID,
            repository_full_name=REPO,
            base_sha=BASE_SHA,
            head_sha=HEAD_SHA,
            gate="G2_EXECUTION",
            scope_hash_16="f2064073432936ec",
        )
        decision = validate_resume_token(token, self.cp, ctx)
        self.assertEqual(decision.route, Route.RESUME)
        self.assertFalse(decision.authority_granted)


if __name__ == "__main__":
    unittest.main()
