from __future__ import annotations

import unittest
from typing import Any

from tools.node_architect.side_effect_check import (
    BLOCKED,
    PASS,
    VERDICT_CONFIRMED,
    VERDICT_DUPLICATE,
    VERDICT_FAILED,
    VERDICT_PENDING,
    VERDICT_UNKNOWN,
    check_side_effects,
)

REPO = "nhatnguyenquang1838-coder/gwc"
BASE = "1" * 40
HEAD = "2" * 40
SCOPE = "sha256:" + "3" * 64
BRANCH = "codex/scrum-341-validation-quality-side-effect-check-r10-20260814"


def observation(**overrides: Any) -> dict[str, Any]:
    base = {
        "effect_id": "eff-1",
        "observation_kind": "external_write",
        "declared_intent": "created_record",
        "verbatim_observation": "created_record",
        "status": "CONFIRMED",
        "authoritative_readback": "created_record",
        "readback_kind": "confirmed",
        "task_id": "SCRUM-341",
        "repository": REPO,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
    }
    base.update(overrides)
    return base


def evidence(**overrides: Any) -> dict[str, Any]:
    base = {
        "task_id": "SCRUM-341",
        "repository": REPO,
        "branch": BRANCH,
        "base_sha": BASE,
        "head_sha": HEAD,
        "scope_hash": SCOPE,
        "graph_revision": "scrum-341-route-v1",
        "idempotency_key": "scrum-341-side-effect-1",
        "pr_number": 276,
        "observations": [observation()],
    }
    base.update(overrides)
    return base


class SideEffectCheckM5Tests(unittest.TestCase):
    def test_confirms_all_observations(self):
        result = check_side_effects(evidence())
        self.assertEqual(result["status"], PASS)
        self.assertEqual(result["reason_codes"], ["SIDE_EFFECTS_RESOLVED"])
        self.assertEqual(result["verdicts"]["eff-1"], VERDICT_CONFIRMED)
        self.assertFalse(result["merge_authority_granted"])

    def test_pending_observation_blocks(self):
        value = evidence(observations=[observation(status="PENDING", authoritative_readback=None, readback_kind="")])
        result = check_side_effects(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertEqual(result["verdicts"]["eff-1"], VERDICT_PENDING)

    def test_failed_observation_blocks(self):
        value = evidence(observations=[observation(status="FAILED", authoritative_readback="not_created")])
        result = check_side_effects(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertEqual(result["verdicts"]["eff-1"], VERDICT_FAILED)

    def test_unknown_interrupted_outcome_blocks_and_must_reconcile(self):
        value = evidence(observations=[observation(interrupted=True)])
        result = check_side_effects(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertEqual(result["verdicts"]["eff-1"], VERDICT_UNKNOWN)
        self.assertIn("UNKNOWN_OUTCOME_UNRECONCILED", result["reason_codes"])

    def test_timeout_interrupted_classified_unknown(self):
        value = evidence(observations=[observation(timeout=True, status="TIMEOUT")])
        result = check_side_effects(value)
        self.assertEqual(result["verdicts"]["eff-1"], VERDICT_UNKNOWN)
        self.assertIn("UNKNOWN_OUTCOME_UNRECONCILED", result["reason_codes"])

    def test_duplicate_equivalent_must_not_duplicate_effect(self):
        value = evidence(observations=[observation(duplicate_of="eff-0", replay_equivalent=True, effect_duplicate="applied")])
        result = check_side_effects(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertEqual(result["verdicts"]["eff-1"], VERDICT_DUPLICATE)
        self.assertIn("DUPLICATE_EFFECT", result["reason_codes"])

    def test_readback_mismatch_blocks(self):
        value = evidence(observations=[observation(declared_intent="created_record", authoritative_readback="deleted_record")])
        result = check_side_effects(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("READBACK_MISMATCH", result["reason_codes"])

    def test_stale_fence_blocks(self):
        value = evidence(observations=[observation(fence_expires_at="2026-08-13T00:00:00Z", evaluated_at="2026-08-14T00:00:00Z")])
        result = check_side_effects(value)
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("STALE_FENCE", result["reason_codes"])

    def test_replay_is_deterministic_and_does_not_duplicate(self):
        cache = {}
        first = check_side_effects(evidence(), replay_cache=cache)
        second = check_side_effects(evidence(), replay_cache=cache)
        self.assertEqual(first["decision_digest"], second["decision_digest"])
        self.assertTrue(second["replayed"])

    def test_replay_with_divergent_input_reconciles(self):
        cache = {}
        check_side_effects(evidence(), replay_cache=cache)
        divergent = evidence(observations=[observation(status="FAILED", authoritative_readback="not_created")])
        result = check_side_effects(divergent, replay_cache=cache)
        # Cache hit with a non-matching digest -> reconcile (fail-closed), not a
        # silent re-run of the new verdicts.
        self.assertFalse(result.get("replayed", False))
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("UNKNOWN_OUTCOME_UNRECONCILED", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
