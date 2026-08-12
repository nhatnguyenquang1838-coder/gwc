"""NA81 current-task tests for SCRUM-329 (runtime_checkpoint.lease-acquisition).

These tests validate the current brief's additional requirements that are NOT
proven by the historical SCRUM-206 test suite:
- SCRUM-329 / pre-prod / R4 binding (not SCRUM-206)
- identical safe reacquire by the current holder without expiry
- concurrent actor denied (duplicate agent / competing lease)
- stale worker fenced by monotonic token
- expiry boundary: verified zero-effect readback allows reacquire
- wrong scope/run rejected (observed scope hash, repository, run_id)
- durable readback preserved in normal acquire path
- deterministic digest and replay equivalence
"""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from node_architect.lease_acquisition import (
    LeaseAcquisitionError,
    decide_lease_acquisition,
    is_replay_equivalent,
)

TASK = "SCRUM-329"
RUN = "SCRUM-288-NA81-20260811-R4"
NODE = "runtime_checkpoint.lease-acquisition"
GATE = "G2_EXECUTION"
REPO = "nhatnguyenquang1838-coder/gwc"
BRANCH = "auto/SCRUM-329-na81-20260810"
BASE = "dfbd831dd2d455fdedeec752390f082d200d6f6c"
HEAD = "b" * 40
SCOPE = "sha256:60a28922c6921e4fe6172aebef5a10a48f419427da132dc3e41f60c0856bcfa3"
LEASE = "lease-329-1"
ACTOR = "Hermes"


def base_kwargs(**overrides):
    data = dict(
        task_id=TASK,
        run_id=RUN,
        node_id=NODE,
        gate=GATE,
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash=SCOPE,
        repository=REPO,
        branch=BRANCH,
        lease_id=LEASE,
        actor_id=ACTOR,
    )
    data.update(overrides)
    return data


class LeaseAcquisitionNa81Tests(unittest.TestCase):
    def test_first_acquire_when_no_competing_lease(self):
        decision = decide_lease_acquisition(**base_kwargs())
        self.assertEqual(decision["outcome"], "ACQUIRED")
        self.assertEqual(decision["reason_code"], "NO_COMPETING_ACTIVE_LEASE")
        self.assertTrue(decision["advancement_allowed"])
        self.assertTrue(decision["side_effect_allowed"])
        self.assertFalse(decision["reacquire_required"])
        self.assertEqual(decision["fencing_token"], 1)

    def test_identical_safe_reacquire_by_current_holder(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder=ACTOR,
            observed_fencing_token=1,
        )
        self.assertEqual(decision["outcome"], "ACQUIRED")
        self.assertEqual(decision["reason_code"], "CURRENT_HOLDER_LEASE_STILL_VALID")
        self.assertTrue(decision["advancement_allowed"])
        self.assertTrue(decision["side_effect_allowed"])
        self.assertFalse(decision["reacquire_required"])
        self.assertEqual(decision["fencing_token"], 2)

    def test_concurrent_actor_denied(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            duplicate_agent_detected=True,
        )
        self.assertEqual(decision["outcome"], "FENCE_DUPLICATE_AGENT")
        self.assertFalse(decision["advancement_allowed"])
        self.assertFalse(decision["side_effect_allowed"])

    def test_stale_holder_fenced_by_monotonic_token(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            actor_fencing_token=3,
            observed_fencing_token=7,
        )
        self.assertEqual(decision["outcome"], "FENCE_STALE_WORKER")
        self.assertFalse(decision["advancement_allowed"])

    def test_expiry_boundary_reacquire_after_verified_readback(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder=ACTOR,
            lease_expired=True,
            readback_status="VERIFIED_ZERO_EFFECT",
        )
        self.assertEqual(decision["outcome"], "ACQUIRED")
        self.assertEqual(decision["reason_code"], "LEASE_REACQUIRED_WITH_MONOTONIC_FENCE")
        self.assertTrue(decision["advancement_allowed"])
        self.assertTrue(decision["side_effect_allowed"])
        self.assertFalse(decision["reacquire_required"])
        self.assertEqual(decision["fencing_token"], 1)

    def test_wrong_scope_hash_rejected(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            observed_scope_hash="sha256:" + "0" * 64,
        )
        self.assertEqual(decision["outcome"], "SCOPE_MISMATCH")
        self.assertFalse(decision["advancement_allowed"])

    def test_wrong_run_id_rejected(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            observed_run_id="other-run-id",
        )
        self.assertEqual(decision["outcome"], "SCOPE_MISMATCH")
        self.assertEqual(decision["reason_code"], "RUN_ID_MISMATCH")
        self.assertFalse(decision["advancement_allowed"])

    def test_durable_readback_preserved_in_acquire_decision(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            readback_status="VERIFIED_ZERO_EFFECT",
        )
        self.assertEqual(decision["outcome"], "ACQUIRED")
        self.assertEqual(decision["readback_status"], "VERIFIED_ZERO_EFFECT")

    def test_deterministic_digest_same_inputs(self):
        a = decide_lease_acquisition(**base_kwargs())
        b = decide_lease_acquisition(**base_kwargs())
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        self.assertEqual(a, b)

    def test_replay_equivalent_ignores_observation_time(self):
        first = decide_lease_acquisition(**base_kwargs(), observed_at="2026-08-11T23:00:00Z")
        second = decide_lease_acquisition(**base_kwargs(), observed_at="2026-08-11T23:05:00Z")
        self.assertTrue(is_replay_equivalent(first, second))

    def test_different_outcome_not_replay_equivalent(self):
        first = decide_lease_acquisition(**base_kwargs())
        second = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            duplicate_agent_detected=True,
        )
        self.assertFalse(is_replay_equivalent(first, second))


if __name__ == "__main__":
    unittest.main()
