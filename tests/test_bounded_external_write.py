import unittest

from tools.node_architect.bounded_external_write import (
    AdapterDispatch,
    BoundedWriteIntent,
    BoundedWriteReadback,
    BoundedWriteState,
    classify_bounded_external_write,
)

SCOPE = "sha256:" + "1" * 64


def intent(**overrides):
    data = {
        "task_id": "SCRUM-108",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "scope_hash": SCOPE,
        "idempotency_key": "SCRUM-108:projection:1",
        "operation": "jira-shadow-projection",
        "payload_hash": "sha256:" + "2" * 64,
        "checkpoint_revision": 3,
        "fencing_token": 5,
        "persisted": True,
        "lease_owner": "worker-a",
        "evidence": ("intent-log#1",),
    }
    data.update(overrides)
    return BoundedWriteIntent(**data)


def classify(**overrides):
    data = {
        "intent": intent(),
        "dispatch": AdapterDispatch(status="not_called", dispatched=False),
        "readback": None,
        "expected_scope_hash": SCOPE,
        "active_checkpoint_revision": 3,
        "active_fencing_token": 5,
    }
    data.update(overrides)
    return classify_bounded_external_write(**data)


class BoundedExternalWriteTests(unittest.TestCase):
    def test_intent_must_be_persisted_before_mutation(self):
        result = classify(intent=intent(persisted=False))

        self.assertEqual(result.state, BoundedWriteState.FAILED_VALIDATION)
        self.assertFalse(result.mutation_allowed)
        self.assertIn("persisted", result.reason)

    def test_scope_hash_mismatch_prevents_dispatch(self):
        result = classify(expected_scope_hash="sha256:" + "0" * 64)

        self.assertEqual(result.state, BoundedWriteState.FAILED_VALIDATION)
        self.assertFalse(result.mutation_allowed)

    def test_persisted_intent_is_ready_for_first_dispatch(self):
        result = classify()

        self.assertEqual(result.state, BoundedWriteState.READY_TO_DISPATCH)
        self.assertTrue(result.mutation_allowed)
        self.assertFalse(result.repeat_dispatch_allowed)

    def test_timeout_before_effect_is_retryable_only_after_zero_readback(self):
        result = classify(
            dispatch=AdapterDispatch(status="timeout", dispatched=True, evidence=("adapter-timeout",)),
            readback=BoundedWriteReadback(
                observed=True,
                effect_count=0,
                idempotency_key=None,
                scope_hash=None,
                evidence=("live-readback#0",),
            ),
        )

        self.assertEqual(result.state, BoundedWriteState.RETRYABLE_CONFIRMED_NOT_APPLIED)
        self.assertTrue(result.mutation_allowed)
        self.assertTrue(result.repeat_dispatch_allowed)

    def test_timeout_after_effect_passes_only_with_exact_matching_readback(self):
        result = classify(
            dispatch=AdapterDispatch(status="timeout", dispatched=True),
            readback=BoundedWriteReadback(
                observed=True,
                effect_count=1,
                idempotency_key="SCRUM-108:projection:1",
                scope_hash=SCOPE,
                external_reference="JIRA-1",
            ),
        )

        self.assertEqual(result.state, BoundedWriteState.PASS_RECONCILED)
        self.assertFalse(result.mutation_allowed)
        self.assertFalse(result.repeat_dispatch_allowed)

    def test_duplicate_worker_observes_single_effect_without_second_mutation(self):
        result = classify(
            dispatch=AdapterDispatch(status="completed", dispatched=True),
            readback=BoundedWriteReadback(
                observed=True,
                effect_count=1,
                idempotency_key="SCRUM-108:projection:1",
                scope_hash=SCOPE,
                external_reference="JIRA-1",
            ),
        )

        self.assertEqual(result.state, BoundedWriteState.PASS_SINGLE_EFFECT)
        self.assertFalse(result.mutation_allowed)
        self.assertFalse(result.repeat_dispatch_allowed)

    def test_stale_checkpoint_or_fencing_token_prevents_dispatch(self):
        result = classify(active_checkpoint_revision=4)

        self.assertEqual(result.state, BoundedWriteState.STALE_CHECKPOINT)
        self.assertFalse(result.mutation_allowed)

    def test_ambiguous_post_state_requires_human_and_forbids_repeat(self):
        result = classify(dispatch=AdapterDispatch(status="timeout", dispatched=True), readback=None)

        self.assertEqual(result.state, BoundedWriteState.AMBIGUOUS_HUMAN_REQUIRED)
        self.assertTrue(result.human_required)
        self.assertFalse(result.repeat_dispatch_allowed)

    def test_idempotency_mismatch_is_ambiguous_not_pass(self):
        result = classify(
            dispatch=AdapterDispatch(status="completed", dispatched=True),
            readback=BoundedWriteReadback(
                observed=True,
                effect_count=1,
                idempotency_key="other-key",
                scope_hash=SCOPE,
            ),
        )

        self.assertEqual(result.state, BoundedWriteState.AMBIGUOUS_HUMAN_REQUIRED)
        self.assertTrue(result.human_required)
        self.assertFalse(result.mutation_allowed)

    def test_human_takeover_packet_contains_replay_guards(self):
        result = classify(dispatch={"status": "timeout", "dispatched": True}, readback=None)
        packet = result.as_dict()

        self.assertEqual(packet["idempotency_key"], "SCRUM-108:projection:1")
        self.assertEqual(packet["checkpoint_revision"], 3)
        self.assertEqual(packet["fencing_token"], 5)
        self.assertFalse(packet["repeat_dispatch_allowed"])
        self.assertTrue(packet["human_required"])


if __name__ == "__main__":
    unittest.main()
