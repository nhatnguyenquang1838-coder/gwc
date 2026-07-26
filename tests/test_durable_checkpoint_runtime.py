from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from tools.node_architect.durable_checkpoint_runtime import (
    CheckpointCasMismatch,
    DurableCheckpointStore,
    FencingTokenMismatch,
    LeaseConflict,
    LeaseRequired,
    RuntimeBinding,
    StaleCheckpoint,
)


BASE_SHA = "be46a89f3a31bafbc95f1faf2e62978f98510ba2"


def binding(**overrides):
    data = {
        "task_id": "SCRUM-109",
        "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": BASE_SHA,
        "scope_hash": "sha256:5779d0be8def7b48fc8848ea9c226778e463a2befdefd00a103c8bde6eac7f8e",
        "graph_revision": "scrum-106-p2-scenario-matrix-r2",
    }
    data.update(overrides)
    return RuntimeBinding(**data)


class DurableCheckpointRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.store = DurableCheckpointStore()
        self.now = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
        self.store.create_run(
            run_id="run-109",
            binding=binding(),
            current_node_id="durable-checkpoint-cas-lease-resume",
            next_node_id="durable-checkpoint-cas-lease-resume",
            next_action="load_checkpoint",
            gate="G2_EXECUTION",
            evidence=("SCRUM-105", "SCRUM-106"),
        )

    def test_cas_advances_checkpoint_once_under_active_lease(self):
        leased = self.store.acquire_lease(
            run_id="run-109",
            lease_owner="worker-a",
            ttl_seconds=60,
            now=self.now,
        )

        advanced = self.store.cas_checkpoint(
            run_id="run-109",
            expected_revision=0,
            lease_owner="worker-a",
            fencing_token=leased.fencing_token,
            next_state={
                "current_node_id": "durable-checkpoint-cas-lease-resume",
                "next_node_id": "bounded-external-write",
                "next_action": "resume_after_checkpoint",
                "gate": "G2_EXECUTION",
                "status": "CHECKPOINTED",
                "pending_actions": ["persist-next-checkpoint"],
                "evidence": ["checkpoint revision advanced once"],
            },
            now=self.now + timedelta(seconds=1),
        )

        self.assertEqual(advanced.revision, 1)
        self.assertEqual(advanced.next_action, "resume_after_checkpoint")
        self.assertEqual(advanced.pending_actions, ("persist-next-checkpoint",))

    def test_stale_expected_revision_is_rejected_without_overwrite(self):
        leased = self.store.acquire_lease(
            run_id="run-109",
            lease_owner="worker-a",
            ttl_seconds=60,
            now=self.now,
        )
        self.store.cas_checkpoint(
            run_id="run-109",
            expected_revision=0,
            lease_owner="worker-a",
            fencing_token=leased.fencing_token,
            next_state={"status": "FIRST_ADVANCE"},
            now=self.now + timedelta(seconds=1),
        )

        with self.assertRaises(CheckpointCasMismatch):
            self.store.cas_checkpoint(
                run_id="run-109",
                expected_revision=0,
                lease_owner="worker-a",
                fencing_token=leased.fencing_token,
                next_state={"status": "STALE_OVERWRITE"},
                now=self.now + timedelta(seconds=2),
            )

        self.assertEqual(self.store.read_checkpoint("run-109").status, "FIRST_ADVANCE")

    def test_active_lease_and_fencing_token_are_required(self):
        leased = self.store.acquire_lease(
            run_id="run-109",
            lease_owner="worker-a",
            ttl_seconds=60,
            now=self.now,
        )

        with self.assertRaises(LeaseConflict):
            self.store.acquire_lease(
                run_id="run-109",
                lease_owner="worker-b",
                ttl_seconds=60,
                now=self.now + timedelta(seconds=1),
            )

        with self.assertRaises(FencingTokenMismatch):
            self.store.cas_checkpoint(
                run_id="run-109",
                expected_revision=0,
                lease_owner="worker-a",
                fencing_token=leased.fencing_token - 1,
                next_state={"status": "STALE_TOKEN"},
                now=self.now + timedelta(seconds=1),
            )

    def test_resume_rejects_stale_binding(self):
        with self.assertRaises(StaleCheckpoint):
            self.store.resume_checkpoint(
                run_id="run-109",
                expected_binding=binding(scope_hash="sha256:" + "0" * 64),
                lease_owner="worker-a",
                ttl_seconds=60,
                now=self.now,
            )

    def test_safe_takeover_after_expiry_blocks_old_owner(self):
        first = self.store.acquire_lease(
            run_id="run-109",
            lease_owner="worker-a",
            ttl_seconds=5,
            now=self.now,
        )
        takeover = self.store.resume_checkpoint(
            run_id="run-109",
            expected_binding=binding(),
            lease_owner="worker-b",
            ttl_seconds=60,
            now=self.now + timedelta(seconds=6),
        )

        self.assertEqual(takeover.lease_owner, "worker-b")
        self.assertGreater(takeover.fencing_token, first.fencing_token)

        with self.assertRaises(LeaseRequired):
            self.store.cas_checkpoint(
                run_id="run-109",
                expected_revision=0,
                lease_owner="worker-a",
                fencing_token=first.fencing_token,
                next_state={"status": "OLD_OWNER_WRITE"},
                now=self.now + timedelta(seconds=7),
            )

    def test_suspend_state_is_checkpointed_before_wait(self):
        leased = self.store.acquire_lease(
            run_id="run-109",
            lease_owner="worker-a",
            ttl_seconds=60,
            now=self.now,
        )

        suspended = self.store.cas_checkpoint(
            run_id="run-109",
            expected_revision=0,
            lease_owner="worker-a",
            fencing_token=leased.fencing_token,
            next_state={
                "next_action": "wait_for_human_takeover_decision",
                "gate": "G4_MERGE",
                "status": "SUSPENDED_WAITING_FOR_HUMAN",
                "pending_actions": ["approval-token-required"],
            },
            now=self.now + timedelta(seconds=1),
        )

        self.assertEqual(suspended.next_action, "wait_for_human_takeover_decision")
        self.assertEqual(suspended.gate, "G4_MERGE")
        self.assertIn("approval-token-required", suspended.pending_actions)


if __name__ == "__main__":
    unittest.main()
