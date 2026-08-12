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
# SCRUM-331 context: runtime_checkpoint.cas-write-guard
# ---------------------------------------------------------------------------
SCOPE = "sha256:2d5e3a1f4b7c8906d3e1a5f7b9c2d8e4f6a1b3c5d7e9f0a2b4c6d8e0f1a3b5c7"
BRANCH = "auto/SCRUM-331-na81-20260810"
BASE = "c72d715d0d4dc0e52cad415108b09340f4393b64"
CHECKPOINT_KEY = "SCRUM-331:g2-scrum-331-r4:runtime_checkpoint.cas-write-guard"


def observation(**overrides):
    payload = {
        "task_id": "SCRUM-331",
        "observed_task_id": "SCRUM-331",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "observed_repository": "nhatnguyenquang1838-coder/gwc",
        "branch": BRANCH,
        "observed_branch": BRANCH,
        "base_sha": BASE,
        "observed_base_sha": BASE,
        "scope_hash": SCOPE,
        "observed_scope_hash": SCOPE,
        "checkpoint_key": CHECKPOINT_KEY,
        "run_id": "g2-scrum-331-r4",
        "checkpoint_node_id": "runtime_checkpoint.cas-write-guard",
        "expected_revision": 3,
        "observed_revision": 3,
        "lease_owner": "Hermes",
        "observed_lease_owner": "Hermes",
        "lease_token": "lease-scrum-331",
        "observed_lease_token": "lease-scrum-331",
        "lease_expires_at": "2026-08-12T09:30:00Z",
        "observed_at": "2026-08-12T09:25:00Z",
        "fencing_token": 7,
        "observed_fencing_token": 7,
        "idempotency_key": "scrum-331-effect-001",
        "committed_effects": {},
        "latest_observed_state": {"revision": 3, "status": "ready"},
        "precondition_errors": [],
    }
    payload.update(overrides)
    return payload


class CasWriteGuardNA81Tests(unittest.TestCase):
    """SCRUM-331 NA81 acceptance tests for runtime_checkpoint.cas-write-guard."""

    def test_successful_cas_allows_one_monotonic_write(self):
        result = evaluate_cas_write(observation())
        self.assertEqual(result["outcome"], "ALLOW_WRITE")
        self.assertTrue(result["may_write"])
        self.assertEqual(result["next_revision"], 4)
        self.assertFalse(result["auto_retry_allowed"])

    def test_stale_version_routes_to_repair(self):
        result = evaluate_cas_write(observation(expected_revision=2))
        self.assertEqual(result["outcome"], "CAS_MISMATCH")
        self.assertEqual(result["latest_observed_state"], {"revision": 3, "status": "ready"})
        self.assertEqual(result["reconciliation_route"], "REPAIR")
        self.assertFalse(result["auto_retry_allowed"])

    def test_stale_fence_rejects_even_when_revision_matches(self):
        result = evaluate_cas_write(observation(fencing_token=6))
        self.assertEqual(result["outcome"], "FENCING_MISMATCH")
        self.assertEqual(result["reconciliation_route"], "ABORT_STALE_WORKER")

    def test_wrong_actor_owner_is_fenced(self):
        result = evaluate_cas_write(observation(lease_owner="OtherAgent"))
        self.assertEqual(result["outcome"], "LEASE_OWNER_MISMATCH")
        self.assertIn("STALE_OR_DUPLICATE_AGENT", result["reason_codes"])

    def test_wrong_actor_scope_routes_to_reapproval(self):
        result = evaluate_cas_write(observation(observed_scope_hash="sha256:" + "9" * 64))
        self.assertEqual(result["outcome"], "SCOPE_MISMATCH")
        self.assertEqual(result["reconciliation_route"], "REAPPROVAL_REQUIRED")

    def test_concurrent_race_duplicate_effect_replays(self):
        payload = observation(
            lease_expires_at="2026-08-12T09:30:00Z",
            observed_at="2026-08-12T09:25:00Z",
        )
        effect = {
            "binding": {
                "task_id": "SCRUM-331",
                "repository": "nhatnguyenquang1838-coder/gwc",
                "branch": BRANCH,
                "base_sha": BASE,
                "scope_hash": SCOPE,
                "checkpoint_key": CHECKPOINT_KEY,
                "run_id": "g2-scrum-331-r4",
                "checkpoint_node_id": "runtime_checkpoint.cas-write-guard",
                "lease_owner": "Hermes",
                "lease_token": "lease-scrum-331",
                "fencing_token": 7,
                "lease_expires_at": "2026-08-12T09:30:00Z",
                "idempotency_key": "scrum-331-effect-001",
                "expected_revision": 3,
            },
            "revision": 4,
            "state_digest": "sha256:" + "f" * 64,
            "cas_decision_digest": "sha256:" + "e" * 64,
            "committed_at": "2026-08-12T09:24:00Z",
        }
        payload["committed_effects"] = {payload["idempotency_key"]: effect}
        result = evaluate_cas_write(payload)
        self.assertEqual(result["outcome"], "DUPLICATE_EFFECT_REPLAYED")
        self.assertEqual(result["reconciliation_route"], "RESUME")

    def test_unknown_write_invalid_input_fails_closed(self):
        result = evaluate_cas_write({"task_id": "SCRUM-331"})
        self.assertEqual(result["outcome"], "INVALID_INPUT")
        self.assertEqual(result["reconciliation_route"], "STOP_BLOCKED")

    def test_readback_returns_latest_observed_state_on_mismatch(self):
        result = evaluate_cas_write(observation(expected_revision=2))
        self.assertEqual(result["latest_observed_state"], {"revision": 3, "status": "ready"})
        self.assertIsNotNone(result["decision_digest"])

    def test_replay_is_idempotent(self):
        # same idempotency key on same accepted state returns the same decision shape
        r1 = evaluate_cas_write(observation())
        r2 = evaluate_cas_write(observation())
        self.assertEqual(r1["outcome"], r2["outcome"])
        self.assertEqual(r1["decision_digest"], r2["decision_digest"])

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
                "lease_expires_at": "2026-08-12T09:15:00Z",
                "observed_at": "2026-08-12T09:17:00Z",
                "committed_effects": {
                    "scrum-331-effect-001": {
                        "binding": {"task_id": "SCRUM-331"},
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
