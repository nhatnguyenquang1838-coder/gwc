from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "tools/node_architect/generate_resume_token.py"
    spec = importlib.util.spec_from_file_location("resume_token_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResumeTokenGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = load_module()
        self.schema = json.loads((ROOT / "schemas/node-architect/resume-token.schema.json").read_text())
        self.issued = "2026-08-02T15:30:00Z"
        self.checkpoint = {
            "checkpoint_id": "checkpoint-scrum-204-1",
            "task": {"id": "SCRUM-204"},
            "state_digest": "sha256:" + "1" * 64,
        }

    def generate(self, **overrides):
        values = {
            "checkpoint": self.checkpoint,
            "task_id": "SCRUM-204",
            "run_id": "scrum-204-m5-1",
            "scope_hash": "sha256:" + "2" * 64,
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "state_digest": self.checkpoint["state_digest"],
            "lease_token": "lease-1",
            "fencing_token": "fence-1",
            "issued_at_utc": self.issued,
            "expires_at_utc": "2026-08-03T15:30:00Z",
        }
        values.update(overrides)
        return self.m.generate_resume_token(**values)

    def test_generated_token_binds_context_and_validates_schema(self):
        token = self.generate()
        Draft202012Validator(self.schema, format_checker=FormatChecker()).validate(token)
        self.assertEqual(self.m.validate_generated_token(token, self.checkpoint), [])
        self.assertFalse(token["authority_granted"])
        self.assertEqual(token["node_id"], "runtime_checkpoint.resume-token-generation")

    def test_generation_is_deterministic_for_same_checkpoint_and_context(self):
        self.assertEqual(self.generate(), self.generate())

    def test_missing_state_digest_fails_closed(self):
        with self.assertRaises(self.m.ResumeTokenError) as raised:
            self.generate(state_digest="")
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_BINDING_MISSING")

    def test_checkpoint_state_drift_fails_closed(self):
        with self.assertRaises(self.m.ResumeTokenError) as raised:
            self.generate(state_digest="sha256:" + "3" * 64)
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_STATE_DIGEST_MISMATCH")

    def test_tamper_is_detected(self):
        token = self.generate()
        tampered = copy.deepcopy(token)
        tampered["next_action"] = "merge"
        self.assertIn("RESUME_TOKEN_DIGEST_MISMATCH", self.m.validate_generated_token(tampered, self.checkpoint))

    def test_expiry_must_follow_issue_time(self):
        with self.assertRaises(self.m.ResumeTokenError) as raised:
            self.generate(expires_at_utc="2026-08-02T15:29:00Z")
        self.assertEqual(raised.exception.code, "RESUME_TOKEN_TIME_INVALID")


if __name__ == "__main__":
    unittest.main()
