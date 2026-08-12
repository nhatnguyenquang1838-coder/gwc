from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

# SCRUM-323 fix: absolute tools/ path so `python -m unittest discover -s tests`
# works without PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from jsonschema import Draft202012Validator

from node_architect.cas_write_guard import evaluate_cas_write

# ---------------------------------------------------------------------------
# SCRUM-368 context: failure_recovery.duplicate-agent-fencing
# ---------------------------------------------------------------------------
SCOPE = "sha256:c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8"
BRANCH = "auto/SCRUM-368-na81-20260810"
BASE = "aeb5cc23080c06cfeb633124aa56d0f6e4cccde3"
CHECKPOINT_KEY = "SCRUM-368:g2-scrum-368-r4:failure_recovery.duplicate-agent-fencing"


def observation(**overrides):
    payload = {
        "task_id": "SCRUM-368",
        "observed_task_id": "SCRUM-368",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "observed_repository": "nhatnguyenquang1838-coder/gwc",
        "branch": BRANCH,
        "observed_branch": BRANCH,
        "base_sha": BASE,
        "observed_base_sha": BASE,
        "scope_hash": SCOPE,
        "observed_scope_hash": SCOPE,
        "checkpoint_key": CHECKPOINT_KEY,
        "run_id": "g2-scrum-368-r4",
        "checkpoint_node_id": "failure_recovery.duplicate-agent-fencing",
        "expected_revision": 3,
        "observed_revision": 3,
        "lease_owner": "Hermes",
        "observed_lease_owner": "Hermes",
        "lease_token": "lease-scrum-368",
        "observed_lease_token": "lease-scrum-368",
        "lease_expires_at": "2026-08-12T10:00:00Z",
        "observed_at": "2026-08-12T09:55:00Z",
        "fencing_token": 7,
        "observed_fencing_token": 7,
        "idempotency_key": "scrum-368-effect-001",
        "committed_effects": {},
        "latest_observed_state": {"revision": 3, "status": "ready"},
        "precondition_errors": [],
    }
    payload.update(overrides)
    return payload


class DuplicateAgentFencingNA81Tests(unittest.TestCase):
    """SCRUM-368 NA81 acceptance tests for failure_recovery.duplicate-agent-fencing."""

    def test_two_agent_race_stale_owner_denied(self):
        result = evaluate_cas_write(observation(lease_owner="Hermes", observed_lease_owner="StaleAgent"))
        self.assertEqual(result["outcome"], "LEASE_OWNER_MISMATCH")
        self.assertIn("STALE_OR_DUPLICATE_AGENT", result["reason_codes"])

    def test_stale_fence_denied_even_when_revision_matches(self):
        result = evaluate_cas_write(observation(fencing_token=6))
        self.assertEqual(result["outcome"], "FENCING_MISMATCH")
        self.assertEqual(result["reconciliation_route"], "ABORT_STALE_WORKER")

    def test_valid_current_holder_allows_write(self):
        result = evaluate_cas_write(observation())
        self.assertEqual(result["outcome"], "ALLOW_WRITE")
        self.assertTrue(result["may_write"])
        self.assertEqual(result["next_revision"], 4)
        self.assertFalse(result["auto_retry_allowed"])

    def test_duplicate_passive_replay_returns_committed_effect(self):
        payload = observation(
            lease_expires_at="2026-08-12T10:00:00Z",
            observed_at="2026-08-12T09:55:00Z",
        )
        effect = {
            "binding": {
                "task_id": "SCRUM-368",
                "repository": "nhatnguyenquang1838-coder/gwc",
                "branch": BRANCH,
                "base_sha": BASE,
                "scope_hash": SCOPE,
                "checkpoint_key": CHECKPOINT_KEY,
                "run_id": "g2-scrum-368-r4",
                "checkpoint_node_id": "failure_recovery.duplicate-agent-fencing",
                "lease_owner": "Hermes",
                "lease_token": "lease-scrum-368",
                "fencing_token": 7,
                "lease_expires_at": "2026-08-12T10:00:00Z",
                "idempotency_key": "scrum-368-effect-001",
                "expected_revision": 3,
            },
            "revision": 4,
            "state_digest": "sha256:" + "f" * 64,
            "cas_decision_digest": "sha256:" + "e" * 64,
            "committed_at": "2026-08-12T09:54:00Z",
        }
        payload["committed_effects"] = {payload["idempotency_key"]: effect}
        result = evaluate_cas_write(payload)
        self.assertEqual(result["outcome"], "DUPLICATE_EFFECT_REPLAYED")
        self.assertEqual(result["reconciliation_route"], "RESUME")

    def test_takeover_after_expiry_routes_to_reapproval(self):
        result = evaluate_cas_write(observation(lease_expires_at="2026-08-12T09:50:00Z", observed_at="2026-08-12T09:52:00Z"))
        self.assertEqual(result["outcome"], "LEASE_EXPIRED")
        self.assertEqual(result["reconciliation_route"], "REAPPROVAL_REQUIRED")

    def test_unknown_effect_invalid_input_fails_closed(self):
        result = evaluate_cas_write({"task_id": "SCRUM-368"})
        self.assertEqual(result["outcome"], "INVALID_INPUT")
        self.assertEqual(result["reconciliation_route"], "STOP_BLOCKED")

    def test_split_brain_rejection_via_cas_mismatch(self):
        # Second agent sees the first agent's revision advance → CAS_MISMATCH.
        # latest_observed_state is echoed from the caller's observation, not synthesized.
        result = evaluate_cas_write(observation(expected_revision=3, observed_revision=4))
        self.assertEqual(result["outcome"], "CAS_MISMATCH")
        self.assertEqual(result["reconciliation_route"], "REPAIR")
        self.assertEqual(result["latest_observed_state"], {"revision": 3, "status": "ready"})

    def test_result_schema_accepts_all_outcomes(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "cas-write-guard-result.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        for outcome_args in (
            {},
            {"expected_revision": 1},
            {"fencing_token": 1},
            {
                "expected_revision": 3,
                "observed_revision": 4,
                "lease_expires_at": "2026-08-12T09:50:00Z",
                "observed_at": "2026-08-12T09:52:00Z",
                "committed_effects": {
                    "scrum-368-effect-001": {
                        "binding": {"task_id": "SCRUM-368"},
                        "revision": 4,
                    }
                },
            },
        ):
            result = evaluate_cas_write(observation(**outcome_args))
            errors = sorted(validator.iter_errors(result), key=lambda e: e.message)
            self.assertEqual(errors, [], f"schema errors: {[e.message for e in errors]}")


if __name__ == "__main__":
    unittest.main()
