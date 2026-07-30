from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.node_architect.checkpoint_store import (
    CheckpointConflict,
    CheckpointInput,
    digest_payload,
    load_store,
    persist_checkpoint,
    persist_to_file,
    replay_checkpoint,
)

BASE = "3b0938065e71e699d327d041f5b6023ed30a29dc"
HEAD = "a" * 40


def item(expected_revision=None):
    return CheckpointInput(
        task_id="SCRUM-203",
        run_id="g1-scrum-203-fastlane-r3",
        node_id="runtime_checkpoint.checkpoint-persist",
        repository="nhatnguyenquang1838-coder/gwc",
        branch="codex/scrum-203-checkpoint-persist-m5-fastlane-r3-20260730",
        base_sha=BASE,
        head_sha=HEAD,
        scope_hash="sha256:8ab19301ea8de65c0d1d911708e14dd13d1f5d11d49f4b89c1071cbd2d57c332",
        graph_revision="scrum-104-20260726",
        state={"gate": "G2_EXECUTION", "status": "running"},
        expected_revision=expected_revision,
        lease_id="lease-1",
        fencing_token="fence-1",
    )


class CheckpointPersistReplayTests(unittest.TestCase):
    def test_persist_appends_event_and_checkpoint_atomically(self):
        store = persist_checkpoint(load_store(Path("/tmp/nonexistent-gwc-store.json")), item(expected_revision=0), committed_at="2026-07-30T14:00:00Z")
        self.assertEqual(store["revision"], 1)
        self.assertEqual(len(store["events"]), 1)
        record = replay_checkpoint(store, "SCRUM-203", "g1-scrum-203-fastlane-r3", "runtime_checkpoint.checkpoint-persist")
        self.assertIsNotNone(record)
        self.assertEqual(record["state_digest"], digest_payload({"gate": "G2_EXECUTION", "status": "running"}))
        self.assertEqual(record["previous_revision"], 0)

    def test_cas_mismatch_does_not_append_event(self):
        store = persist_checkpoint(load_store(Path("/tmp/nonexistent-gwc-store.json")), item(expected_revision=0), committed_at="2026-07-30T14:00:00Z")
        before = json.dumps(store, sort_keys=True)
        with self.assertRaises(CheckpointConflict):
            persist_checkpoint(store, item(expected_revision=0), committed_at="2026-07-30T14:01:00Z")
        self.assertEqual(json.dumps(store, sort_keys=True), before)

    def test_crash_after_commit_readback_is_replay_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            persist_to_file(path, item(expected_revision=0))
            loaded = load_store(path)
            before_events = list(loaded["events"])
            replayed = replay_checkpoint(loaded, "SCRUM-203", "g1-scrum-203-fastlane-r3", "runtime_checkpoint.checkpoint-persist")
            self.assertIsNotNone(replayed)
            self.assertEqual(loaded["events"], before_events)


if __name__ == "__main__":
    unittest.main()
