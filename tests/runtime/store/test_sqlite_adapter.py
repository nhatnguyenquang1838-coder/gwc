"""Tests for SQLite-backed runtime store."""

from __future__ import annotations

import unittest

from runtime.store.sqlite_adapter import SqliteRuntimeStore
from runtime.store.pending_action import PendingActionStore


class SqliteRuntimeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqliteRuntimeStore(path=":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_append_and_read_events(self) -> None:
        event = {
            "schema_version": "0.1",
            "artifact_type": "durable-event",
            "event_id": "evt_1",
            "run_id": "run_store",
            "sequence": 0,
            "parent_event_id": None,
            "event_type": "run_started",
            "occurred_at_utc": "2026-07-27T00:00:00+00:00",
            "actor": {"kind": "node", "id": "tester", "execution_mode": "local_agent"},
            "gate": "G2_EXECUTION",
            "node_id": "tester",
            "outcome": "success",
            "runtime_version": "0.1",
            "node_version": "0.1.0",
            "checkpoint_revision": 0,
            "idempotency_key": None,
            "evidence_refs": [],
            "payload": {},
        }
        self.store.append_event(event)
        events = self.store.read_events("run_store")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], "evt_1")

    def test_write_and_cas_checkpoint(self) -> None:
        checkpoint = {
            "schema_version": "0.1",
            "artifact_type": "durable-checkpoint",
            "checkpoint_id": "chk_store",
            "run_id": "run_store",
            "revision": 0,
            "cas": {"expected_revision": 0},
            "lease": {"owner": "node-1", "expires_at_utc": "2026-07-27T01:00:00+00:00", "fencing_token": 1},
            "current_node_id": "tester",
            "current_node_version": "0.1.0",
            "next_node_id": "next",
            "next_action": "continue",
            "gate": "G2_EXECUTION",
            "status": "running",
            "pending_action_ids": [],
            "scope_hash": "sha256:" + "a" * 64,
            "created_at_utc": "2026-07-27T00:00:00+00:00",
            "updated_at_utc": "2026-07-27T00:00:00+00:00",
        }
        self.store.write_checkpoint(checkpoint)
        loaded = self.store.read_checkpoint("chk_store")
        self.assertEqual(loaded["revision"], 0)
        self.assertTrue(self.store.compare_and_swap_checkpoint("chk_store", 0, {"status": "completed"}))
        updated = self.store.read_checkpoint("chk_store")
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["revision"], 1)
        self.assertFalse(self.store.compare_and_swap_checkpoint("chk_store", 0, {"status": "running"}))

    def test_pending_action_lifecycle(self) -> None:
        store = PendingActionStore(store=self.store)
        action = store.submit(
            run_id="run_pending",
            adapter_id="bounded_external_write",
            operation="transition_issue",
            idempotency_key="idem-pending",
            payload={"issue": "SCRUM-108"},
        )
        self.assertEqual(action.status, "pending")

        self.assertTrue(store.claim(action.action_id, action.run_id))
        self.assertTrue(store.mark_executing(action.action_id, action.run_id))
        self.assertTrue(store.mark_succeeded(action.action_id, action.run_id, external_reference="ref-1"))
        loaded = self.store.read_pending_action(action.action_id)
        self.assertEqual(loaded["status"], "succeeded")
        self.assertEqual(loaded["readback_status"], "confirmed")


if __name__ == "__main__":
    unittest.main()
