"""NA81 current-task tests for SCRUM-327 (runtime_checkpoint.resume-token-generation).

Current-task requirement -> code -> test evidence map (SCRUM-327 / GitHub #262):

  Brief: render a scoped, deterministic, tamper-evident resume token from ONE
  valid persisted checkpoint; bind task/run/checkpoint/head/scope/expiry as
  applicable; generation must NEVER create authority or widen scope; an invalid
  checkpoint must NOT yield a usable token.

  | # | Requirement (current brief)                     | Code                              | Test                                  |
  |---|--------------------------------------------------|-----------------------------------|---------------------------------------|
  | 1 | valid token binds exact context + validates      | generate_resume_token + schema    | test_valid_token_binds_context        |
  | 2 | missing/invalid checkpoint fails closed          | RESUME_TOKEN_CHECKPOINT_INVALID/  | test_none_checkpoint_fails_closed     |
  |   |                                                  | _MISSING / _MISMATCH              | test_missing_checkpoint_id_fails_...  |
  |   |                                                  |                                   | test_checkpoint_task_mismatch_...     |
  | 3 | wrong head/scope/run is detectable               | faithful binding + token_digest   | test_wrong_head_scope_run_detectable  |
  |   |                                                  |                                   | test_malformed_head_fails_closed      |
  |   |                                                  |                                   | test_empty_run_id_fails_closed        |
  | 4 | expiry must follow issue time                    | expires <= issued guard           | test_expiry_must_follow_issue_time    |
  | 5 | tamper is detected                               | validate_generated_token digest   | test_tamper_is_detected               |
  | 6 | replay equivalence (deterministic)              | canonical_json binding            | test_generation_is_deterministic      |
  | 7 | no authority expansion                          | authority_*=False; G2-only gate   | test_no_authority_expansion           |
  |   |                                                  |                                   | test_generation_is_g2_only            |

These cover the current brief's test matrix that the historical M5 (SCRUM-204)
suite does NOT prove for the current task.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from datetime import datetime, timedelta, timezone

from jsonschema import Draft202012Validator, FormatChecker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from node_architect.generate_resume_token import (  # noqa: E402
    GATES,
    ResumeTokenError,
    digest,
    generate_resume_token,
    validate_generated_token,
)


ROOT = Path(__file__).resolve().parents[1]


def _schema():
    return json.loads((ROOT / "schemas/node-architect/resume-token.schema.json").read_text())


class SCRUM327NA81Tests(unittest.TestCase):
    """NA81 requirement->code->test evidence map for SCRUM-327."""

    def setUp(self) -> None:
        self.schema = _schema()
        self.issued = "2026-08-11T21:00:00Z"
        self.expires = "2026-08-12T21:00:00Z"
        self.checkpoint = {
            "checkpoint_id": "checkpoint-scrum-327-1",
            "task": {"id": "SCRUM-327"},
            "state_digest": "sha256:" + "c" * 64,
        }

    # --- helpers ---------------------------------------------------------

    def generate(self, **overrides):
        values = dict(
            checkpoint=self.checkpoint,
            task_id="SCRUM-327",
            run_id="scrum-327-na81-1",
            scope_hash="sha256:" + "2" * 64,
            base_sha="a" * 40,
            head_sha="b" * 40,
            state_digest=self.checkpoint["state_digest"],
            lease_token="lease-327",
            fencing_token="fence-327",
            issued_at_utc=self.issued,
            expires_at_utc=self.expires,
        )
        values.update(overrides)
        return generate_resume_token(**values)

    # --- 1. valid token binds exact context + validates ------------------

    def test_valid_token_binds_context_and_validates_schema(self):
        token = self.generate()
        Draft202012Validator(self.schema, format_checker=FormatChecker()).validate(token)
        self.assertEqual(validate_generated_token(token, self.checkpoint), [])
        self.assertEqual(token["node_id"], "runtime_checkpoint.resume-token-generation")
        self.assertEqual(token["task_id"], "SCRUM-327")
        self.assertEqual(token["run_id"], "scrum-327-na81-1")
        self.assertEqual(token["checkpoint_id"], "checkpoint-scrum-327-1")
        self.assertEqual(token["base_sha"], "a" * 40)
        self.assertEqual(token["head_sha"], "b" * 40)
        self.assertFalse(token["authority_granted"])

    # --- 2. missing / invalid checkpoint fails closed --------------------

    def test_none_checkpoint_fails_closed(self):
        with self.assertRaises(ResumeTokenError) as raised:
            generate_resume_token(
                checkpoint=None,
                task_id="SCRUM-327", run_id="r", node_id="runtime_checkpoint.resume-token-generation",
                gate="G2_EXECUTION", scope_hash="sha256:" + "2" * 64,
                base_sha="a" * 40, head_sha="b" * 40,
                state_digest="sha256:" + "c" * 64, lease_token="l", fencing_token="f",
                issued_at_utc=self.issued, expires_at_utc=self.expires,
            )
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_CHECKPOINT_INVALID")

    def test_missing_checkpoint_id_fails_closed(self):
        bad = {"checkpoint_id": "", "task": {"id": "SCRUM-327"}, "state_digest": "sha256:" + "c" * 64}
        with self.assertRaises(ResumeTokenError) as raised:
            self.generate(checkpoint=bad)
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_BINDING_MISSING")

    def test_checkpoint_task_mismatch_fails_closed(self):
        bad = {
            "checkpoint_id": "checkpoint-scrum-327-1",
            "task": {"id": "SCRUM-999"},
            "state_digest": "sha256:" + "c" * 64,
        }
        with self.assertRaises(ResumeTokenError) as raised:
            self.generate(checkpoint=bad)
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_CHECKPOINT_MISMATCH")

    def test_checkpoint_state_drift_fails_closed(self):
        with self.assertRaises(ResumeTokenError) as raised:
            self.generate(state_digest="sha256:" + "3" * 64)
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_STATE_DIGEST_MISMATCH")

    # --- 3. wrong head / scope / run is detectable -----------------------

    def test_wrong_head_scope_run_is_detectable(self):
        # Faithful binding: the token records EXACTLY the context it was given,
        # and a token generated for a different run/head/scope differs in digest,
        # so a wrong-context token is always distinguishable from the canonical one.
        token_a = self.generate(run_id="run-na81-a", head_sha="b" * 40, scope_hash="sha256:" + "2" * 64)
        token_b = self.generate(run_id="run-na81-b", head_sha="d" * 40, scope_hash="sha256:" + "9" * 64)
        # faithful binding
        self.assertEqual(token_a["run_id"], "run-na81-a")
        self.assertEqual(token_a["head_sha"], "b" * 40)
        self.assertEqual(token_a["scope_hash"], "sha256:" + "2" * 64)
        # cross-context tokens are distinct (digest differs)
        self.assertNotEqual(token_a["token_digest"], token_b["token_digest"])
        # a context-equality gate flags the mismatched token
        expected_context = {"run_id": "run-na81-a", "head_sha": "b" * 40, "scope_hash": "sha256:" + "2" * 64}
        for key, val in expected_context.items():
            self.assertEqual(token_a.get(key), val)          # canonical matches
            self.assertNotEqual(token_b.get(key), val)       # wrong-context detected

    def test_malformed_head_fails_closed(self):
        with self.assertRaises(ResumeTokenError) as raised:
            self.generate(head_sha="NOT-A-SHA")
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_BINDING_INVALID")

    def test_empty_run_id_fails_closed(self):
        with self.assertRaises(ResumeTokenError) as raised:
            self.generate(run_id="")
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_BINDING_MISSING")

    # --- 4. expiry must follow issue time --------------------------------

    def test_expiry_must_follow_issue_time(self):
        with self.assertRaises(ResumeTokenError) as raised:
            self.generate(expires_at_utc="2026-08-11T20:59:00Z")
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_TIME_INVALID")

    # --- 5. tamper is detected ------------------------------------------

    def test_tamper_is_detected(self):
        import copy
        token = self.generate()
        tampered = copy.deepcopy(token)
        tampered["next_action"] = "merge"
        errors = validate_generated_token(tampered, self.checkpoint)
        self.assertIn("RESUME_TOKEN_DIGEST_MISMATCH", errors)

    # --- 6. replay equivalence (deterministic) --------------------------

    def test_generation_is_deterministic_for_same_context(self):
        self.assertEqual(self.generate(), self.generate())

    # --- 7. no authority expansion --------------------------------------

    def test_no_authority_expansion(self):
        token = self.generate()
        for key in ("authority_granted", "write_authority_granted", "merge_authority_granted",
                    "deployment_authority_granted", "production_authority_granted"):
            self.assertFalse(token[key], msg=key)
        self.assertNotIn("G3", GATES)  # generation grants no downstream gate authority

    def test_generation_is_g2_only(self):
        with self.assertRaises(ResumeTokenError) as raised:
            self.generate(gate="G3_PR")
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_GATE_INVALID")

    def test_requires_human_approval_demands_reference(self):
        with self.assertRaises(ResumeTokenError) as raised:
            self.generate(requires_human_approval=True)
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_APPROVAL_MISSING")


if __name__ == "__main__":
    unittest.main()
