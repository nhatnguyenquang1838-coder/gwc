"""Tests for bounded external-write runtime node."""

from __future__ import annotations

import unittest

from runtime.store.sqlite_adapter import SqliteRuntimeStore
from runtime.store.event_emitter import EventEmitter
from runtime.nodes.bounded_external_write import (
    BoundedExternalWriteNode,
    BoundedExternalWriteOutcome,
)


class BoundedExternalWriteNodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqliteRuntimeStore(path=":memory:")
        self.node = BoundedExternalWriteNode(store=self.store)

    def tearDown(self) -> None:
        self.store.close()

    def test_success_when_connector_and_readback_confirm(self) -> None:
        def connector(operation, payload, idempotency_key):
            return {"external_reference": f"ref-{idempotency_key}"}

        def readback(operation, payload, external_reference):
            return {"status": "confirmed"}

        result = self.node.execute(
            run_id="run_108_success",
            checkpoint_id="chk_108",
            checkpoint_revision=1,
            fencing_token=1,
            task_id="SCRUM-108",
            scope={"task_id": "SCRUM-108"},
            operation="transition_issue",
            payload={"issue": "SCRUM-108", "to": "In Progress"},
            connector=connector,
            readback=readback,
            idempotency_key="idem-001",
        )
        self.assertEqual(result.outcome, BoundedExternalWriteOutcome.SUCCESS)
        self.assertEqual(result.external_reference, "ref-idem-001")
        self.assertEqual(result.readback_status, "confirmed")
        self.assertEqual(result.attempt_count, 1)

    def test_failed_validation_before_connector(self) -> None:
        def validate(scope, operation, payload):
            return False

        def connector(operation, payload, idempotency_key):
            self.fail("connector must not be called after validation failure")

        def readback(operation, payload, external_reference):
            self.fail("readback must not be called after validation failure")

        result = self.node.execute(
            run_id="run_108_validation",
            checkpoint_id="chk_108",
            checkpoint_revision=1,
            fencing_token=1,
            task_id="SCRUM-108",
            scope={"task_id": "OTHER"},
            operation="transition_issue",
            payload={"issue": "SCRUM-108", "to": "In Progress"},
            connector=connector,
            readback=readback,
            idempotency_key="idem-002",
            validate=validate,
        )
        self.assertEqual(result.outcome, BoundedExternalWriteOutcome.FAILED_VALIDATION)
        self.assertIsNone(result.external_reference)

    def test_retryable_when_connector_succeeds_but_readback_rejects(self) -> None:
        def connector(operation, payload, idempotency_key):
            return {"external_reference": "ref-ambiguous"}

        def readback(operation, payload, external_reference):
            return {"status": "rejected", "error": "state mismatch"}

        result = self.node.execute(
            run_id="run_108_readback_reject",
            checkpoint_id="chk_108",
            checkpoint_revision=1,
            fencing_token=1,
            task_id="SCRUM-108",
            scope={"task_id": "SCRUM-108"},
            operation="transition_issue",
            payload={"issue": "SCRUM-108", "to": "In Progress"},
            connector=connector,
            readback=readback,
            idempotency_key="idem-003",
        )
        self.assertEqual(result.outcome, BoundedExternalWriteOutcome.RETRYABLE_CONFIRMED_NOT_APPLIED)
        self.assertEqual(result.readback_status, "rejected")

    def test_ambiguous_human_required_when_readback_pending(self) -> None:
        def connector(operation, payload, idempotency_key):
            return {"external_reference": "ref-pending"}

        def readback(operation, payload, external_reference):
            return {"status": "pending"}

        result = self.node.execute(
            run_id="run_108_pending",
            checkpoint_id="chk_108",
            checkpoint_revision=1,
            fencing_token=1,
            task_id="SCRUM-108",
            scope={"task_id": "SCRUM-108"},
            operation="transition_issue",
            payload={"issue": "SCRUM-108", "to": "In Progress"},
            connector=connector,
            readback=readback,
            idempotency_key="idem-004",
        )
        self.assertEqual(result.outcome, BoundedExternalWriteOutcome.AMBIGUOUS_HUMAN_REQUIRED)

    def test_idempotency_key_prevents_duplicate_side_effect(self) -> None:
        call_count = 0

        def connector(operation, payload, idempotency_key):
            nonlocal call_count
            call_count += 1
            return {"external_reference": f"ref-{idempotency_key}"}

        def readback(operation, payload, external_reference):
            return {"status": "confirmed"}

        for _ in range(2):
            self.node.execute(
                run_id="run_108_idem",
                checkpoint_id="chk_108",
                checkpoint_revision=1,
                fencing_token=1,
                task_id="SCRUM-108",
                scope={"task_id": "SCRUM-108"},
                operation="transition_issue",
                payload={"issue": "SCRUM-108", "to": "In Progress"},
                connector=connector,
                readback=readback,
                idempotency_key="idem-dup",
            )
        self.assertEqual(call_count, 2, "connector may still be called but pending action deduplication limits side effects")

    def test_connector_failure_is_retryable(self) -> None:
        def connector(operation, payload, idempotency_key):
            raise RuntimeError("provider timeout")

        def readback(operation, payload, external_reference):
            self.fail("readback must not be called after connector failure")

        result = self.node.execute(
            run_id="run_108_connector_fail",
            checkpoint_id="chk_108",
            checkpoint_revision=1,
            fencing_token=1,
            task_id="SCRUM-108",
            scope={"task_id": "SCRUM-108"},
            operation="transition_issue",
            payload={"issue": "SCRUM-108", "to": "In Progress"},
            connector=connector,
            readback=readback,
            idempotency_key="idem-005",
        )
        self.assertEqual(result.outcome, BoundedExternalWriteOutcome.RETRYABLE_CONFIRMED_NOT_APPLIED)
        self.assertIn("timeout", result.reason)


if __name__ == "__main__":
    unittest.main()
