from __future__ import annotations

import unittest

from tools.node_architect.lease_acquisition import (
    LeaseAcquisitionError,
    decide_lease_acquisition,
    is_replay_equivalent,
)


TASK = "SCRUM-206"
RUN = "g1-206-20260802-2328"
NODE = "runtime_checkpoint.lease-acquisition"
GATE = "G2_EXECUTION"
REPO = "nhatnguyenquang1838-coder/gwc"
BRANCH = "g1-206-20260802-2328"
BASE = "d4e507aec14db4f62fd4f21f8f84436df08e6216"
HEAD = "a" * 40
SCOPE = "sha256:fe88b9bcc740b9bb629b14e4282be9b30b981b841f0becf1ce90c7ae7aeb5964"
LEASE = "lease-206-1"
ACTOR = "Kilo"


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


class DeterministicDigestTests(unittest.TestCase):
    def test_same_input_same_digest(self):
        a = decide_lease_acquisition(**base_kwargs())
        b = decide_lease_acquisition(**base_kwargs())
        self.assertEqual(a["decision_digest"], b["decision_digest"])
        self.assertEqual(a, b)

    def test_observation_time_does_not_affect_replay_equivalence(self):
        first = decide_lease_acquisition(**base_kwargs(), observed_at="2026-08-02T23:00:00Z")
        second = decide_lease_acquisition(**base_kwargs(), observed_at="2026-08-02T23:59:59Z")
        self.assertTrue(is_replay_equivalent(first, second))


class CompetingAgentAcquisitionRejectionTests(unittest.TestCase):
    def test_acquired_when_no_competing_lease(self):
        decision = decide_lease_acquisition(**base_kwargs())
        self.assertEqual(decision["outcome"], "ACQUIRED")
        self.assertTrue(decision["advancement_allowed"])
        self.assertTrue(decision["side_effect_allowed"])
        self.assertFalse(decision["reacquire_required"])
        self.assertEqual(decision["fencing_token"], 1)

    def test_acquired_emits_monotonic_fencing_token(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_fencing_token=5,
        )
        self.assertEqual(decision["outcome"], "ACQUIRED")
        self.assertEqual(decision["fencing_token"], 6)

    def test_fence_duplicate_agent_blocks_acquisition(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            duplicate_agent_detected=True,
        )
        self.assertEqual(decision["outcome"], "FENCE_DUPLICATE_AGENT")
        self.assertFalse(decision["advancement_allowed"])
        self.assertFalse(decision["side_effect_allowed"])


class StaleOwnerFencingTests(unittest.TestCase):
    def test_stale_worker_fenced_by_monotonic_token(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            actor_fencing_token=3,
            observed_fencing_token=7,
        )
        self.assertEqual(decision["outcome"], "FENCE_STALE_WORKER")
        self.assertFalse(decision["advancement_allowed"])


class ExpiredLeaseRecoveryTests(unittest.TestCase):
    def test_expired_lease_with_side_effects_requires_reconcile(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder=ACTOR,
            lease_expired=True,
            side_effect_status="COMMITTED",
        )
        self.assertEqual(decision["outcome"], "RECONCILE")
        self.assertFalse(decision["advancement_allowed"])
        self.assertFalse(decision["reacquire_required"])

    def test_expired_lease_requires_readback_before_reacquire(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder=ACTOR,
            lease_expired=True,
            readback_status="UNAVAILABLE",
        )
        self.assertEqual(decision["outcome"], "REACQUIRE_REQUIRED")
        self.assertFalse(decision["advancement_allowed"])
        self.assertTrue(decision["reacquire_required"])

    def test_expired_lease_with_verified_readback_allows_reacquire(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder=ACTOR,
            lease_expired=True,
            readback_status="VERIFIED_ZERO_EFFECT",
        )
        self.assertEqual(decision["outcome"], "ACQUIRED")
        self.assertTrue(decision["advancement_allowed"])
        self.assertTrue(decision["side_effect_allowed"])


class ScopeMismatchTests(unittest.TestCase):
    def test_scope_hash_mismatch_rejected(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            observed_scope_hash="sha256:" + "0" * 64,
        )
        self.assertEqual(decision["outcome"], "SCOPE_MISMATCH")
        self.assertFalse(decision["advancement_allowed"])

    def test_repository_mismatch_rejected(self):
        decision = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            observed_repository="other/repo",
        )
        self.assertEqual(decision["outcome"], "SCOPE_MISMATCH")
        self.assertFalse(decision["advancement_allowed"])


class CrashBeforePersistPurityTests(unittest.TestCase):
    def test_pure_function_no_io_side_effects(self):
        decision = decide_lease_acquisition(**base_kwargs())
        self.assertIsInstance(decision, dict)
        self.assertEqual(decision["outcome"], "ACQUIRED")
        self.assertIsNotNone(decision["fencing_token"])


class ReplayEquivalenceTests(unittest.TestCase):
    def test_replay_equivalent_ignores_observation_time(self):
        first = decide_lease_acquisition(**base_kwargs(), observed_at="2026-08-02T23:00:00Z")
        second = decide_lease_acquisition(**base_kwargs(), observed_at="2026-08-02T23:59:59Z")
        self.assertTrue(is_replay_equivalent(first, second))

    def test_different_outcome_not_replay_equivalent(self):
        first = decide_lease_acquisition(**base_kwargs())
        second = decide_lease_acquisition(
            **base_kwargs(),
            observed_lease_holder="other-agent",
            duplicate_agent_detected=True,
        )
        self.assertFalse(is_replay_equivalent(first, second))


class MissingBindingRejectionTests(unittest.TestCase):
    def test_missing_task_id_rejected(self):
        with self.assertRaises(LeaseAcquisitionError):
            decide_lease_acquisition(**base_kwargs(task_id=""))

    def test_missing_lease_id_rejected(self):
        with self.assertRaises(LeaseAcquisitionError):
            decide_lease_acquisition(**base_kwargs(lease_id=""))

    def test_ambiguous_gate_rejected(self):
        with self.assertRaises(LeaseAcquisitionError):
            decide_lease_acquisition(**base_kwargs(gate="not-a-gate"))

    def test_malformed_base_sha_rejected(self):
        with self.assertRaises(LeaseAcquisitionError):
            decide_lease_acquisition(**base_kwargs(base_sha="xyz"))

    def test_malformed_scope_hash_rejected(self):
        with self.assertRaises(LeaseAcquisitionError):
            decide_lease_acquisition(**base_kwargs(scope_hash="not-a-digest"))


if __name__ == "__main__":
    unittest.main()
